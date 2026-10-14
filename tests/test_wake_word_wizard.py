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
    for step in range(2, 7):
        wizard._show(step)
        assert wizard.step == step
    assert wizard.next_btn.text == 'Fechar'   # the last step ends with a close button
    wizard._back()
    assert wizard.step == 5 and wizard.title.value == 'Melhorar'


def test_recording_step_requires_enough_clips(wizard, tmp_path):
    wizard.lang_dd.value, wizard.word_tf.value = 'pt', 'Bruninha'
    wizard._apply_welcome()
    wizard._show(3)
    assert wizard.next_btn.disabled
    assert 'Ainda falta' in wizard.rec_msg.value
    import numpy as np
    import soundfile as sf
    for folder, n in ((wizard.ws.real_pos, W.MIN_WORD), (wizard.ws.real_neg, W.MIN_SPEECH),
                      (wizard.ws.test_pos, W.MIN_TEST)):
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
    ev = {'verdict': {'level': level, 'reasons': ['12 of 20 normal-speech clips triggered it'] if level == 'poor' else []},
          'test_pos': {'clips': 30, 'above': {'0.5': 29}}, 'hold_real_neg': {'clips': 58, 'above': {'0.5': 2}},
          'ambient': {'windows_above_0_5': 0}}
    wizard._show_verdict(ev)
    shown = ' | '.join(_texts(wizard.verdict_box))
    assert fragment in shown and '29 / 30' in shown and '2 / 58' in shown
    if level == 'poor':
        assert '12 de 20 trechos de fala normal a ativaram' in shown
        assert 'Melhorar agora (recomendado)' in shown          # the fix is one click away


def _run_threads_inline(monkeypatch):
    """Run the wizard's background threads synchronously so the tests can inspect the final state."""
    class Inline:
        def __init__(self, target, daemon=None): self.target = target
        def start(self): self.target()
    monkeypatch.setattr(W.threading, 'Thread', Inline)


def test_voices_button_hides_while_working_and_returns_on_error(wizard, monkeypatch):
    wizard.lang_dd.value, wizard.word_tf.value = 'pt', 'Bruninha'
    wizard._apply_welcome()
    wizard._show(2)
    _run_threads_inline(monkeypatch)
    seen = {}

    def failing(args, on_progress=None, **kw):
        seen['btn_hidden_during'] = not wizard.voices_btn.visible
        seen['wait_shown'] = wizard.voices_wait.visible
        raise RuntimeError('no internet')

    monkeypatch.setattr(wizard, '_run_cli', failing)
    wizard._generate()
    assert seen == {'btn_hidden_during': True, 'wait_shown': True}
    assert wizard.voices_btn.visible and not wizard.voices_wait.visible       # back so the user can retry
    assert 'no internet' in wizard.voices_status.value and 'tentar de novo' in wizard.voices_status.value


def test_training_checklist_marks_each_stage(wizard, monkeypatch):
    wizard.lang_dd.value, wizard.word_tf.value = 'pt', 'Bruninha'
    wizard._apply_welcome()
    wizard._show(4)
    assert set(wizard.stage_state.values()) == {'pending'}
    _run_threads_inline(monkeypatch)
    snapshots = []

    def fake_cli(args, on_progress=None, on_log=None, on_stage=None):
        if args[0] == 'train':
            for name in ('prepare', 'features', 'train', 'export'):
                on_stage(name, 'start')
                snapshots.append(dict(wizard.stage_state))
                if name == 'train':
                    on_progress(5, 40)
                on_stage(name, 'done')
            return {}
        on_stage('evaluate', 'start'); on_stage('evaluate', 'done')
        return {'verdict': {'level': 'good', 'reasons': []}, 'test_pos': {'clips': 1, 'above': {'0.5': 1}},
                'hold_real_neg': {'clips': 0, 'above': {'0.5': 0}}}

    monkeypatch.setattr(wizard, '_run_cli', fake_cli)
    wizard._train()
    assert snapshots[1]['features'] == 'running' and snapshots[1]['prepare'] == 'done'
    assert snapshots[1]['train'] == 'pending'
    assert set(wizard.stage_state.values()) == {'done'}
    assert wizard.train_btn.visible and not wizard.train_wait.visible


