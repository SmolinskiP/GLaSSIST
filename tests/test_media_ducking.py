"""Tests for media player volume ducking in ESPHome mode."""
import os
from unittest.mock import AsyncMock, Mock, patch

import pytest

import media_ducking
from aioesphomeapi.model import VoiceAssistantEventType as EventType
from aioesphomeapi.api_pb2 import VoiceAssistantRequest
from satellite_protocol import VoiceSatelliteProtocol


@pytest.fixture
def client():
    client = Mock()
    client.connect = AsyncMock(return_value=True)
    client.close = AsyncMock()
    client.get_multiple_volumes = AsyncMock(return_value={'media_player.tv': 0.8})
    client.set_multiple_volumes = AsyncMock(return_value={'media_player.tv': True})
    with patch('client.HomeAssistantClient', return_value=client):
        yield client


@pytest.fixture
def ducker():
    ducker = media_ducking.MediaPlayerDucker()
    ducker._executor = Mock(submit=lambda fn, *args: fn(*args))
    return ducker


ENV = {'HA_MEDIA_PLAYER_ENTITIES': 'media_player.tv, media_player.off',
       'HA_MEDIA_PLAYER_TARGET_VOLUME': '0.2', 'HA_TOKEN': 'token'}


def test_duck_then_restore(client, ducker):
    with patch.dict(os.environ, ENV):
        ducker.duck()
        ducker.duck()
        client.get_multiple_volumes.assert_awaited_once_with(['media_player.tv', 'media_player.off'])
        client.set_multiple_volumes.assert_awaited_once_with({'media_player.tv': 0.2})

        ducker.restore()
        ducker.restore()
    client.set_multiple_volumes.assert_awaited_with({'media_player.tv': 0.8})
    assert client.set_multiple_volumes.await_count == 2
    assert client.close.await_count == 2


def test_requires_token(client, ducker):
    with patch.dict(os.environ, {**ENV, 'HA_TOKEN': ''}):
        ducker.duck()
        ducker.restore()
    client.connect.assert_not_called()


def test_no_entities_does_nothing(client, ducker):
    with patch.dict(os.environ, {**ENV, 'HA_MEDIA_PLAYER_ENTITIES': ''}):
        ducker.duck()
    client.connect.assert_not_called()


def test_failed_connection_is_contained(client, ducker):
    client.connect.side_effect = OSError('unreachable')
    with patch.dict(os.environ, ENV):
        ducker.duck()
        ducker.restore()
    client.set_multiple_volumes.assert_not_called()


def make_protocol():
    protocol = VoiceSatelliteProtocol(device_name='glasssist', mac_address='02:00:00:00:00:01',
                                      animation_server=Mock(), on_tts_url=Mock(),
                                      on_tts_finished=Mock(), feedback_enabled=False)
    protocol.send_messages = Mock()
    return protocol


@patch('satellite_protocol.media_ducker')
def test_satellite_ducks_for_the_whole_conversation(ducker):
    protocol = make_protocol()
    protocol.wakeup()
    ducker.duck.assert_called_once()

    protocol._continue_conversation = True
    protocol._tts_finished_on_loop()
    ducker.restore.assert_not_called()

    protocol._continue_conversation = False
    protocol._tts_text = ''
    protocol._tts_finished_on_loop()
    ducker.restore.assert_called_once()


@patch('satellite_protocol.media_ducker')
def test_satellite_restores_on_disconnect(ducker):
    protocol = make_protocol()
    protocol.wakeup()
    protocol.connection_lost(None)
    ducker.restore.assert_called_once()


@pytest.mark.parametrize(
    "setting, text, calls_after_vad, calls_after_stt",
    [("stt_vad_end", "hello", 1, 1), ("stt_end", " hello ", 0, 1), ("stt_end", "  ", 0, 0)],
)
def test_processing_sound_can_wait_for_recognized_speech(setting, text, calls_after_vad, calls_after_stt):
    protocol = make_protocol()
    protocol._feedback_enabled = True
    with patch.dict(os.environ, {"HA_PROCESSING_SOUND_START": setting}), \
         patch("utils._read_from_env_file", return_value=None), \
         patch("satellite_protocol.utils.processing_sound_loop") as sound, \
         patch("satellite_protocol.media_ducker"):
        protocol._handle_voice_event(EventType.VOICE_ASSISTANT_RUN_START, {})
        protocol._handle_voice_event(EventType.VOICE_ASSISTANT_STT_VAD_END, {})
        assert not protocol.is_streaming_audio
        assert sound.start.call_count == calls_after_vad
        protocol._handle_voice_event(EventType.VOICE_ASSISTANT_STT_END, {"text": text})
        assert sound.start.call_count == calls_after_stt


def test_hotkey_cancels_pipeline_and_discards_late_events():
    protocol = make_protocol()
    with patch("satellite_protocol.media_ducker"), patch("utils.processing_sound_loop"):
        protocol.toggle_conversation()
        assert protocol.is_streaming_audio
        protocol.toggle_conversation()
        assert any(isinstance(msg, VoiceAssistantRequest) and not msg.start
                   for call in protocol.send_messages.call_args_list for msg in call.args[0])
        protocol._handle_voice_event(EventType.VOICE_ASSISTANT_TTS_END, {"url": "http://ha/old.wav"})
        protocol._handle_voice_event(EventType.VOICE_ASSISTANT_RUN_END, {})
        protocol._on_tts_url.assert_not_called()
        assert not protocol.is_streaming_audio
        protocol.toggle_conversation()
        protocol._handle_voice_event(EventType.VOICE_ASSISTANT_RUN_START, {})
        assert protocol.is_streaming_audio


@pytest.mark.parametrize("interrupt", [False, True])
def test_wake_word_can_interrupt_streaming_reply(interrupt):
    protocol = make_protocol()
    with patch("satellite_protocol.media_ducker"), patch("utils.processing_sound_loop"), \
         patch("utils.get_env_bool", return_value=interrupt):
        protocol._handle_voice_event(EventType.VOICE_ASSISTANT_RUN_START, {"url": "http://ha/stream.wav"})
        protocol._handle_voice_event(EventType.VOICE_ASSISTANT_INTENT_PROGRESS, {"tts_start_streaming": "1"})
        protocol._handle_voice_event(EventType.VOICE_ASSISTANT_TTS_END, {"url": "http://ha/stream.wav"})
        protocol._on_tts_url.assert_called_once()
        playback = protocol._on_tts_url.call_args.kwargs
        assert playback["streaming"]
        protocol.send_messages.reset_mock()
        protocol.wakeup()
        assert playback["cancel_event"].is_set() is interrupt
        if interrupt:
            requests = [msg for call in protocol.send_messages.call_args_list for msg in call.args[0]
                        if isinstance(msg, VoiceAssistantRequest)]
            assert [msg.start for msg in requests] == [False, True]
            protocol._on_tts_finished.reset_mock()
            playback["done_callback"]()
            protocol._on_tts_finished.assert_not_called()
        else:
            protocol.send_messages.assert_not_called()
