"""
GLaSSIST ESPHome Voice Satellite Protocol.

Implements the ESPHome voice satellite protocol on top of ESPhomeAPIServer.
Home Assistant connects to this server and treats GLaSSIST as a voice satellite
device — enabling timers, conversation mode, and push announcements.

Architecture:
  - HA connects to GLaSSIST TCP server (port 6053 by default)
  - GLaSSIST streams microphone audio to HA via VoiceAssistantAudio messages
  - HA sends TTS URL back via VoiceAssistantEventResponse (TTS_END)
  - GLaSSIST plays TTS locally using existing utils.play_audio_from_url()

Features enabled via feature flags:
  - VOICE_ASSISTANT + API_AUDIO: core pipeline
  - ANNOUNCE: HA can push TTS from automations (assist_satellite.announce)
  - START_CONVERSATION: conversation mode (continue listening after TTS)
  - TIMERS: timer events from HA

Adapted from linux-voice-assistant/satellite.py
(https://github.com/OHF-Voice/linux-voice-assistant)
"""

import asyncio
import logging
import re
import threading
import time
import uuid
from typing import Dict, Iterable, Optional, Set

# pylint: disable=no-name-in-module
from aioesphomeapi.api_pb2 import (  # type: ignore[attr-defined]
    AuthenticationRequest,
    DeviceInfoRequest,
    DeviceInfoResponse,
    ListEntitiesDoneResponse,
    ListEntitiesRequest,
    SubscribeHomeAssistantStatesRequest,
    VoiceAssistantAnnounceFinished,
    VoiceAssistantAnnounceRequest,
    VoiceAssistantAudio,
    VoiceAssistantConfigurationRequest,
    VoiceAssistantConfigurationResponse,
    VoiceAssistantEventResponse,
    VoiceAssistantRequest,
    VoiceAssistantSetConfiguration,
    VoiceAssistantTimerEventResponse,
    VoiceAssistantWakeWord,
)
from aioesphomeapi.core import MESSAGE_TYPE_TO_PROTO
from aioesphomeapi.model import (
    VoiceAssistantEventType,
    VoiceAssistantFeature,
    VoiceAssistantTimerEventType,
)
from google.protobuf import message

import utils
from esphome_server import ESPhomeAPIServer

PROTO_TO_MESSAGE_TYPE = {v: k for k, v in MESSAGE_TYPE_TO_PROTO.items()}

_LOGGER = logging.getLogger(__name__)

TIMER_SOUND_PATH = "sound/timer_finished.wav"


def _generate_timer_beep(path: str) -> None:
    """Generate a simple 880 Hz beep WAV at *path* if it doesn't already exist."""
    import math
    import os
    import struct
    import wave

    os.makedirs(os.path.dirname(path), exist_ok=True)
    sample_rate = 16000
    duration = 0.35
    frequency = 880
    num_samples = int(sample_rate * duration)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        envelope = 1.0 - (t / duration)
        value = int(32767 * envelope * math.sin(2 * math.pi * frequency * t))
        frames += struct.pack("<h", max(-32768, min(32767, value)))
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(frames))
    _LOGGER.info("Generated default timer beep at %s", path)


def _make_mac_address() -> str:
    """Generate a stable-ish MAC address from a UUID seeded by machine hostname."""
    import socket
    seed = socket.gethostname()
    node = uuid.uuid5(uuid.NAMESPACE_DNS, seed).int & 0xFFFFFFFFFFFF
    # Clear multicast bit, set locally administered bit
    node = (node & ~0x010000000000) | 0x020000000000
    mac = ":".join(f"{(node >> (8 * i)) & 0xFF:02X}" for i in range(5, -1, -1))
    return mac