def test_training_failure_marks_the_failed_stage(wizard, monkeypatch):
    wizard.lang_dd.value, wizard.word_tf.value = 'pt', 'Bruninha'
    wizard._apply_welcome()
    wizard._show(4)
    _run_threads_inline(monkeypatch)

    def fake_cli(args, on_progress=None, on_log=None, on_stage=None):
        on_stage('prepare', 'start'); on_stage('prepare', 'done')
        on_stage('features', 'start')
        raise RuntimeError('MemoryError')

    monkeypatch.setattr(wizard, '_run_cli', fake_cli)
    wizard._train()
    assert wizard.stage_state['prepare'] == 'done' and wizard.stage_state['features'] == 'failed'
    assert wizard.stage_state['train'] == 'pending'
    assert 'MemoryError' in wizard.train_status.value and wizard.train_btn.visible


def _fake_trained_project(wizard, word, trained=True):
    name = W.slugify(word)
    ws = W.Workspace(os.path.join(wizard.root, 'projects', name), W.Project(word=word, language='pt'))
    ws.save_project()
    if trained:
        with open(ws.model_path, 'wb') as f:
            f.write(b'onnx')
    return ws


def test_reduce_false_triggers_entry_lists_only_trained_projects(wizard, tmp_path):
    _fake_trained_project(wizard, 'Bruninha')
    _fake_trained_project(wizard, 'Bruna')
    _fake_trained_project(wizard, 'Rascunho', trained=False)        # no model yet: not offered
    wizard.improve_mode = True
    wizard._show_picker()
    assert wizard.title.value == 'Reduzir ativações falsas'
    assert not wizard.next_btn.visible and not wizard.back_btn.visible
    assert [o.key for o in wizard.pick_dd.options] == ['bruna', 'bruninha']
    wizard._open_project('bruninha')
    assert wizard.ws.project.word == 'Bruninha' and wizard.language == 'pt'
    assert wizard.step == 1                      # tools not installed in the test folder: install first


def test_reduce_false_triggers_goes_straight_to_improve_when_tools_are_ready(wizard, monkeypatch):
    _fake_trained_project(wizard, 'Bruninha')
    monkeypatch.setattr(W.env_setup, 'is_ready', lambda root: True)
    wizard.improve_mode = True
    wizard._show_picker()
    wizard._open_project('bruninha')
    assert wizard.step == 5 and wizard.title.value == 'Melhorar'


def test_reduce_false_triggers_without_projects_offers_to_create_one(wizard):
    wizard.improve_mode = True
    wizard._show_picker()
    shown = ' | '.join(_texts(wizard.body))
    assert 'Nenhuma palavra' in shown and 'Criar sua própria palavra' in shown
    wizard._start_new()
    assert wizard.step == 0 and not wizard.improve_mode


def test_settings_button_opens_the_wizard_on_the_improve_step(monkeypatch):
    import flet_settings
    launched = []
    monkeypatch.setattr(flet_settings.subprocess, 'Popen', lambda cmd, **kw: launched.append(cmd))
    app = flet_settings.FletSettingsApp()
    app._open_wake_word_wizard(None, improve=True)
    app._open_wake_word_wizard(None)
    assert launched[0][-2:] == ['--wake-word-wizard', '--improve']
    assert launched[1][-1] == '--wake-word-wizard'


def test_improve_step_records_scans_and_offers_retraining(wizard, monkeypatch):
    wizard.lang_dd.value, wizard.word_tf.value = 'pt', 'Bruninha'
    wizard._apply_welcome()
    wizard._show(5)
    assert wizard.title.value == 'Melhorar' and not wizard.next_btn.disabled     # optional step
    assert wizard.imp_privacy.visible and 'Privacidade' in wizard.imp_privacy.value
    _run_threads_inline(monkeypatch)
    seen = {}

    from wakeword_trainer import recorder
    def fake_record(total, folder, tag, on_update=None, stop_event=None, max_clips=None):
        seen['seconds'], seen['folder'], seen['tag'], seen['max'] = total, folder, tag, max_clips
        seen['btn_hidden'] = not wizard.imp_btn.visible and wizard.imp_wait.visible and wizard.imp_stop.visible
        on_update(60, 0.5, 12)
        return 40
    monkeypatch.setattr(recorder, 'record_ambient', fake_record)
    monkeypatch.setattr(wizard, '_run_cli', lambda args, **kw: {'clips': 20, 'triggers': 6, 'rate': 0.3})
    wizard.imp_minutes.value = '15'
    wizard._improve_record()
    assert seen == {'seconds': 900, 'folder': wizard.ws.real_neg, 'tag': 'env', 'btn_hidden': True,
                    'max': W.IMPROVE_TARGET_CLIPS}
    shown = ' | '.join(_texts(wizard.imp_result))
    assert 'Antes: 6 de 20' in shown
    assert wizard.imp_retrain.visible and wizard.imp_btn.visible and not wizard.imp_wait.visible
    assert wizard.improve_before == {'clips': 20, 'triggers': 6, 'rate': 0.3}


