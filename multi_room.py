"""Opt-in room satellites. All protocol and arbitration work runs on one loop."""
import asyncio
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
import socket
import threading
import time
import uuid

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoomConfig:
    id: str
    name: str
    input_device: int
    output_device: int
    port: int

    @property
    def mac(self):
        node = uuid.uuid5(uuid.NAMESPACE_DNS,
                          f"glassist:{socket.gethostname()}:{self.id}").int
        node = (node & 0xFEFFFFFFFFFF) | 0x020000000000
        return ':'.join(f'{(node >> shift) & 255:02X}' for shift in range(40, -1, -8))


def load_rooms(path):
    """Strict configuration: never silently substitute a different room/device."""
    entries = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    return validate_rooms(entries)


def rooms_enabled():
    import utils
    configured = bool(utils.get_env('HA_ROOMS', '').strip() or utils.get_env('HA_ROOMS_CONFIG', '').strip())
    return utils.get_env('HA_ROOMS_ENABLED', 'true' if configured else 'false').lower() == 'true'


def configured_room_entries():
    """Read settings, importing the earlier file configuration when necessary."""
    import utils
    raw = utils.get_env('HA_ROOMS', '').strip()
    if raw:
        return json.loads(raw)
    legacy = utils.get_env('HA_ROOMS_CONFIG', '').strip()
    if legacy:
        path = Path(legacy)
        if not path.is_absolute():
            path = Path(utils.platform_utils.get_env_file_path()).parent / path
        return json.loads(path.read_text(encoding='utf-8-sig'))
    return []


