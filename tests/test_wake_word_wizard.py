"""Headless tests of the wake word wizard UI (no window is opened)."""
import os
import sys
from unittest.mock import Mock

import flet as ft
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import i18n  # noqa: E402
import wake_word_wizard as W  # noqa: E402


@pytest.fixture
def wizard(tmp_path):
    i18n.set_language('pt_BR')
    i18n._patched = False
    i18n.patch_flet(ft)
    w = W.WakeWordWizard()
    w.root = str(tmp_path / 'trainer')
    page = Mock(spec=ft.Page)
    w.main(page)
    yield w
    i18n.set_language('en')


def _texts(control, out=None):
    out = [] if out is None else out
    for attr in ('value', 'text', 'label'):
        v = getattr(control, attr, None)
        if isinstance(v, str):
            out.append(v)
    for attr in ('content', 'controls'):
        child = getattr(control, attr, None)
        if isinstance(child, list):
            for c in child:
                _texts(c, out)
        elif child is not None and not isinstance(child, str):
            _texts(child, out)
    return out


def test_first_step_is_shown_in_the_chosen_language(wizard):
    assert wizard.step == 0
    assert wizard.title.value == 'Idioma e palavra'
    assert not wizard.back_btn.visible and wizard.next_btn.visible
    assert any('Idioma da palavra' in s for s in _texts(wizard.body))


def test_word_validation(wizard):
    wizard.lang_dd.value = 'pt'
    wizard.word_tf.value = 'ab'
    assert wizard._apply_welcome() is False
    assert 'pelo menos 4 letras' in wizard.welcome_msg.value
    wizard.word_tf.value = 'x' * 40
    assert wizard._apply_welcome() is False
    wizard.word_tf.value = 'Bruninha'
    assert wizard._apply_welcome() is True
    assert wizard.ws.project.model_name == 'bruninha' and wizard.language == 'pt'
    assert os.path.exists(wizard.ws.project_file)


def test_navigation_through_all_steps(wizard):
    wizard.lang_dd.value, wizard.word_tf.value = 'pt', 'Bruninha'
    wizard._next()
    assert wizard.step == 1 and wizard.back_btn.visible
    assert wizard.next_btn.disabled          # tools are not installed in the test folder
    for step in range(2, 6):
        wizard._show(step)
        assert wizard.step == step
    assert not wizard.next_btn.visible        # last step has no "next"
    wizard._back()
    assert wizard.step == 4


def test_recording_step_requires_enough_clips(wizard, tmp_path):
    wizard.lang_dd.value, wizard.word_tf.value = 'pt', 'Bruninha'
    wizard._apply_welcome()
    wizard._show(3)
    assert wizard.next_btn.disabled
    assert 'Ainda falta' in wizard.rec_msg.value
    import numpy as np
    import soundfile as sf
    for folder, n in ((wizard.ws.real_pos, 25), (wizard.ws.real_neg, 30), (wizard.ws.test_pos, 10)):
        for i in range(n):
            sf.write(os.path.join(folder, f'c_{i}.wav'), np.zeros(1600, np.float32), 16000)
    wizard._refresh_recording_status()
    assert not wizard.next_btn.disabled
    assert 'gravações suficientes' in wizard.rec_msg.value


@pytest.mark.parametrize('level,fragment', [('good', 'Bom resultado'), ('poor', 'Ainda não está bom')])
def test_verdict_is_explained(wizard, level, fragment):
    wizard.lang_dd.value, wizard.word_tf.value = 'pt', 'Bruninha'
    assert wizard._apply_welcome()
    wizard._show(4)
    ev = {'verdict': {'level': level, 'reasons': ['50% of normal-speech clips triggered it'] if level == 'poor' else []},
          'test_pos': {'clips': 30, 'above': {'0.5': 29}}, 'hold_real_neg': {'clips': 58, 'above': {'0.5': 2}},
          'ambient': {'windows_above_0_5': 0}}
    wizard._show_verdict(ev)
    shown = ' | '.join(_texts(wizard.verdict_box))
    assert fragment in shown and '29 / 30' in shown and '2 / 58' in shown
    if level == 'poor':
        assert '50% dos trechos de fala normal a ativaram' in shown


def test_add_to_list_uses_install_and_reports(wizard, monkeypatch):
    wizard.lang_dd.value, wizard.word_tf.value = 'pt', 'Bruninha'
    wizard._apply_welcome()
    wizard._show(5)
    calls = []
    monkeypatch.setattr(W.install, 'install_model', lambda *a, **k: calls.append((a, k)) or {'models': ['bruninha']})
    wizard._add(replace=True)
    (args, kwargs), = calls
    assert args[3] == 'bruninha' and kwargs['replace'] is True and kwargs['enable'] is True
    assert 'Adicionado' in wizard.add_msg.value


def test_cli_runner_reports_errors(wizard, monkeypatch):
    wizard.lang_dd.value, wizard.word_tf.value = 'en', 'Jarvis'
    wizard._apply_welcome()
    monkeypatch.setattr(W.env_setup, 'trainer_python', lambda root: sys.executable)
    with pytest.raises(RuntimeError):
        wizard._run_cli(['info', '--workspace', os.path.join(wizard.root, 'does-not-exist-xyz', 'a', 'b')] + ['--bogus'])