class VoiceSatelliteProtocol(ESPhomeAPIServer):
    """
    GLaSSIST voice satellite — ESPHome protocol implementation.

    Lifecycle managed by SatelliteServer.start() / SatelliteServer.stop().
    Audio chunks are fed via handle_audio(). Wake word triggers are sent via wakeup().
    """

    def __init__(
        self,
        device_name: str,
        mac_address: str,
        animation_server,
        on_tts_url: callable,
        on_tts_finished: callable,
        pipeline_id: Optional[str] = None,
    ) -> None:
        super().__init__(device_name)

        self._device_name = device_name
        self._mac_address = mac_address
        self._animation_server = animation_server
        self._on_tts_url = on_tts_url          # callback(url: str, done_callback)
        self._on_tts_finished = on_tts_finished  # callback() — called when TTS done
        self._pipeline_id = pipeline_id

        # Pipeline state
        self._pipeline_active = False
        self._is_streaming_audio = False
        self._block_wake_words = False
        self._tts_url: Optional[str] = None
        self._tts_text: Optional[str] = None
        self._tts_played = False
        self._continue_conversation = False
        self._timer_active = False
        self._speech_end_handled = False
        self._known_timer_ids: Set[str] = set()  # timers started in this session

        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # -------------------------------------------------------------------------
    # Public API (called from SatelliteServer / main.py)
    # -------------------------------------------------------------------------

    @property
    def is_streaming_audio(self) -> bool:
        return self._is_streaming_audio

    @property
    def pipeline_active(self) -> bool:
        return self._pipeline_active

    @property
    def block_wake_words(self) -> bool:
        return self._block_wake_words or self._pipeline_active

    def handle_audio(self, audio_chunk: bytes) -> None:
        """Feed a microphone audio chunk — called from audio capture thread."""
        if not self._is_streaming_audio:
            return
        self.send_messages([VoiceAssistantAudio(data=audio_chunk)])

    def wakeup(self) -> None:
        """Trigger a pipeline run — called when wake word detected."""
        if self._timer_active:
            _LOGGER.info("Wake word during timer — stopping timer sound (say wake word again to interact)")
            self._timer_active = False
            # Don't call sd.stop() — concurrent sd.play() calls can crash PortAudio.
            # The timer loop checks _timer_active before each repeat and will stop naturally.
            return

        if self.block_wake_words:
            _LOGGER.debug("Wake word blocked — pipeline already active")
            return

        self._start_pipeline_run()

    def start_conversation(self) -> None:
        """Start pipeline run without wake word (e.g. hotkey trigger)."""
        if self._pipeline_active:
            _LOGGER.debug("Pipeline already active, ignoring trigger")
            return
        self._start_pipeline_run()

    # -------------------------------------------------------------------------
    # ESPHome message handling
    # -------------------------------------------------------------------------

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        if isinstance(msg, VoiceAssistantEventResponse):
            data: Dict[str, str] = {arg.name: arg.value for arg in msg.data}
            self._handle_voice_event(VoiceAssistantEventType(msg.event_type), data)

        elif isinstance(msg, VoiceAssistantTimerEventResponse):
            self._handle_timer_event(VoiceAssistantTimerEventType(msg.event_type), msg.timer_id)

        elif isinstance(msg, VoiceAssistantAnnounceRequest):
            _LOGGER.info("HA announce: %s", msg.text)
            self._continue_conversation = msg.start_conversation

            urls = []
            if msg.preannounce_media_id:
                urls.append(msg.preannounce_media_id)
            urls.append(msg.media_id)

            self._play_tts_sequence(urls, done_callback=self._tts_finished)

        elif isinstance(msg, DeviceInfoRequest):
            yield from self._respond_device_info()

        elif isinstance(msg, ListEntitiesRequest):
            yield ListEntitiesDoneResponse()

        elif isinstance(msg, SubscribeHomeAssistantStatesRequest):
            pass  # No entities to report state for

        elif isinstance(msg, VoiceAssistantConfigurationRequest):
            yield VoiceAssistantConfigurationResponse(
                available_wake_words=[],  # GLaSSIST handles wake words locally
                active_wake_words=[],
                max_active_wake_words=0,
            )
            _LOGGER.info("Connected to Home Assistant (VoiceAssistantConfigurationRequest)")
            self._set_animation("idle")

        elif isinstance(msg, VoiceAssistantSetConfiguration):
            pass  # Wake words managed locally by GLaSSIST

    def process_packet(self, msg_type: int, packet_data: bytes) -> None:
        super().process_packet(msg_type, packet_data)

        if msg_type == PROTO_TO_MESSAGE_TYPE[AuthenticationRequest]:
            _LOGGER.debug("HA authenticated — connection established")

    # -------------------------------------------------------------------------
    # Voice event state machine
    # -------------------------------------------------------------------------

    def _handle_voice_event(
        self, event_type: VoiceAssistantEventType, data: Dict[str, str]
    ) -> None:
        _LOGGER.info("Voice event: %s data=%s", event_type.name, data)

        if event_type == VoiceAssistantEventType.VOICE_ASSISTANT_RUN_START:
            self._tts_url = data.get("url")
            self._tts_text = None
            self._tts_played = False
            self._continue_conversation = False
            self._pipeline_active = True
            self._is_streaming_audio = True
            self._block_wake_words = True
            self._speech_end_handled = False
            self._set_animation("listening")

        elif event_type in (
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_END,
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_END,
        ):
            if self._speech_end_handled:
                return
            self._speech_end_handled = True
            self._is_streaming_audio = False
            self._set_animation("processing")

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_INTENT_END:
            if data.get("continue_conversation") == "1":
                self._continue_conversation = True
                _LOGGER.info("Conversation mode active — will continue after TTS")

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_INTENT_PROGRESS:
            if data.get("tts_start_streaming") == "1":
                self._play_tts()

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_START:
            self._tts_text = data.get("text", "")
            if self._tts_text and self._animation_server and utils.get_env("HA_RESPONSE_TEXT_ENABLED", "true").lower() in ("true", "1", "yes"):
                try:
                    self._animation_server.send_response_text(self._tts_text)
                except Exception:
                    pass

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_END:
            self._tts_url = data.get("url")
            self._play_tts()
            self._set_animation("responding")

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END:
            self._is_streaming_audio = False
            self._pipeline_active = False
            if not self._tts_played:
                self._tts_finished()
            self._tts_played = False

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_ERROR:
            code = data.get("code", "")
            msg_text = data.get("message", "")
            _LOGGER.error("Pipeline error: %s — %s", code, msg_text)
            self._pipeline_active = False
            self._is_streaming_audio = False
            self._block_wake_words = False
            self._speech_end_handled = False
            self._set_animation("error")

    def _handle_timer_event(self, event_type: VoiceAssistantTimerEventType, timer_id: str = "") -> None:
        _LOGGER.debug("Timer event: %s (id=%s)", event_type.name, timer_id)

        if event_type == VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_STARTED:
            _LOGGER.info("Timer started (id=%s)", timer_id)
            self._known_timer_ids.add(timer_id)

        elif event_type == VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_CANCELLED:
            _LOGGER.info("Timer cancelled (id=%s)", timer_id)
            self._known_timer_ids.discard(timer_id)

        elif event_type == VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED:
            if timer_id not in self._known_timer_ids:
                _LOGGER.info("Ignoring timer finished for unknown timer (id=%s) — likely from before app start", timer_id)
                return
            self._known_timer_ids.discard(timer_id)
            if not self._timer_active:
                self._timer_active = True
                if self._pipeline_active:
                    _LOGGER.info("Timer finished but pipeline active — will play after pipeline ends (id=%s)", timer_id)
                else:
                    _LOGGER.info("Timer finished — playing sound (id=%s)", timer_id)
                    self._play_timer_sound()

    # -------------------------------------------------------------------------
    # Pipeline control
    # -------------------------------------------------------------------------

    def _start_pipeline_run(self) -> None:
        request = VoiceAssistantRequest(start=True)
        if self._pipeline_id:
            # pipeline_id is passed via HA configuration, not the protobuf message,
            # but we set it here for completeness if the field exists
            if hasattr(request, "pipeline_id"):
                request.pipeline_id = self._pipeline_id

        self._pipeline_active = True
        self._block_wake_words = True
        self._is_streaming_audio = True
        self._speech_end_handled = False
        self._tts_played = False
        self._continue_conversation = False

        try:
            self.send_messages([request])
        except Exception:
            _LOGGER.exception("Failed to send pipeline start request; resetting state")
            self._pipeline_active = False
            self._is_streaming_audio = False
            return
        utils.play_feedback_sound("activation")
        self._set_animation("listening")
        _LOGGER.info("Pipeline run started")

    def _send_end_of_stream(self) -> None:
        try:
            msg = VoiceAssistantAudio()
            if hasattr(msg, "end"):
                msg.end = True
            elif hasattr(msg, "end_of_stream"):
                msg.end_of_stream = True
            else:
                msg.data = b""
            self.send_messages([msg])
        except Exception:
            _LOGGER.exception("Failed to send end-of-stream marker")

    # -------------------------------------------------------------------------
    # TTS playback
    # -------------------------------------------------------------------------

    def _play_tts(self) -> None:
        if not self._tts_url or self._tts_played:
            return
        self._tts_played = True
        _LOGGER.debug("Playing TTS: %s", self._tts_url)
        self._on_tts_url(self._tts_url, done_callback=self._tts_finished)

    def _play_tts_sequence(self, urls: list, done_callback: callable) -> None:
        """Play a sequence of URLs (for announce preannounce + main audio)."""
        if not urls:
            done_callback()
            return

        url = urls[0]
        remaining = urls[1:]

        def _next():
            self._play_tts_sequence(remaining, done_callback)

        self._on_tts_url(url, done_callback=_next if remaining else done_callback)

    def _tts_finished(self) -> None:
        """Called from TTS playback thread — schedule on asyncio loop for thread safety."""
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._tts_finished_on_loop)
        else:
            self._tts_finished_on_loop()

    def _tts_finished_on_loop(self) -> None:
        """Runs on the asyncio event loop thread."""
        _LOGGER.info(
            "_tts_finished_on_loop: continue_conversation=%s pipeline_active=%s",
            self._continue_conversation,
            self._pipeline_active,
        )
        self.send_messages([VoiceAssistantAnnounceFinished()])
        self._on_tts_finished()

        if not self._continue_conversation and self._tts_text:
            if utils.get_env("HA_CONTINUE_ON_QUESTION", "false").lower() in ("true", "1", "yes"):
                text = self._tts_text.rstrip()
                if text.endswith("?"):
                    self._continue_conversation = True
                    _LOGGER.info("Continuing conversation — TTS ends with '?': %s", text[-60:])

        if self._continue_conversation:
            _LOGGER.info("Continuing conversation — starting new pipeline run")
            self._start_pipeline_run()
        elif self._timer_active:
            _LOGGER.info("Pipeline ended — playing pending timer sound")
            self._set_animation("hidden")
            # Release wake word block so user can interact while timer sounds
            self._block_wake_words = True
            loop = self._loop
            if loop is not None:
                def _schedule():
                    loop.call_later(0.5, self._release_block)
                loop.call_soon_threadsafe(_schedule)
            else:
                self._release_block()
            self._play_timer_sound()
        else:
            self._block_wake_words = True
            loop = self._loop
            if loop is not None:
                def _schedule():
                    loop.call_later(0.5, self._release_block)
                loop.call_soon_threadsafe(_schedule)
            else:
                self._release_block()
            self._set_animation("hidden")
            utils.play_feedback_sound("deactivation")

    def _release_block(self) -> None:
        self._block_wake_words = False

    # -------------------------------------------------------------------------
    # Timer sound
    # -------------------------------------------------------------------------

    def _play_timer_sound(self) -> None:
        import os
        custom = utils.get_env("HA_TIMER_SOUND", "")
        if custom and os.path.isfile(custom):
            sound_path = os.path.normpath(custom)
        else:
            sound_path = os.path.normpath(os.path.join(os.path.dirname(__file__), TIMER_SOUND_PATH))
        if not os.path.exists(sound_path):
            _LOGGER.warning("Timer sound not found: %s — generating default beep", sound_path)
            try:
                _generate_timer_beep(sound_path)
            except Exception:
                _LOGGER.exception("Could not generate timer beep")
                self._timer_active = False
                return

        def _loop_sound():
            if not self._timer_active:
                return
            self._on_tts_url(sound_path, done_callback=_check_repeat)

        def _check_repeat():
            if not self._timer_active:
                return
            if self._pipeline_active:
                # Pipeline interrupted the timer sound — _tts_finished_on_loop will restart it
                _LOGGER.debug("Timer sound interrupted by active pipeline — deferring restart")
                return
            time.sleep(1.0)
            _loop_sound()

        _loop_sound()

    def stop_timer(self) -> None:
        """Stop looping timer sound — call when user says 'stop' or presses hotkey."""
        self._timer_active = False
        _LOGGER.info("Timer stopped by user")

    # -------------------------------------------------------------------------
    # Device info response
    # -------------------------------------------------------------------------

    def _respond_device_info(self) -> Iterable[message.Message]:
        base_name = re.sub(r"[\s-]+", "-", self._device_name.lower()).strip("-")
        mac_no_colon = self._mac_address.replace(":", "").lower()
        mac_last6 = mac_no_colon[-6:]
        device_name = f"{base_name}-{mac_last6}"

        yield DeviceInfoResponse(
            uses_password=False,
            name=device_name,
            mac_address=self._mac_address,
            manufacturer="GLaSSIST",
            model="GLaSSIST Voice Satellite",
            voice_assistant_feature_flags=(
                VoiceAssistantFeature.VOICE_ASSISTANT
                | VoiceAssistantFeature.API_AUDIO
                | VoiceAssistantFeature.ANNOUNCE
                | VoiceAssistantFeature.START_CONVERSATION
                | VoiceAssistantFeature.TIMERS
            ),
        )

    # -------------------------------------------------------------------------
    # Animation helpers
    # -------------------------------------------------------------------------

    def _set_animation(self, state: str) -> None:
        if self._animation_server is None:
            return
        try:
            if state == "idle":
                pass  # don't change state to idle — let it stay hidden
            elif state == "hidden":
                self._animation_server.change_state("hidden")
            else:
                self._animation_server.change_state(state)
        except Exception:
            _LOGGER.debug("Animation state change failed: %s", state)

    # -------------------------------------------------------------------------
    # asyncio.Protocol overrides
    # -------------------------------------------------------------------------

    def connection_made(self, transport) -> None:
        super().connection_made(transport)
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        if self._animation_server:
            try:
                self._animation_server.show_success("Connected to Home Assistant", duration=2.0)
            except Exception:
                pass

    def connection_lost(self, exc) -> None:
        super().connection_lost(exc)
        self._pipeline_active = False
        self._is_streaming_audio = False
        self._block_wake_words = False
        self._tts_url = None
        self._tts_played = False
        self._continue_conversation = False
        self._timer_active = False
        self._speech_end_handled = False
        self._known_timer_ids.clear()
        if self._animation_server:
            try:
                self._animation_server.show_connecting("Connecting...")
            except Exception:
                pass


