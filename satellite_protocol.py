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
import os
import re
import tempfile
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

import ai_errors
import utils
from esphome_server import ESPhomeAPIServer
from media_ducking import media_ducker

PROTO_TO_MESSAGE_TYPE = {v: k for k, v in MESSAGE_TYPE_TO_PROTO.items()}

_LOGGER = logging.getLogger(__name__)

TIMER_SOUND_PATH = "sound/timer_finished.wav"
MDNS_RETRY_SECONDS = 30
ERROR_SPEECH_TIMEOUT = 10


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


def _ha_host_ipv4() -> Optional[str]:
    """HA_HOST when it is an IPv4 literal; host names are not resolved here."""
    import ipaddress
    from urllib.parse import urlsplit

    host = utils.get_env("HA_HOST", "").strip()
    if not host:
        return None
    try:
        name = urlsplit(host if "//" in host else f"//{host}").hostname
        return str(ipaddress.IPv4Address(name)) if name else None
    except ValueError:
        return None


def find_local_ipv4() -> Optional[str]:
    """LAN IPv4 address to advertise over mDNS, or None when there is none.

    Asks the OS which address it would use to reach Home Assistant (HA_HOST, works without a
    default gateway) or the internet; a UDP "connect" sends nothing. Without a route it uses an
    adapter address only when exactly one candidate exists: with several (VPN, Hyper-V/WSL,
    VirtualBox) a guess could hand HA an unreachable address. Loopback and link-local
    (169.254.x.x) addresses are never returned.
    """
    import ipaddress
    import socket

    def usable(address: str) -> bool:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        return ip.version == 4 and not (ip.is_loopback or ip.is_link_local or ip.is_unspecified)

    for target in (_ha_host_ipv4(), "8.8.8.8"):
        if target is None:
            continue
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.connect((target, 80))
                address = sock.getsockname()[0]
            finally:
                sock.close()
            if usable(address):
                return address
        except OSError:
            pass
    try:
        import ifaddr  # installed together with zeroconf
        candidates = {ip.ip for adapter in ifaddr.get_adapters() for ip in adapter.ips
                      if ip.is_IPv4 and usable(ip.ip)}
    except Exception:
        _LOGGER.debug("mDNS: listing network adapters failed", exc_info=True)
        return None
    private = {a for a in candidates if ipaddress.ip_address(a).is_private}
    pool = private or candidates
    return next(iter(pool)) if len(pool) == 1 else None


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
        feedback_enabled: bool = True,
    ) -> None:
        super().__init__(device_name)

        self._device_name = device_name
        self._mac_address = mac_address
        self._animation_server = animation_server
        self._on_tts_url = on_tts_url
        self._on_tts_finished = on_tts_finished  # callback() — called when TTS done
        self._pipeline_id = pipeline_id
        self._feedback_enabled = feedback_enabled

        # Pipeline state
        self._pipeline_active = False
        self._is_streaming_audio = False
        self._block_wake_words = False
        self._tts_url: Optional[str] = None
        self._tts_text: Optional[str] = None
        self._tts_override: Optional[str] = None   # friendly text for an AI-service error, spoken locally
        self._error_speech_path: Optional[str] = None
        self._tts_played = False
        self._tts_completed = False
        self._tts_end_received = False
        self._playback_cancel = None
        self._ignore_cancelled_events = False
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

    @property
    def can_interrupt_response(self) -> bool:
        return self._playback_cancel is not None and utils.get_env_bool("HA_WAKE_WORD_INTERRUPT", False)

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
            if self.can_interrupt_response:
                self.cancel_interaction(restart=True)
                return
            _LOGGER.debug("Wake word blocked — pipeline already active")
            return

        self._start_pipeline_run()

    def start_conversation(self) -> None:
        """Start pipeline run without wake word (e.g. hotkey trigger)."""
        if self.block_wake_words or self._playback_cancel:
            _LOGGER.debug("Pipeline already active, ignoring trigger")
            return
        self._start_pipeline_run()

    def toggle_conversation(self) -> None:
        """Cancel the current interaction or start one if idle."""
        if not self.cancel_interaction():
            self.start_conversation()

    def cancel_interaction(self, *, restart=False) -> bool:
        if not self._pipeline_active and self._playback_cancel is None:
            return False

        if self._pipeline_active:
            self.send_messages([VoiceAssistantRequest(start=False)])
            self._ignore_cancelled_events = True
        if self._playback_cancel:
            self._playback_cancel.set()
            self._playback_cancel = None
        self._pipeline_active = False
        self._is_streaming_audio = False
        self._tts_url = self._tts_text = self._tts_override = None
        self._tts_played = False
        self._tts_completed = False
        self._tts_end_received = False
        self._continue_conversation = False
        utils.processing_sound_loop.stop()
        media_ducker.restore()
        self._set_animation("hidden")
        # HA uses the same completion message for interrupted TTS and announcements.
        self.send_messages([VoiceAssistantAnnounceFinished()])
        if restart:
            self._start_pipeline_run()
        else:
            self._release_block()
            if self._timer_active:
                self._play_timer_sound()
        return True

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
            if self._playback_cancel:
                self._playback_cancel.set()
            self._continue_conversation = msg.start_conversation

            urls = []
            if msg.preannounce_media_id:
                urls.append(msg.preannounce_media_id)
            urls.append(msg.media_id)

            media_ducker.duck()
            self._block_wake_words = True
            self._play_tts_sequence(urls)

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

        if self._ignore_cancelled_events:
            # Events have no run ID in ESPHome. Wait for the next run's start.
            if event_type != VoiceAssistantEventType.VOICE_ASSISTANT_RUN_START or not self._pipeline_active:
                return
            self._ignore_cancelled_events = False

        if event_type == VoiceAssistantEventType.VOICE_ASSISTANT_RUN_START:
            self._tts_url = data.get("url")
            self._tts_text = None
            self._tts_override = None
            self._tts_played = False
            self._tts_completed = False
            self._tts_end_received = False
            self._continue_conversation = False
            self._pipeline_active = True
            self._is_streaming_audio = True
            self._block_wake_words = True
            self._speech_end_handled = False
            media_ducker.duck()
            self._set_animation("listening")

        elif event_type in (
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_END,
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_END,
        ):
            first_speech_end = not self._speech_end_handled
            if first_speech_end:
                self._speech_end_handled = True
                self._is_streaming_audio = False
                self._set_animation("processing")
            wait_for_text = utils.get_env("HA_PROCESSING_SOUND_START", "stt_vad_end").lower() == "stt_end"
            speech_recognized = (
                event_type == VoiceAssistantEventType.VOICE_ASSISTANT_STT_END
                and bool(data.get("text", "").strip())
            )
            if self._feedback_enabled and (speech_recognized if wait_for_text else first_speech_end):
                utils.processing_sound_loop.start()

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_INTENT_END:
            if data.get("continue_conversation") == "1":
                self._continue_conversation = True
                _LOGGER.info("Conversation mode active — will continue after TTS")

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_INTENT_PROGRESS:
            if data.get("tts_start_streaming") == "1":
                self._play_tts(streaming=True)

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_START:
            self._tts_text = data.get("text", "")
            friendly = ai_errors.friendly_error(self._tts_text)
            if friendly:
                _LOGGER.info("AI service error answer replaced: %s", friendly)
                self._tts_text = self._tts_override = friendly
            if self._tts_text and self._animation_server and utils.get_env("HA_RESPONSE_TEXT_ENABLED", "true").lower() in ("true", "1", "yes"):
                try:
                    self._animation_server.send_response_text(self._tts_text)
                except Exception:
                    pass

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_END:
            self._tts_url = data.get("url")
            self._tts_end_received = True
            self._play_tts()

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END:
            utils.processing_sound_loop.stop()
            self._is_streaming_audio = False
            self._pipeline_active = False
            playback_done = not self._tts_played or self._tts_completed
            self._tts_played = False
            if playback_done:
                self._tts_finished_on_loop()

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_ERROR:
            code = data.get("code", "")
            msg_text = data.get("message", "")
            _LOGGER.error("Pipeline error: %s — %s", code, msg_text)
            utils.processing_sound_loop.stop()
            if self._playback_cancel:
                self._playback_cancel.set()
                self._playback_cancel = None
            self._pipeline_active = False
            self._is_streaming_audio = False
            self._block_wake_words = False
            self._speech_end_handled = False
            media_ducker.restore()
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
        self._tts_completed = False
        self._tts_end_received = False
        self._continue_conversation = False

        try:
            self.send_messages([request])
        except Exception:
            _LOGGER.exception("Failed to send pipeline start request; resetting state")
            self._pipeline_active = False
            self._is_streaming_audio = False
            self._block_wake_words = False
            return
        media_ducker.duck()
        if self._feedback_enabled:
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

    def _play_tts(self, *, streaming=False) -> None:
        if not self._tts_url or self._tts_played:
            return
        utils.processing_sound_loop.stop()
        self._tts_played = True
        _LOGGER.debug("Playing TTS: %s", self._tts_url)
        self._set_animation("responding")
        # A streamed reply is already playing HA's audio; only the shown text is replaced then.
        if self._tts_override and not streaming:
            self._play_error_speech(self._tts_override)
            return
        self._play_tts_sequence([self._tts_url], streaming=streaming)

    def _play_error_speech(self, text: str) -> None:
        """Speak the friendly AI-error sentence locally; HA's English audio is the fallback."""
        cancel_event = threading.Event()
        self._playback_cancel = cancel_event        # the hotkey can cancel while synthesizing
        url, loop = self._tts_url, self._loop
        # A new file each time: a cancelled synthesis may still hold the previous one open.
        self._remove_error_speech()
        fd, path = tempfile.mkstemp(prefix="glassist-ai-error-", suffix=".wav")
        os.close(fd)
        self._error_speech_path = path

        def start(spoken: bool) -> None:
            # Runs once: playback replaces _playback_cancel, so a late call is ignored.
            if self._playback_cancel is not cancel_event:
                return
            self._play_tts_sequence([path if spoken else url])

        def synthesize() -> None:
            spoken = ai_errors.synthesize(text, path)
            if loop is None:
                start(spoken)
            elif not loop.is_closed():
                loop.call_soon_threadsafe(start, spoken)

        threading.Thread(target=synthesize, name="ai-error-speech", daemon=True).start()
        if loop is not None:
            # Should the voice hang, the user still gets Home Assistant's answer.
            loop.call_later(ERROR_SPEECH_TIMEOUT, start, False)

    def _remove_error_speech(self) -> None:
        if self._error_speech_path:
            try:
                os.remove(self._error_speech_path)
            except OSError:
                pass
            self._error_speech_path = None

    def _play_tts_sequence(self, urls: list, *, streaming=False) -> None:
        """Play a sequence of URLs (for announce preannounce + main audio)."""
        cancel_event = threading.Event()
        self._playback_cancel = cancel_event
        remaining = iter(urls)

        def next_url(success=True):
            if self._playback_cancel is not cancel_event:
                return
            if not success and streaming and (self._pipeline_active or self._tts_end_received):
                # Streaming failed; play the final TTS_END audio instead.
                self._playback_cancel = None
                self._tts_played = False
                if self._tts_end_received:
                    self._play_tts()
                if self._playback_cancel is None and not self._pipeline_active:
                    self._tts_finished_on_loop()
                return
            url = next(remaining, None)
            if url is None:
                self._playback_cancel = None
                if self._tts_played and self._pipeline_active:
                    self._tts_completed = True
                    return
                self._tts_finished_on_loop()
                return
            self._on_tts_url(url, done_callback=finished, cancel_event=cancel_event, streaming=streaming)

        def finished(success=True):
            if self._loop is not None:
                if not self._loop.is_closed():
                    self._loop.call_soon_threadsafe(next_url, success)
            else:
                next_url(success)

        next_url()

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
            return

        media_ducker.restore()
        if self._timer_active:
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
            if self._feedback_enabled:
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

        def _check_repeat(_success=True):
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
        if self._playback_cancel:
            self._playback_cancel.set()
            self._playback_cancel = None
        utils.processing_sound_loop.stop()
        self._pipeline_active = False
        self._is_streaming_audio = False
        self._block_wake_words = False
        self._tts_url = None
        self._tts_played = False
        self._continue_conversation = False
        self._timer_active = False
        self._speech_end_handled = False
        self._known_timer_ids.clear()
        media_ducker.restore()
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
        mac_address: Optional[str] = None,
        protocol_factory=None,
    ) -> None:
        self._device_name = device_name
        self._animation_server = animation_server
        self._on_tts_url = on_tts_url
        self._on_tts_finished = on_tts_finished
        self._port = port
        self._pipeline_id = pipeline_id
        self._mac_address = mac_address or utils.get_env("DEVICE_MAC", "") or _make_mac_address()
        self._protocol_factory = protocol_factory or VoiceSatelliteProtocol

        self._server = None
        self._protocol: Optional[VoiceSatelliteProtocol] = None
        self._zeroconf = None
        self._zeroconf_info = None
        self._mdns_retry: Optional[asyncio.Task] = None

    def _make_protocol(self) -> VoiceSatelliteProtocol:
        protocol = self._protocol_factory(
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

        local_ip = find_local_ipv4()
        if local_ip is None:
            # Never advertise a loopback or guessed address: HA would store it and lose the device.
            _LOGGER.warning("mDNS: no LAN IPv4 address yet, retrying every %d s", MDNS_RETRY_SECONDS)
            self._mdns_retry = asyncio.get_running_loop().create_task(self._register_mdns_later())
            return

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

    async def _register_mdns_later(self) -> None:
        while find_local_ipv4() is None:
            await asyncio.sleep(MDNS_RETRY_SECONDS)
        await self._register_mdns()
        if self._mdns_retry is asyncio.current_task():
            self._mdns_retry = None

    async def stop(self) -> None:
        retry, self._mdns_retry = self._mdns_retry, None
        if retry is not None and not retry.done():
            # cleanup() may call stop() from another event loop; Task.cancel is not thread-safe.
            retry_loop = retry.get_loop()
            if retry_loop is asyncio.get_running_loop():
                retry.cancel()
            elif not retry_loop.is_closed():
                retry_loop.call_soon_threadsafe(retry.cancel)
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
            self._dispatch(self._protocol.wakeup)
        else:
            _LOGGER.warning("Wake word detected but HA not connected — ignoring")
            if self._animation_server:
                self._animation_server.show_error("Brak połączenia z Home Assistant", duration=3.0)

    def start_conversation(self) -> None:
        """Trigger pipeline run from hotkey / tray menu."""
        if self._protocol:
            self._dispatch(self._protocol.start_conversation)
        else:
            _LOGGER.warning("Voice trigger but HA not connected")

    def toggle_conversation(self) -> None:
        if self.is_connected:
            self._dispatch(self._protocol.toggle_conversation)

    def _dispatch(self, callback) -> None:
        loop = self._protocol._loop
        if loop is not None:
            if not loop.is_closed():
                loop.call_soon_threadsafe(callback)
        else:
            callback()

    def stop_timer(self) -> None:
        """Stop looping timer sound."""
        if self._protocol:
            self._protocol.stop_timer()

    @property
    def is_connected(self) -> bool:
        return self._protocol is not None and self._protocol._transport is not None

    @property
    def can_interrupt_response(self) -> bool:
        return self.is_connected and self._protocol.can_interrupt_response

    @property
    def is_streaming_audio(self) -> bool:
        return self._protocol is not None and self._protocol.is_streaming_audio
