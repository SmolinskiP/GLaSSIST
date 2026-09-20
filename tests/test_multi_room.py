"""Room routing and reservation tests without opening physical audio devices."""
import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest

from multi_room import ConversationGate, MultiRoomManager, RoomConfig, load_rooms, room_protocol_factory
from aioesphomeapi.model import VoiceAssistantEventType as Event


def room(**changes):
    return dict(id='salon', name='Salon', input_device=1, output_device=2, port=6053, **changes)


def test_configuration_identity_and_validation(tmp_path):
    config = tmp_path / 'rooms.json'
    entries = [room(), dict(id='kuchnia', name='Kuchnia', input_device=3, output_device=4, port=6054)]
    config.write_text(json.dumps(entries))
    first = load_rooms(config)
    config.write_text(json.dumps(entries[::-1]))
    assert first[0].mac == load_rooms(config)[1].mac
    assert first[0].mac != first[1].mac
    assert int(first[0].mac[:2], 16) & 3 == 2
    for key, value in [('port', 6053), ('id', 'salon'), ('input_device', 1)]:
        broken = [entries[0], {**entries[1], key: value}]
        config.write_text(json.dumps(broken))
        with pytest.raises(ValueError, match='Duplicate'):
            load_rooms(config)


@pytest.mark.parametrize('value', [[], {}, [{'id': 'a'}], [dict(room(), port=True)],
                                        [dict(room(), output_device=-1)], [dict(room(), pipeline_id='x')]])
def test_bad_configuration_fails_closed(tmp_path, value):
    path = tmp_path / 'rooms.json'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        load_rooms(path)


def make_protocol(gate):
    protocol = room_protocol_factory(gate)(device_name='room', mac_address='02:00:00:00:00:01',
        animation_server=Mock(), on_tts_url=Mock(), on_tts_finished=Mock())
    protocol._loop = asyncio.get_running_loop()
    protocol._transport = Mock()
    protocol.send_messages = Mock()
    return protocol


def test_two_microphones_only_start_one_pipeline_and_disconnect_releases():
    async def scenario():
        gate = ConversationGate()
        a, b = make_protocol(gate), make_protocol(gate)
        with patch('satellite_protocol.utils.play_feedback_sound') as feedback:
            a.wakeup()
            b.wakeup()
            assert a.send_messages.call_count == 1
            b.send_messages.assert_not_called()
            feedback.assert_not_called()
        a.connection_lost(None)
        assert gate.owner is None
        b.wakeup()
        b.send_messages.assert_not_called()  # Echo cooldown.
        gate.until = 0
        b.wakeup()
        assert gate.owner is b
        b.connection_lost(None)
    asyncio.run(scenario())


@pytest.mark.parametrize('playback_first', [True, False])
def test_reservation_lasts_through_run_end_and_playback(playback_first):
    async def scenario():
        gate = ConversationGate()
        a, b = make_protocol(gate), make_protocol(gate)
        a.wakeup()
        a._tts_played = True
        if playback_first:
            a._tts_finished_on_loop()
            assert a._playback_finished_early
        a._handle_voice_event(Event.VOICE_ASSISTANT_RUN_END, {})
        if not playback_first:
            assert gate.owner is a
            a._tts_finished_on_loop()
        b.wakeup()
        b.send_messages.assert_not_called()
        a._release_block()
        assert gate.owner is None
        a.connection_lost(None)
    asyncio.run(scenario())


def test_pipeline_error_and_playback_still_block_other_room():
    async def scenario():
        gate = ConversationGate()
        a, b = make_protocol(gate), make_protocol(gate)
        a.wakeup()
        gate.playbacks = 1
        a._handle_voice_event(Event.VOICE_ASSISTANT_ERROR, {'code': 'test'})
        gate.until = 0
        b.wakeup()
        b.send_messages.assert_not_called()
        gate.playbacks = 0
        b.wakeup()
        assert gate.owner is b
        a._tts_finished_on_loop()  # Late old callback cannot release the new room.
        assert gate.owner is b
        b.connection_lost(None)
    asyncio.run(scenario())


