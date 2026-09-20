"""Exercise the Save Settings handler through validation, disk write and dialog."""
import asyncio
from contextlib import nullcontext
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import flet as ft
import pytest

from flet_settings import FletSettingsApp
from room_settings import RoomSettings


def make_app():
    app = FletSettingsApp()
    app.page = Mock(spec=ft.Page)
    app.animation_port_field = ft.TextField(value='8765')
    with patch('room_settings.configured_room_entries', return_value=[]), \
         patch('room_settings.rooms_enabled', return_value=False):
        app.room_settings = RoomSettings(app.page)
    app.room_settings.enabled.value = True
    return app


def test_invalid_rooms_show_visible_dialog_and_do_not_write():
    app = make_app()
    app.room_settings.add_room()
    with patch.object(app, '_save_env_file') as save:
        asyncio.run(app._save_settings_async(None))
    save.assert_not_called()
    dialog = app.page.open.call_args.args[0]
    assert isinstance(dialog, ft.AlertDialog)
    assert dialog.title.value == 'Validation Error'
    assert 'select a microphone and speaker' in dialog.content.value


@pytest.mark.parametrize('disk_failure', [False, True])
def test_save_button_writes_rooms_or_reports_disk_error(tmp_path, disk_failure):
    app = make_app()
    room = {'id': 'salon', 'name': 'Pokój', 'input_device': 1, 'output_device': 2, 'port': 6053}
    app.room_settings.add_room(room)
    text_fields = {
        'connection_mode_dropdown': 'websocket', 'host_field': '', 'token_field': '',
        'microphone_dropdown': '-1', 'output_device_dropdown': '-1', 'pipeline_dropdown': '',
        'hotkey_dropdown': 'ctrl+shift+h', 'activation_sound_dropdown': 'activation.wav',
        'deactivation_sound_dropdown': 'deactivation.wav', 'processing_sound_dropdown': 'processing.wav',
        'sample_rate_dropdown': '16000', 'output_sample_rate_dropdown': '-1',
        'frame_duration_dropdown': '30', 'media_player_entities_field': '',
        'timer_sound_field': '', 'device_name_field': 'GLaSSIST', 'esphome_port_field': '6053',
    }
    for name, value in text_fields.items():
        setattr(app, name, SimpleNamespace(value=value))
    for name in ('wake_word_enabled', 'sound_feedback_switch', 'processing_sound_switch',
                 'debug_switch', 'animations_switch', 'response_text_switch',
                 'noise_suppression_switch', 'continue_on_question_switch'):
        setattr(app, name, ft.Switch(value=False))
    for name, value in {'silence_slider': 0.8, 'vad_slider': 3, 'wake_threshold_slider': 0.5,
                        'vad_threshold_slider': 0.3, 'target_volume_slider': 0.3,
                        'conversation_timeout_slider': 300}.items():
        setattr(app, name, SimpleNamespace(value=value))
    app.selected_models_column = ft.Column()
    asyncio.run(app._populate_wake_word_models('hey_jarvis'))
    env = tmp_path / '.env'
    disk = patch('flet_settings.os.replace', side_effect=OSError('disk failure')) if disk_failure else nullcontext()
    with patch('flet_settings.platform_utils.get_env_file_path', return_value=env), \
         patch.dict('sys.modules', {'openwakeword': Mock()}), disk:
        asyncio.run(app._save_settings_async(None))
    if disk_failure:
        assert not env.exists()
        dialog = app.page.open.call_args.args[0]
        assert dialog.title.value == 'Save Error'
        assert 'disk failure' in dialog.content.value
        return
    values = dict(line.split('=', 1) for line in env.read_text(encoding='utf-8').splitlines()
                  if line and not line.startswith('#'))
    assert values['CONNECTION_MODE'] == 'esphome'
    assert values['HA_ROOMS_ENABLED'] == 'true'
    assert values['HA_WAKE_WORD_ENABLED'] == 'true'
    assert json.loads(values['HA_ROOMS']) == [room]
    dialog = app.page.open.call_args.args[0]
    assert dialog.title.value == 'Settings Saved'


def test_dialog_closes_and_runs_callback():
    # Test the same reporting path used by validation and failed writes.
    app = make_app()
    asyncio.run(app._show_dialog('Save Error', 'Cannot write settings'))
    dialog = app.page.open.call_args.args[0]
    assert dialog.content.value == 'Cannot write settings'
    callback = Mock()
    app._close_dialog(dialog, callback)
    app.page.close.assert_called_once_with(dialog)
    callback.assert_called_once()