def validate_rooms(entries):
    if not isinstance(entries, list) or not entries:
        raise ValueError('Room configuration must be a non-empty JSON array')
    rooms = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'id', 'name', 'input_device', 'output_device', 'port'}:
            raise ValueError('Each room requires id, name, input_device, output_device and port')
        if not isinstance(entry['id'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,39}', entry['id']):
            raise ValueError('Room id must contain lowercase letters, digits or hyphens (max 40)')
        if not isinstance(entry['name'], str) or not entry['name'].strip():
            raise ValueError('Room name must not be empty')
        for key in ('input_device', 'output_device', 'port'):
            if type(entry[key]) is not int or entry[key] < 0:
                raise ValueError(f'{key} must be a non-negative integer')
        if not 1024 <= entry['port'] <= 65535:
            raise ValueError('Room port must be between 1024 and 65535')
        rooms.append(RoomConfig(**entry))
    for key in ('id', 'port', 'input_device'):
        if len({getattr(room, key) for room in rooms}) != len(rooms):
            raise ValueError(f'Duplicate room {key}')
    return rooms


class ConversationGate:
    """Loop-owned reservation held until playback and the echo cooldown finish."""
    def __init__(self):
        self.owner = None
        self.playbacks = 0
        self.until = 0.0

    def acquire(self, owner):
        if self.owner is owner:
            return True
        if self.owner is not None or self.playbacks or time.monotonic() < self.until:
            return False
        self.owner = owner
        return True

    def release(self, owner):
        if self.owner is owner:
            self.owner = None
            self.until = time.monotonic() + 0.75

    @property
    def idle(self):
        return self.owner is None and not self.playbacks and time.monotonic() >= self.until


def room_protocol_factory(gate):
    from satellite_protocol import VoiceSatelliteProtocol
    from aioesphomeapi.api_pb2 import VoiceAssistantAnnounceRequest, VoiceAssistantTimerEventResponse
    from aioesphomeapi.model import VoiceAssistantEventType, VoiceAssistantFeature

    class RoomProtocol(VoiceSatelliteProtocol):
        def __init__(self, **kwargs):
            super().__init__(**kwargs, feedback_enabled=False)
            self._watchdog = None
            self._playback_finished_early = False

        def start_conversation(self):
            # Manual triggers must wait for playback and the echo cooldown.
            # Automatic follow-ups call _start_pipeline_run directly and retain
            # ownership of the room across consecutive pipeline runs.
            if not gate.idle:
                return
            super().start_conversation()

        def _start_pipeline_run(self):
            if self._transport is None or not gate.acquire(self):
                return
            self._playback_finished_early = False
            super()._start_pipeline_run()
            if not self._pipeline_active:
                gate.release(self)
                return
            if self._watchdog:
                self._watchdog.cancel()
            self._watchdog = self._loop.call_later(180, self._expire)

        def _expire(self):
            logger.error('Room conversation timed out: %s', self._device_name)
            if self._transport:
                self._transport.close()

        def _release_block(self):
            super()._release_block()
            if not self._pipeline_active:
                gate.release(self)
                if self._watchdog:
                    self._watchdog.cancel()

        def _handle_voice_event(self, event_type, data):
            # Ignore late events after a failed/finished run.
            if gate.owner is not self:
                return
            super()._handle_voice_event(event_type, data)
            if event_type == VoiceAssistantEventType.VOICE_ASSISTANT_ERROR:
                self._continue_conversation = False
                gate.release(self)
                if self._watchdog:
                    self._watchdog.cancel()
            elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END:
                if self._playback_finished_early:
                    self._playback_finished_early = False
                    self._tts_finished_on_loop()
                # Playback can finish before RUN_END arrives.
                if not self._block_wake_words:
                    gate.release(self)

        def _tts_finished_on_loop(self):
            if gate.owner is not self:
                return
            if self._pipeline_active:
                self._playback_finished_early = True
                return
            super()._tts_finished_on_loop()

        def _respond_device_info(self):
            for info in super()._respond_device_info():
                # First version only advertises supported room capabilities.
                info.voice_assistant_feature_flags = (
                    VoiceAssistantFeature.VOICE_ASSISTANT | VoiceAssistantFeature.API_AUDIO)
                yield info

        def handle_message(self, msg):
            if isinstance(msg, (VoiceAssistantAnnounceRequest, VoiceAssistantTimerEventResponse)):
                logger.warning('Timers and announcements are unavailable in room mode')
                return
            yield from super().handle_message(msg)

        def connection_lost(self, exc):
            if self._watchdog:
                self._watchdog.cancel()
            gate.release(self)
            super().connection_lost(exc)

    return RoomProtocol


class MultiRoomManager:
    """One capture stream and wake model per room, one active conversation."""
    def __init__(self, rooms, animation_server):
        self.rooms = rooms
        self.animation = animation_server
        self.gate = ConversationGate()
        self.servers = []
        self.detectors = []
        self.streams = []
        self.readers = []
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._ready = threading.Event()
        self._error = None
        self._loop = None
        self._thread = None
        self._audio = None
        self._play_tasks = set()

    def start(self):
        self._thread = threading.Thread(target=self._run, name='room-satellites', daemon=True)
        self._thread.start()
        if not self._ready.wait(60):
            self.stop()
            raise RuntimeError('Room startup timed out')
        if self._error:
            raise RuntimeError(f'Cannot start room audio: {self._error}') from self._error

    def _run(self):
        try:
            asyncio.run(self._serve())
        except Exception as exc:
            self._error = exc
            logger.exception('Room satellites failed')
        finally:
            self._ready.set()

    async def _serve(self):
        import pyaudio
        import sounddevice as sd
        import utils
        from wake_word_detector import WakeWordDetector
        from satellite_protocol import SatelliteServer

        self._loop = asyncio.get_running_loop()
        self._audio = pyaudio.PyAudio()
        try:
            # Open and validate every device before accepting any conversation.
            for room in self.rooms:
                if self._stop.is_set():
                    return
                info = self._audio.get_device_info_by_index(room.input_device)
                if info['maxInputChannels'] < 1:
                    raise ValueError(f'{room.name}: selected device is not a microphone')
                # In automatic mode probe the device's default rate. The TTS
                # rate is only known (and validated by OutputStream) at playback.
                sd.check_output_settings(device=room.output_device, channels=1,
                                         dtype='float32', samplerate=utils.get_output_sample_rate())
                self.streams.append(self._audio.open(
                    format=pyaudio.paInt16, channels=1, rate=16000, input=True,
                    input_device_index=room.input_device, frames_per_buffer=1280))
                detector = WakeWordDetector()
                if not detector.enabled or detector.model is None:
                    raise ValueError(f'{room.name}: enable and configure local wake word detection')
                self.detectors.append(detector)
                server = SatelliteServer(
                    device_name=f'GLaSSIST-{room.id}', animation_server=self.animation,
                    on_tts_url=lambda url, done_callback=None, r=room: self._play(r, url, done_callback),
                    on_tts_finished=lambda: None, port=room.port,
                    mac_address=room.mac, protocol_factory=room_protocol_factory(self.gate))
                self.servers.append(server)
                await server.start()
            for room, stream, detector, server in zip(self.rooms, self.streams, self.detectors, self.servers):
                reader = threading.Thread(target=self._capture,
                                          args=(room, stream, detector, server),
                                          name=f'microphone-{room.id}', daemon=True)
                self.readers.append(reader)
                reader.start()
            self._ready.set()
            while not self._stop.is_set():
                await asyncio.sleep(0.1)
        finally:
            self._stop.set()
            # Readers wait on loop work, so don't block the loop while joining.
            for reader in self.readers:
                await asyncio.to_thread(reader.join, 2)
            for stream in self.streams:
                try:
                    stream.close()
                except Exception:
                    logger.exception('Closing room microphone failed')
            for server in self.servers:
                try:
                    if server._protocol and server._protocol._transport:
                        server._protocol._transport.close()
                    await server.stop()
                except Exception:
                    logger.exception('Closing room satellite failed')
            if self._play_tasks:
                await asyncio.gather(*self._play_tasks, return_exceptions=True)
            self._audio.terminate()

    def _capture(self, room, stream, detector, server):
        import numpy as np
        was_listening = False
        try:
            while not self._stop.is_set():
                data = stream.read(1280, exception_on_overflow=False)
                future = asyncio.run_coroutine_threadsafe(self._feed(server, data), self._loop)
                listen = future.result(timeout=2)
                if listen:
                    if not was_listening:
                        detector.model.reset()
                    predictions = detector.model.predict(np.frombuffer(data, dtype=np.int16))
                    if any(score >= detector.detection_threshold and name in detector.selected_models
                           for name, score in predictions.items()):
                        self._loop.call_soon_threadsafe(self._wakeup, server)
                was_listening = listen
        except Exception:
            if not self._stop.is_set():
                logger.exception('Room microphone failed: %s; stopping room mode', room.name)
                self._stop.set()
                if self.animation:
                    self.animation.show_error(f'Microphone disconnected: {room.name}. Restart GLaSSIST.', duration=10)

    async def _feed(self, server, data):
        if self._stop.is_set():
            return False
        server.handle_audio(data)
        return not self.paused and self.gate.idle and server.is_connected

    @property
    def paused(self):
        return self._paused.is_set()

    def toggle_pause(self):
        if self.paused:
            self._paused.clear()
        else:
            self._paused.set()

    def _wakeup(self, server):
        if not self.paused and not self._stop.is_set():
            server.wakeup()

    def status(self):
        if self._stop.is_set():
            return 'Room audio stopped; restart GLaSSIST'
        state = 'paused' if self.paused else 'listening'
        connected = sum(server.is_connected for server in self.servers)
        return f'Rooms: {connected}/{len(self.rooms)} connected, wake word {state}'

    def _play(self, room, url, callback):
        # Protocol calls this on its loop. Capture that connection's callback;
        # reconnecting must never finish another connection's conversation.
        self.gate.playbacks += 1
        async def play():
            import utils
            try:
                await asyncio.to_thread(utils.play_audio_from_url, url,
                                        utils.get_env('HA_HOST', ''), None, None,
                                        room.output_device)
            finally:
                self.gate.playbacks -= 1
                if not self._stop.is_set() and callback:
                    callback()
        task = self._loop.create_task(play())
        self._play_tasks.add(task)
        task.add_done_callback(self._play_tasks.discard)

    def start_conversation(self):
        """Hotkey uses the first configured room; wake words select their source."""
        if self._loop and not self._stop.is_set() and self.servers:
            self._loop.call_soon_threadsafe(self.servers[0].start_conversation)

    def stop(self):
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=15)
            if self._thread.is_alive():
                logger.warning('Room shutdown is waiting for audio playback to finish')