def test_improve_step_reports_silence_and_errors(wizard, monkeypatch):
    wizard.lang_dd.value, wizard.word_tf.value = 'pt', 'Bruninha'
    wizard._apply_welcome()
    wizard._show(5)
    _run_threads_inline(monkeypatch)
    from wakeword_trainer import recorder
    monkeypatch.setattr(recorder, 'record_ambient', lambda *a, **k: 0)
    monkeypatch.setattr(wizard, '_run_cli', lambda args, **kw: {'clips': 0, 'triggers': 0, 'rate': None})
    wizard._improve_record()
    assert 'Nenhum som foi gravado' in ' | '.join(_texts(wizard.imp_result)) and not wizard.imp_retrain.visible

    def boom(*a, **k):
        raise RuntimeError('mic busy')
    monkeypatch.setattr(recorder, 'record_ambient', boom)
    wizard._improve_record()
    assert 'mic busy' in wizard.imp_status.value and wizard.imp_btn.visible


def test_retrain_from_improve_jumps_to_train_and_shows_before_after(wizard, monkeypatch):
    wizard.lang_dd.value, wizard.word_tf.value = 'pt', 'Bruninha'
    wizard._apply_welcome()
    wizard.improve_before = {'clips': 20, 'triggers': 6, 'rate': 0.3}
    wizard._show(5)
    _run_threads_inline(monkeypatch)

    def fake_cli(args, on_progress=None, on_log=None, on_stage=None):
        if args[0] == 'scan':
            return {'clips': 20, 'triggers': 1, 'rate': 0.05}
        if args[0] == 'train':
            return {}
        return {'verdict': {'level': 'good', 'reasons': []}, 'test_pos': {'clips': 1, 'above': {'0.5': 1}},
                'hold_real_neg': {'clips': 0, 'above': {'0.5': 0}}}
    monkeypatch.setattr(wizard, '_run_cli', fake_cli)
    wizard._improve_retrain()
    assert wizard.step == 4
    shown = ' | '.join(_texts(wizard.verdict_box))
    assert 'Antes: 6 de 20' in shown and 'Depois: 1 de 20' in shown
    assert wizard.improve_before is None            # consumed: a later retrain does not compare again


def test_captured_triggers_are_used_as_negatives_and_never_twice(wizard, monkeypatch):
    import numpy as np
    import soundfile as sf
    wizard.lang_dd.value, wizard.word_tf.value = 'pt', 'Bruninha'
    wizard._apply_welcome()
    folder = os.path.join(wizard.root, 'detections', 'bruninha')
    os.makedirs(folder)
    for i in range(6):
        sf.write(os.path.join(folder, f'trig_20261014_11000{i}_bruninha_099.wav'), np.zeros(48000, np.float32), 16000)
    wizard._show(5)
    assert '6' in wizard.imp_trig_text.value and not wizard.imp_trig_btn.disabled
    _run_threads_inline(monkeypatch)
    calls = []

    def fake_cli(args, on_progress=None, on_log=None, on_stage=None):
        calls.append(args)
        if args[0] == 'scan':
            return {'clips': 3, 'triggers': 2 if len(calls) == 1 else 0, 'rate': 0.0}
        if args[0] == 'train':
            return {}
        return {'verdict': {'level': 'good', 'reasons': []}, 'test_pos': {'clips': 1, 'above': {'0.5': 1}},
                'hold_real_neg': {'clips': 0, 'above': {'0.5': 0}}}
    monkeypatch.setattr(wizard, '_run_cli', fake_cli)
    wizard._use_captured()
    copied = sorted(n for n in os.listdir(wizard.ws.real_neg) if n.startswith('real_trig_'))
    assert copied == [f'real_trig_000{i}.wav' for i in range(6)]
    assert os.listdir(os.path.join(folder, 'used')) and not [n for n in os.listdir(folder) if n.endswith('.wav')]
    assert ['scan', '--workspace', wizard.ws.root, '--tag', 'trig'] in calls            # "before" on trigger clips
    assert wizard.step == 4 and wizard.improve_before is None                          # retrained, consumed
    assert 'Antes: 2 de 3' in ' | '.join(_texts(wizard.verdict_box))
    wizard._show(5)
    assert wizard.imp_trig_btn.disabled and 'Ainda nenhum' in wizard.imp_trig_text.value    # all were consumed


