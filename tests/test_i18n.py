"""Tests for the pt_BR translation layer (i18n.py + locales/pt_BR.json)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import i18n  # noqa: E402


def setup_function(_):
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


def test_language_code_normalization():
    assert i18n.normalize('pt-BR') == 'pt_BR'
    assert i18n.normalize('pt') == 'pt_BR'
    assert i18n.normalize('xx') == 'en'
    assert i18n.normalize(None) == 'en'


def test_every_translation_keeps_placeholders():
    path = os.path.join(os.path.dirname(i18n.__file__), 'locales', 'pt_BR.json')
    with open(path, encoding='utf-8') as f:
        table = json.load(f)
    for english, translated in table.items():
        assert translated.strip(), english
        for token in ('{value}', '{}', '%s'):
            assert english.count(token) == translated.count(token), english


def test_flet_controls_are_translated():
    import flet as ft
    i18n.set_language('pt_BR')
    i18n._patched = False  # allow re-patching inside the test process
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