class SatelliteServer:
    """
    Manages the ESPHome TCP server lifecycle.

    Usage:
        server = SatelliteServer(device_name, animation_server, on_tts_url, on_tts_finished)
        await server.start()      # starts TCP server
        server.handle_audio(chunk)  # feed mic audio chunks
        server.wakeup()           # trigger on wake word
        await server.stop()       # shutdown
    """

    def __init__(
        self,
        device_name: str,
        animation_server,
        on_tts_url: callable,
        on_tts_finished: callable,
        port: int = 6053,
        pipeline_id: Optional[str] = None,
    ) -> None:
        self._device_name = device_name
        self._animation_server = animation_server
        self._on_tts_url = on_tts_url
        self._on_tts_finished = on_tts_finished
        self._port = port
        self._pipeline_id = pipeline_id
        self._mac_address = utils.get_env("DEVICE_MAC", "") or _make_mac_address()

        self._server = None
        self._protocol: Optional[VoiceSatelliteProtocol] = None
        self._zeroconf = None
        self._zeroconf_info = None

    def _make_protocol(self) -> VoiceSatelliteProtocol:
        protocol = VoiceSatelliteProtocol(
            device_name=self._device_name,
            mac_address=self._mac_address,
            animation_server=self._animation_server,
            on_tts_url=self._on_tts_url,
            on_tts_finished=self._on_tts_finished,
            pipeline_id=self._pipeline_id,
        )
        self._protocol = protocol
        return protocol

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._server = await loop.create_server(
            self._make_protocol,
            host="0.0.0.0",
            port=self._port,
        )
        _LOGGER.info(
            "ESPHome satellite server listening on port %d (device: %s, MAC: %s)",
            self._port,
            self._device_name,
            self._mac_address,
        )
        await self._register_mdns()

    async def _register_mdns(self) -> None:
        """Register as an ESPHome device via mDNS so HA can auto-discover GLaSSIST."""
        import socket
        try:
            from zeroconf import ServiceInfo
            from zeroconf.asyncio import AsyncZeroconf
        except ImportError:
            _LOGGER.warning("zeroconf not available — mDNS auto-discovery disabled")
            return

        # Resolve the local IP by connecting a UDP socket (no actual data sent)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            local_ip = "127.0.0.1"

        # ESPHome service name: lowercase device name with spaces → dashes
        service_slug = self._device_name.lower().replace(" ", "-")
        mac_plain = self._mac_address.replace(":", "").lower()

        self._zeroconf_info = ServiceInfo(
            type_="_esphomelib._tcp.local.",
            name=f"{service_slug}._esphomelib._tcp.local.",
            addresses=[socket.inet_aton(local_ip)],
            port=self._port,
            properties={
                "friendly_name": self._device_name,
                "version": "2024.1.0",
                "mac": mac_plain,
                "platform": "POSIX",
                "board": "native",
                "network": "ethernet",
            },
            server=f"{service_slug}.local.",
        )

        try:
            self._zeroconf = AsyncZeroconf()
            await self._zeroconf.async_register_service(self._zeroconf_info)
            _LOGGER.info(
                "mDNS: registered '%s' at %s:%d — HA can now auto-discover GLaSSIST",
                service_slug,
                local_ip,
                self._port,
            )
        except Exception:
            _LOGGER.exception("mDNS registration failed (non-fatal)")

    async def stop(self) -> None:
        if self._zeroconf and self._zeroconf_info:
            try:
                await self._zeroconf.async_unregister_service(self._zeroconf_info)
                await self._zeroconf.async_close()
            except Exception:
                _LOGGER.debug("mDNS unregister error (non-fatal)", exc_info=True)
            self._zeroconf = None
            self._zeroconf_info = None

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            _LOGGER.info("ESPHome satellite server stopped")

    def handle_audio(self, audio_chunk: bytes) -> None:
        """Feed microphone audio — call from audio capture thread."""
        if self._protocol:
            self._protocol.handle_audio(audio_chunk)

    def wakeup(self) -> None:
        """Trigger pipeline run on wake word detection."""
        if self._protocol:
            self._protocol.wakeup()
        else:
            _LOGGER.warning("Wake word detected but HA not connected — ignoring")
            if self._animation_server:
                self._animation_server.show_error("Brak połączenia z Home Assistant", duration=3.0)

    def start_conversation(self) -> None:
        """Trigger pipeline run from hotkey / tray menu."""
        if self._protocol:
            self._protocol.start_conversation()
        else:
            _LOGGER.warning("Voice trigger but HA not connected")

    def stop_timer(self) -> None:
        """Stop looping timer sound."""
        if self._protocol:
            self._protocol.stop_timer()

    @property
    def is_connected(self) -> bool:
        return self._protocol is not None and self._protocol._transport is not None

    @property
    def is_streaming_audio(self) -> bool:
        return self._protocol is not None and self._protocol.is_streaming_audio