def test_last_step_has_a_close_button(wizard, monkeypatch):
    wizard.lang_dd.value, wizard.word_tf.value = 'pt', 'Bruninha'
    wizard._apply_welcome()
    wizard._show(6)
    assert wizard.next_btn.visible and wizard.next_btn.text == 'Fechar'
    closed = []
    monkeypatch.setattr(wizard, '_on_close', lambda: closed.append(True))
    wizard.next_btn.on_click(None)
    assert closed == [True]
    wizard._show(4)
    assert wizard.next_btn.text == 'Avançar'          # not the close button on other steps


def test_risky_word_is_warned_once_then_allowed(wizard):
    wizard.lang_dd.value, wizard.word_tf.value = 'pt', 'Bruna'          # short, and a common name
    assert wizard._apply_welcome() is False
    warning = wizard.welcome_msg.value
    assert 'curta' in warning and 'palavra ou nome comum' in warning and 'Avançar de novo' in warning
    assert wizard.ws is None
    assert wizard._apply_welcome() is True                               # same word, second click: continue
    assert wizard.ws.project.model_name == 'bruna'
    wizard.word_tf.value = 'Bruninha'                                    # a good word: no warning at all
    assert wizard._apply_welcome() is True


def test_adding_a_weak_model_warns_and_offers_to_improve_first(wizard, monkeypatch):
    wizard.lang_dd.value, wizard.word_tf.value = 'pt', 'Bruninha'
    wizard._apply_welcome()
    wizard._show(6)
    wizard.evaluation = {'verdict': {'level': 'ok', 'reasons': []}}
    wizard._offer_add()
    assert 'Atenção' in wizard.add_msg.value
    labels = [b.text for b in wizard.add_row.controls]
    assert labels[0] == 'Melhorar antes (recomendado)' and 'Adicionar mesmo assim' in labels
    wizard.add_row.controls[0].on_click(None)
    assert wizard.step == 5                                              # jumps to the Improve step


def test_a_good_model_is_offered_without_warning(wizard):
    wizard.lang_dd.value, wizard.word_tf.value = 'pt', 'Bruninha'
    wizard._apply_welcome()
    wizard._show(6)
    wizard.evaluation = {'verdict': {'level': 'good', 'reasons': []}}
    wizard._offer_add()
    assert 'Atenção' not in wizard.add_msg.value
    assert wizard.add_row.controls[0].text == 'Adicionar à minha lista de palavras'


def test_false_triggers_seen_in_the_live_test_count_as_weak(wizard):
    wizard.lang_dd.value, wizard.word_tf.value = 'pt', 'Bruninha'
    wizard._apply_welcome()
    wizard._show(6)
    wizard.evaluation = {'verdict': {'level': 'good', 'reasons': []}}
    wizard.false_test_count = 3
    wizard._offer_add()
    assert 'Atenção' in wizard.add_msg.value


def test_verdict_is_remembered_between_sessions(wizard):
    wizard.lang_dd.value, wizard.word_tf.value = 'pt', 'Bruninha'
    wizard._apply_welcome()
    wizard._save_evaluation({'verdict': {'level': 'poor', 'reasons': []}})
    wizard.evaluation = None
    assert wizard._last_verdict_level() == 'poor'
    wizard._show(6)
    wizard._offer_add()
    assert 'Atenção' in wizard.add_msg.value


def test_add_to_list_uses_install_and_reports(wizard, monkeypatch):
    wizard.lang_dd.value, wizard.word_tf.value = 'pt', 'Bruninha'
    wizard._apply_welcome()
    wizard._show(6)
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