def test_hotkey_waits_for_playback_and_cooldown_in_same_room():
    async def scenario():
        gate = ConversationGate()
        protocol = make_protocol(gate)
        protocol.start_conversation()
        protocol._tts_played = True
        gate.playbacks = 1
        protocol._handle_voice_event(Event.VOICE_ASSISTANT_RUN_END, {})
        protocol.send_messages.reset_mock()

        protocol.start_conversation()
        protocol.send_messages.assert_not_called()
        assert not protocol.pipeline_active

        gate.playbacks = 0
        protocol._tts_finished_on_loop()
        assert not protocol._playback_finished_early
        protocol.send_messages.reset_mock()
        protocol.start_conversation()
        protocol.send_messages.assert_not_called()
        protocol._release_block()
        protocol.start_conversation()
        protocol.send_messages.assert_not_called()

        gate.until = 0
        protocol.start_conversation()
        assert protocol.pipeline_active
        protocol.send_messages.assert_called_once()
        protocol.connection_lost(None)
    asyncio.run(scenario())


def test_tts_routes_to_source_speaker_even_on_failure():
    async def scenario():
        config = RoomConfig(**room())
        manager = MultiRoomManager([config], Mock())
        manager._loop = asyncio.get_running_loop()
        callback = Mock()
        with patch('utils.play_audio_from_url', return_value=False) as play:
            manager._play(config, 'http://ha/audio.wav', callback)
            assert not manager.gate.idle
            await asyncio.gather(*manager._play_tasks)
            assert play.call_args.args[-1] == config.output_device
            callback.assert_called_once()
            assert manager.gate.playbacks == 0
    asyncio.run(scenario())


def test_explicit_speaker_uses_independent_stream(tmp_path):
    import utils
    path = str(tmp_path / 'audio.wav')
    with patch('utils.sf.read', return_value=(np.zeros(160, dtype=np.float32), 16000)), \
         patch('utils.sd.OutputStream') as output, patch('utils.sd.play') as global_play, \
         patch('utils.get_output_sample_rate', return_value=None), \
         patch('utils.get_output_device_index') as default_device:
        assert utils.play_audio_from_url(path, '', output_device_index=7)
        assert output.call_args.kwargs['device'] == 7
        output.return_value.__enter__.return_value.write.assert_called_once()
        global_play.assert_not_called()
        default_device.assert_not_called()


def test_default_playback_retains_existing_device_selection(tmp_path):
    import utils
    with patch('utils.sf.read', return_value=(np.zeros(160), 16000)), \
         patch('utils.sd.OutputStream') as output, patch('utils.sd.play') as play, \
         patch('utils.sd.wait'), patch('utils.get_output_sample_rate', return_value=None), \
         patch('utils.get_output_device_index', return_value=5):
        assert utils.play_audio_from_url(str(tmp_path / 'audio.wav'), '')
        assert play.call_args.kwargs['device'] == 5
        output.assert_not_called()


def test_startup_failure_closes_opened_devices():
    async def scenario():
        manager = MultiRoomManager([RoomConfig(**room())], Mock())
        with patch('pyaudio.PyAudio') as audio, patch('sounddevice.check_output_settings'), \
             patch('wake_word_detector.WakeWordDetector') as detector:
            audio.return_value.get_device_info_by_index.return_value = {'maxInputChannels': 1}
            detector.return_value.enabled = False
            with pytest.raises(ValueError, match='wake word'):
                await manager._serve()
            audio.return_value.open.return_value.close.assert_called_once()
            audio.return_value.terminate.assert_called_once()
    asyncio.run(scenario())


def test_capture_data_only_reaches_active_satellite():
    async def scenario():
        gate = ConversationGate()
        a, b = make_protocol(gate), make_protocol(gate)
        a.wakeup()
        a.send_messages.reset_mock()
        a.handle_audio(b'room-a')
        b.handle_audio(b'room-b')
        assert a.send_messages.call_args.args[0][0].data == b'room-a'
        b.send_messages.assert_not_called()
        a.connection_lost(None)
    asyncio.run(scenario())


