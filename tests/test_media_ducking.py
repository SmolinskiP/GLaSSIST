"""Tests for media player volume ducking in ESPHome mode."""
import os
from unittest.mock import AsyncMock, Mock, patch

import pytest

import media_ducking
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
