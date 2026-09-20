import unicodedata
from unittest.mock import Mock, patch

import pytest

from utils import normalize_audio_device_name, get_available_output_devices


@pytest.mark.parametrize('encoding', ['cp1250', 'cp1252', 'latin1'])
@pytest.mark.parametrize('name', ['Mapowanie dźwięku Microsoft - Input', 'Głośniki (High Definition Audio)'])
def test_repair_windows_mojibake(name, encoding):
    broken = name.encode('utf-8').decode(encoding)
    assert normalize_audio_device_name(broken) == name


@pytest.mark.parametrize('name', ['Głośniki', 'Mikrofon', 'Zażółć gęślą jaźń',
                                  '耳机', 'Микрофон', 'Mikrofon USB', 'Büro Lautsprecher'])
def test_correct_names_remain_intact(name):
    assert normalize_audio_device_name(name) == name
    assert normalize_audio_device_name(name.encode('utf-8')) == name


def test_decomposed_unicode_is_composed():
    assert normalize_audio_device_name(unicodedata.normalize('NFD', 'Głośniki')) == 'Głośniki'


def test_device_lists_repair_names_without_changing_indices():
    from audio import AudioManager
    manager = AudioManager.__new__(AudioManager)
    manager.audio = Mock()
    manager.audio.get_device_count.return_value = 1
    manager.audio.get_device_info_by_index.return_value = {
        'name': 'Mapowanie dźwięku'.encode('utf-8').decode('cp1250'), 'maxInputChannels': 1}
    devices = manager.get_available_microphones()
    assert devices[0]['name'] == 'Mapowanie dźwięku'
    assert devices[0]['index'] == 0
    with patch('utils.sd.query_devices', return_value=[{
            'name': 'Głośniki'.encode('utf-8').decode('cp1250'), 'max_output_channels': 2}]):
        devices = get_available_output_devices()
    assert devices[0]['name'] == 'Głośniki'
    assert devices[0]['index'] == 0