def test_follow_up_keeps_room_reserved():
    async def scenario():
        gate = ConversationGate()
        a, b = make_protocol(gate), make_protocol(gate)
        a.wakeup()
        a._continue_conversation = True
        a._tts_played = True
        a._handle_voice_event(Event.VOICE_ASSISTANT_RUN_END, {})
        a._tts_finished_on_loop()
        assert gate.owner is a
        assert a.pipeline_active
        b.wakeup()
        b.send_messages.assert_not_called()
        a.connection_lost(None)
    asyncio.run(scenario())


@pytest.mark.parametrize('output_rate', [None, 48000])
def test_room_runtime_creates_distinct_devices_and_closes_them(output_rate):
    async def scenario():
        rooms = [RoomConfig(**room()), RoomConfig('kitchen', 'Kitchen', 3, 4, 6054)]
        manager = MultiRoomManager(rooms, Mock())
        with patch('pyaudio.PyAudio') as audio, patch('sounddevice.check_output_settings') as check_output, \
             patch('utils.get_output_sample_rate', return_value=output_rate), \
             patch('wake_word_detector.WakeWordDetector'), \
             patch('satellite_protocol.SatelliteServer') as server, \
             patch.object(manager, '_capture'):
            audio.return_value.get_device_info_by_index.return_value = {'maxInputChannels': 1}
            server.return_value.start = AsyncMock()
            server.return_value.stop = AsyncMock()
            task = asyncio.create_task(manager._serve())
            await asyncio.sleep(0)
            assert manager._ready.is_set()
            assert [c.kwargs['samplerate'] for c in check_output.call_args_list] == [output_rate, output_rate]
            calls = server.call_args_list
            assert [c.kwargs['port'] for c in calls] == [6053, 6054]
            assert calls[0].kwargs['mac_address'] != calls[1].kwargs['mac_address']
            with patch.object(manager, '_play') as play:
                calls[0].kwargs['on_tts_url']('first')
                calls[1].kwargs['on_tts_url']('second')
                assert [c.args[0].output_device for c in play.call_args_list] == [2, 4]
            manager._stop.set()
            await task
            assert server.return_value.stop.await_count == 2
            assert audio.return_value.open.return_value.close.call_count == 2
            audio.return_value.terminate.assert_called_once()
    asyncio.run(scenario())


def test_app_keeps_single_room_initialization_and_routes_room_hotkey():
    import main
    def config(key, default=None, as_type=str):
        return {'HA_ROOMS_CONFIG': 'rooms.json', 'CONNECTION_MODE': 'esphome'}.get(key, default)
    with patch('main.utils.get_env', side_effect=config), patch('main.WakeWordDetector') as detector:
        app = main.HAAssistApp()
        detector.assert_not_called()
        app.multi_room_manager = Mock()
        app.on_voice_command_trigger()
        app.multi_room_manager.start_conversation.assert_called_once()
    with patch('main.utils.get_env', side_effect=lambda key, default=None, as_type=str: default), \
         patch('main.WakeWordDetector') as detector:
        app = main.HAAssistApp()
        detector.assert_called_once()
        assert not app.multi_room_enabled


def test_pause_blocks_queued_wake_words_but_keeps_current_audio_flow():
    async def scenario():
        manager = MultiRoomManager([RoomConfig(**room())], Mock())
        server = Mock(is_connected=True)
        assert await manager._feed(server, b'audio')
        manager.toggle_pause()
        assert not await manager._feed(server, b'more audio')
        manager._wakeup(server)
        server.wakeup.assert_not_called()
        server.handle_audio.assert_called_with(b'more audio')
        manager.toggle_pause()
        manager._wakeup(server)
        server.wakeup.assert_called_once()
    asyncio.run(scenario())


def test_settings_save_preserves_room_configuration(tmp_path):
    from collections import defaultdict
    from flet_settings import FletSettingsApp
    env = tmp_path / '.env'
    settings = defaultdict(str, CONNECTION_MODE='esphome')
    with patch('flet_settings.platform_utils.get_env_file_path', return_value=env), \
         patch('flet_settings.utils.get_env', return_value='rooms.json'):
        result = FletSettingsApp._save_env_file(None, settings)
    assert result['success']
    assert 'HA_ROOMS_CONFIG=rooms.json\n' in env.read_text(encoding='utf-8')
