"""Tests for the translation layer (i18n.py + locales/*.json)."""
import glob
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import i18n  # noqa: E402


LOCALES_DIR = os.path.join(os.path.dirname(i18n.__file__), 'locales')


def _load(code):
    with open(os.path.join(LOCALES_DIR, f'{code}.json'), encoding='utf-8') as f:
        return json.load(f)


def setup_function(_):
    i18n.set_language('en')


def teardown_function(_):
    i18n.set_language('en')


def test_english_is_untouched():
    i18n.set_language('en')
    assert i18n.t('Save Settings') == 'Save Settings'


def test_exact_and_prefix_translation():
    i18n.set_language('pt_BR')
    assert i18n.t('Save Settings') == 'Salvar configurações'
    assert i18n.t('Current: 0.50') == 'Atual: 0.50'
    assert i18n.t('Texto sem tradução') == 'Texto sem tradução'


def test_pattern_with_values():
    i18n.set_language('pt_BR')
    assert (i18n.t('11 microphones and 10 speakers found.')
            == '11 microfones e 10 alto-falantes encontrados.')


def test_polish_translation():
    i18n.set_language('pl')
    assert i18n.t('Save Settings') == 'Zapisz ustawienia'
    assert i18n.t('Current: 0.50') == 'Obecnie: 0.50'
    assert i18n.t('Room 2: select a microphone and speaker and enter a valid port.') == (
        'Pokój 2: wybierz mikrofon i głośnik oraz podaj poprawny port.')


def test_language_code_normalization():
    assert i18n.normalize('pt-BR') == 'pt_BR'
    assert i18n.normalize('pt') == 'pt_BR'
    assert i18n.normalize('pl') == 'pl'
    assert i18n.normalize('pl_PL') == 'pl'
    assert i18n.normalize('PL-pl') == 'pl'
    assert i18n.normalize('en_US') == 'en'
    assert i18n.normalize('xx') == 'en'
    assert i18n.normalize(None) == 'en'


def test_every_language_has_a_locale_file():
    files = {os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(LOCALES_DIR, '*.json'))}
    assert files == set(i18n.LANGUAGES) - {'en'}


@pytest.mark.parametrize('code', sorted(set(i18n.LANGUAGES) - {'en'}))
def test_every_translation_keeps_placeholders(code):
    for english, translated in _load(code).items():
        assert translated.strip(), english
        for token in ('{value}', '{}', '%s'):
            assert english.count(token) == translated.count(token), english


def test_locales_cover_the_same_texts():
    codes = sorted(set(i18n.LANGUAGES) - {'en'})
    keys = {code: set(_load(code)) for code in codes}
    for code in codes[1:]:
        assert keys[code] == keys[codes[0]], code


def test_init_from_env_reads_env_file():
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr('utils._read_from_env_file', lambda key: 'pl' if key == 'HA_LANGUAGE' else None)
        mp.setenv('HA_LANGUAGE', 'pt_BR')
        assert i18n.init_from_env() == 'pl'


def test_flet_controls_are_translated(monkeypatch):
    import flet as ft
    for name in ('Text', 'TextField', 'ElevatedButton', 'FilledTonalButton', 'Tab', 'Dropdown',
                 'Switch', 'TextButton', 'OutlinedButton', 'FilledButton', 'Checkbox', 'Slider',
                 'IconButton', 'Chip', 'ListTile', 'Radio', 'FloatingActionButton'):
        monkeypatch.setattr(ft, name, getattr(ft, name))
    monkeypatch.setattr(ft.dropdown, 'Option', ft.dropdown.Option)
    monkeypatch.setattr(i18n, '_patched', False)
    i18n.set_language('pt_BR')
    i18n.patch_flet(ft)
    assert ft.Text('Save Settings').value == 'Salvar configurações'
    assert ft.TextField(label='Device Name').label == 'Nome do dispositivo'
    assert ft.ElevatedButton('Test Connection').text == 'Testar conexão'
    text = ft.Text('x')
    text.value = 'Current: 3'
    assert text.value == 'Atual: 3'
    # Option(key, text): key must stay, label is translated
    option = ft.dropdown.Option('websocket', 'WebSocket — GLaSSIST connects to HA')
    assert option.key == 'websocket'
    assert option.text == 'WebSocket — o GLaSSIST se conecta ao HA'
    assert ft.FilledTonalButton('Test Connection').text == 'Testar conexão'
