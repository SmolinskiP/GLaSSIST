"""Settings controls, migration, validation and persistence without real devices."""
import asyncio
from collections import defaultdict
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from flet_settings import FletSettingsApp
from multi_room import configured_room_entries, rooms_enabled, validate_rooms
from room_settings import RoomSettings


ROOM = dict(id='salon', name='Salon', input_device=1, output_device=2, port=6053)


def editor(entries=None, enabled=False):
    with patch('room_settings.configured_room_entries', return_value=entries or []), \
         patch('room_settings.rooms_enabled', return_value=enabled):
        return RoomSettings(Mock())


def test_add_edit_remove_reorder_and_stable_identity():
    ui = editor([ROOM], True)
    ui.rows[0]['name'].value = 'Living room'
    ui.add_room()
    row = ui.rows[1]
    assert row['port'].value == '6054'
    row['name'].value = 'Kitchen'
    row['input_device'].value = '3'
    row['output_device'].value = '4'
    ui.move_first(row)
    settings = ui.settings(8765)
    entries = json.loads(settings['HA_ROOMS'])
    assert entries[0]['name'] == 'Kitchen'
    assert entries[1]['id'] == 'salon'
    assert entries[1]['name'] == 'Living room'
    validate_rooms(entries)
    ui.remove(row)
    assert len(ui.rows) == 1


def test_disable_retains_rooms_and_reenable_loads_them():
    ui = editor([ROOM], True)
    ui.enabled.value = False
    settings = ui.settings()
    with patch('utils.get_env', side_effect=lambda key, default=None: settings.get(key, default)):
        assert not rooms_enabled()
        assert configured_room_entries() == [ROOM]
        settings['HA_ROOMS_ENABLED'] = 'true'
        assert rooms_enabled()


@pytest.mark.parametrize('field,value,match', [
    ('name', '', 'name'), ('input_device', None, 'select'),
    ('port', '8765', 'animation'), ('port', '99999', 'port')])
def test_invalid_form_is_rejected(field, value, match):
    ui = editor([ROOM], True)
    ui.rows[0][field].value = value
    with pytest.raises(ValueError, match=match):
        ui.settings(8765)


def test_duplicate_microphone_is_rejected():
    ui = editor([ROOM, dict(ROOM, id='kitchen', port=6054, input_device=3)], True)
    ui.rows[1]['input_device'].value = '1'
    with pytest.raises(ValueError, match='Duplicate room input_device'):
        ui.settings()


def test_missing_devices_remain_visible_and_selected():
    ui = editor([ROOM], True)
    field = ui.rows[0]['input_device']
    assert field.value == '1'
    assert 'Unavailable' in field.options[0].text


def test_device_refresh_does_not_open_a_microphone():
    ui = editor([ROOM])
    with patch('pyaudio.PyAudio') as audio, \
         patch('utils.get_available_output_devices', return_value=[{'index': 2, 'name': 'USB speaker'}]):
        audio.return_value.get_device_count.return_value = 2
        audio.return_value.get_device_info_by_index.side_effect = [
            {'maxInputChannels': 0}, {'maxInputChannels': 1, 'name': 'USB mic'}]
        asyncio.run(ui.refresh_devices())
        audio.return_value.open.assert_not_called()
        audio.return_value.terminate.assert_called_once()
    assert ui.rows[0]['input_device'].options[0].text == 'USB mic (1)'
    assert ui.rows[0]['output_device'].options[0].text == 'USB speaker (2)'


def test_migrate_legacy_file_and_save_with_other_settings(tmp_path):
    path = tmp_path / 'rooms.json'
    path.write_text(json.dumps([ROOM]))
    env = tmp_path / '.env'
    legacy = {'HA_ROOMS_CONFIG': str(path)}
    with patch('utils.get_env', side_effect=lambda key, default=None: legacy.get(key, default)):
        ui = RoomSettings(Mock())
    assert ui.enabled.value
    settings = defaultdict(str, CONNECTION_MODE='esphome', **ui.settings())
    with patch('flet_settings.platform_utils.get_env_file_path', return_value=env):
        assert FletSettingsApp._save_env_file(None, settings)['success']
    saved = dict(line.split('=', 1) for line in env.read_text(encoding='utf-8').splitlines()
                 if line and not line.startswith('#'))
    assert saved['HA_ROOMS_CONFIG'] == ''
    with patch('utils.get_env', side_effect=lambda key, default=None: saved.get(key, default)):
        assert rooms_enabled()
        assert configured_room_entries() == [ROOM]
    assert path.exists()  # Import does not destroy the original file.


def test_failed_save_keeps_previous_settings(tmp_path):
    env = tmp_path / '.env'
    env.write_text('previous settings')
    with patch('flet_settings.platform_utils.get_env_file_path', return_value=env), \
         patch('flet_settings.os.replace', side_effect=OSError('test failure')):
        result = FletSettingsApp._save_env_file(None, defaultdict(str, HA_ROOMS='[]', HA_ROOMS_ENABLED='false'))
    assert not result['success']
    assert env.read_text() == 'previous settings'
    assert list(tmp_path.iterdir()) == [env]


def test_corrupt_configuration_cannot_be_silently_overwritten():
    with patch('room_settings.configured_room_entries', side_effect=ValueError('bad JSON')), \
         patch('room_settings.rooms_enabled', return_value=True):
        ui = RoomSettings(Mock())
    with pytest.raises(ValueError, match='Reset'):
        ui.settings()
    ui.reset()
    ui.enabled.value = False
    assert ui.settings()['HA_ROOMS'] == '[]'


def test_rooms_tab_enables_required_settings():
    import flet as ft
    app = FletSettingsApp()
    app.page = Mock()
    app.connection_mode_dropdown = ft.Dropdown(value='websocket')
    app.wake_word_enabled = ft.Switch(value=False)
    with patch('room_settings.configured_room_entries', return_value=[]), \
         patch('room_settings.rooms_enabled', return_value=False), \
         patch.object(RoomSettings, 'refresh_devices', new_callable=AsyncMock):
        content = asyncio.run(app._create_rooms_tab())
    assert content is app.room_settings.content
    app.room_settings.enabled.value = True
    app.room_settings.enabled.on_change(None)
    assert app.connection_mode_dropdown.value == 'esphome'
    assert app.wake_word_enabled.value
