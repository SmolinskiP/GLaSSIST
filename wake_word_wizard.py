"""Step-by-step wizard that trains a custom wake word in any supported language.

Run it from Settings -> Wake Word -> "Create your own wake word", or directly:
    python main.py --wake-word-wizard

Steps: 1 language & word - 2 training tools - 3 synthetic voices - 4 record your voice -
       5 train & evaluate - 6 test it live and add it to your wake word list.
The heavy work (voices, training) runs in a separate Python environment so GLaSSIST itself
does not need PyTorch. See docs/WAKE_WORD_WIZARD.md.
"""
import json
import os
import subprocess
import sys
import threading

import flet as ft

import i18n
import platform_utils
import utils
from wakeword_trainer import confusables, env_setup, install, languages
from wakeword_trainer.workspace import Project, Workspace, slugify

logger = utils.setup_logger()
i18n.init_from_env()
i18n.patch_flet(ft)
t = i18n.t

APP_DIR = os.path.dirname(os.path.abspath(__file__))
STEP_NAMES = ['Language & word', 'Training tools', 'Voices', 'Your voice', 'Train', 'Improve', 'Test']
IMPROVE_MINUTES = ('15', '30', '60')

MIN_WORD, MIN_SPEECH, MIN_TEST = 25, 60, 10      # minimum clips before "Next" is enabled

# (key, title, seconds, instructions, minimum clips)
RECORDINGS = [
    ('word', 'Say your wake word', 120,
     'Say the wake word about once every 3 seconds, with a pause in between. Vary it: normal, quiet, loud, '
     'fast, near and far from the microphone.', MIN_WORD),
    ('speech', 'Talk normally', 180,
     'Talk about anything (tell about your day, read something aloud, let a video play). '
     'Do NOT say the wake word. This teaches the model what is not the word and checks that it does not '
     'trigger by mistake: the more normal speech, the more reliable the result.', MIN_SPEECH),
    ('quiet', 'Stay quiet', 30,
     'Do not speak. This records the sound of your room (fan, hum, keyboard).', 0),
    ('test', 'Final exam: say it once more', 75,
     'Say the wake word again, about once every 3 seconds. These recordings are never used for training: '
     'they are only used to check honestly how well the model works.', MIN_TEST),
]


# (stage name emitted by the trainer, label shown in the checklist)
TRAIN_STAGES = [
    ('prepare', 'Prepare the data'),
    ('features', 'Extract the audio features (the slow part, about 10 minutes)'),
    ('train', 'Train the model'),
    ('export', 'Save the model'),
    ('evaluate', 'Check it on your exam recordings'),
]


class WakeWordWizard:
    def __init__(self, improve=False):
        self.improve_mode = improve       # opened from "Reduce false triggers": pick a project, go to Improve
        # recordings, projects and the training environment live here (kept out of git, see .gitignore)
        self.root = os.path.join(str(platform_utils.get_config_dir()), 'wakeword_workspace')
        self.page = None
        self.step = 0
        self.ws = None
        # default to the language of the interface when we have a corpus for it
        ui = i18n.get_language().split('_')[0]
        self.language = ui if ui in dict(languages.available_languages()) else 'en'
        self.word = ''
        self.busy = False
        self.stop_event = threading.Event()
        self.proc = None
        self.evaluation = None
        self.improve_before = None      # scan of everyday audio before retraining ("Improve" step)
        self.logs = []

    # ------------------------------------------------------------------ page scaffolding
    def main(self, page: ft.Page):
        self.page = page
        page.title = t('Create your own wake word')
        page.theme_mode = ft.ThemeMode.SYSTEM
        page.window_width, page.window_height = 860, 760
        page.padding = 20
        page.window_prevent_close = True          # so we can stop the background training first
        page.on_window_event = lambda e: self._on_close() if e.data == 'close' else None
        self.header = ft.Row(wrap=True, spacing=8)
        self.title = ft.Text(size=22, weight=ft.FontWeight.BOLD)
        self.body = ft.Container(expand=True)
        self.back_btn = ft.OutlinedButton('Back', icon=ft.Icons.ARROW_BACK, on_click=self._back)
        self.next_btn = ft.FilledButton('Next', icon=ft.Icons.ARROW_FORWARD, on_click=self._next)
        self.hint = ft.Text(size=12, color=ft.Colors.GREY_600)
        page.add(ft.Column([self.header, self.title, ft.Divider(), self.body,
                            ft.Row([self.hint], expand=False),
                            ft.Row([self.back_btn, self.next_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)],
                           expand=True))
        self._show_picker() if self.improve_mode else self._show(0)

    # ------------------------------------------------------------------ "improve" entry: pick a project
    def trained_projects(self):
        """[(folder name, Project)] of the projects that already have a trained model."""
        base = os.path.join(self.root, 'projects')
        found = []
        for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            try:
                ws = Workspace(os.path.join(base, name))
            except (OSError, ValueError, TypeError):
                continue
            if os.path.exists(ws.model_path):
                found.append((name, ws.project))
        return found

    def _show_picker(self):
        self.step = -1
        self.header.controls = []
        self.title.value = t('Reduce false triggers')
        self.back_btn.visible = self.next_btn.visible = False
        projects = self.trained_projects()
        if not projects:
            self.body.content = ft.Column([
                ft.Text('No custom wake word was trained with the wizard yet. Create one first: the wizard '
                        'then offers to improve it.'),
                ft.FilledButton('Create your own wake word', icon=ft.Icons.AUTO_FIX_HIGH,
                                on_click=lambda e: self._start_new())], spacing=12)
        else:
            self.pick_dd = ft.Dropdown(label='Which wake word do you want to improve?', width=480,
                                       value=projects[0][0],
                                       options=[ft.dropdown.Option(key=n, text=f'{p.word}  ({p.language})')
                                                for n, p in projects])
            self.body.content = ft.Column([
                ft.Text('The wizard will record everyday audio (conversations, TV, music) while you go about your '
                        'day, measure how often the model is fooled by it, and retrain it with those clips.'),
                self.pick_dd,
                ft.Row([ft.FilledButton('Continue', icon=ft.Icons.ARROW_FORWARD,
                                        on_click=lambda e: self._open_project(self.pick_dd.value)),
                        ft.TextButton('Create a new wake word instead', on_click=lambda e: self._start_new())])],
                spacing=12)
        self.page.update()

    def _start_new(self):
        self.improve_mode = False
        self._show(0)

    def _open_project(self, name):
        self.ws = Workspace(os.path.join(self.root, 'projects', name))
        self.language, self.word = self.ws.project.language, self.ws.project.word
        # the training tools are needed to measure and retrain; every earlier step is already done
        self._show(5 if env_setup.is_ready(self.root) else 1)

    def _on_close(self):
        self.stop_event.set()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        try:
            self.page.window_destroy()
        except Exception:
            pass

    def _refresh_header(self):
        self.header.controls = [
            ft.Container(
                content=ft.Text(f'{i + 1}. {t(name)}', size=12,
                                color=ft.Colors.WHITE if i == self.step else ft.Colors.GREY_700),
                padding=ft.padding.symmetric(horizontal=10, vertical=4), border_radius=12,
                bgcolor=ft.Colors.BLUE_600 if i == self.step else ft.Colors.GREY_300 if i > self.step else ft.Colors.GREEN_200)
            for i, name in enumerate(STEP_NAMES)]

    def _show(self, step):
        self.step = step
        self._refresh_header()
        self.title.value = t(STEP_NAMES[step])
        self.hint.value = ''
        self.back_btn.visible = step > 0
        last = step == len(STEP_NAMES) - 1
        self.next_btn.visible = True
        self.next_btn.disabled = False
        # the last step ends the wizard: the button closes the window
        self.next_btn.text = t('Close') if last else t('Next')
        self.next_btn.icon = ft.Icons.CHECK if last else ft.Icons.ARROW_FORWARD
        self.next_btn.on_click = self._close_window if last else self._next
        getattr(self, f'_view_{step}')()
        self.page.update()

    def _close_window(self, e=None):
        if self.busy or getattr(self, 'test_running', False):
            self.stop_event.set()
        self._on_close()

    def _back(self, e=None):
        if self.busy:
            return
        self._show(max(0, self.step - 1))

    def _next(self, e=None):
        if self.busy:
            return
        if self.step == 0 and not self._apply_welcome():
            return
        self._show(self.step + 1)

    def _set_busy(self, busy):
        self.busy = busy
        self.back_btn.disabled = busy
        self.next_btn.disabled = busy or not self._can_continue()
        self.page.update()

    def _can_continue(self):
        if self.step == 1:
            return env_setup.is_ready(self.root)
        if self.step == 2:
            return self.ws is not None and self.ws.count(self.ws.pos) >= 50 and self.ws.count(self.ws.neg) >= 100
        if self.step == 3:
            s = self.ws.summary()
            return s['real_pos'] >= MIN_WORD and s['real_neg'] >= MIN_SPEECH and s['test_pos'] >= MIN_TEST
        return True

    def _say(self, control, text, color=None):
        control.value = text
        control.color = color
        self.page.update()

    def _error(self, control, exc):
        logger.error(f'wizard error: {exc}')
        self._say(control, f'{t("Something went wrong")}: {exc}', ft.Colors.RED_600)

    # ------------------------------------------------------------------ step 1: language & word
    def _view_0(self):
        langs = languages.available_languages()
        self.lang_dd = ft.Dropdown(label='Language of the wake word', value=self.language, width=560,
                                   options=[ft.dropdown.Option(key=c, text=n) for c, n in langs])
        self.word_tf = ft.TextField(label='Wake word', value=self.word, width=560,
                                    helper_text='Best: 3-4 syllables, not a common word. Example: Bruninha, Jarvis')
        self.welcome_msg = ft.Text(size=13, color=ft.Colors.RED_600)
        self.body.content = ft.Column([
            ft.Text('This wizard teaches GLaSSIST to recognize a word of your choice, in your language. '
                    'It takes about 30 to 40 minutes, most of it waiting while the computer works.'),
            ft.Text('What it needs from you: a microphone, an internet connection (to download the training '
                    'tools and synthetic voices) and about 6 minutes of recordings of your own voice.',
                    size=13, color=ft.Colors.GREY_700),
            ft.Container(height=10), self.lang_dd, self.word_tf, self.welcome_msg,
            ft.Text('Privacy: your recordings never leave this computer. Only the text of the training '
                    'phrases is sent to the Microsoft Edge online voices to generate synthetic speech.',
                    size=12, color=ft.Colors.GREY_600)], spacing=10, scroll=ft.ScrollMode.AUTO)

    def _apply_welcome(self):
        word = (self.word_tf.value or '').strip()
        if len(confusables.normalize(word)) < 4:
            self._say(self.welcome_msg, t('Please type a word with at least 4 letters.'), ft.Colors.RED_600)
            return False
        if len(word) > 30:
            self._say(self.welcome_msg, t('That is too long: use a short word or phrase.'), ft.Colors.RED_600)
            return False
        self.language, self.word = self.lang_dd.value, word
        name = slugify(word)
        self.ws = Workspace(os.path.join(self.root, 'projects', name), Project(word=word, language=self.language))
        self.ws.save_project()
        return True

    # ------------------------------------------------------------------ step 2: training tools
    def _view_1(self):
        ready = env_setup.is_ready(self.root)
        self.tools_status = ft.Text(size=13)
        self.tools_log = ft.Text(size=11, color=ft.Colors.GREY_600, selectable=True, max_lines=8)
        self.tools_btn = ft.FilledButton('Install the training tools', icon=ft.Icons.DOWNLOAD, on_click=self._install_tools)
        self.tools_bar = ft.ProgressBar(visible=False)
        self.tools_btn.visible = not ready
        self.tools_status.value = (t('The training tools are installed.') if ready else
                                   t('Not installed yet.'))
        self.body.content = ft.Column([
            ft.Text('The training runs in its own Python environment, so GLaSSIST stays light. It will download '
                    'PyTorch (CPU version), the openWakeWord audio models and a few small libraries '
                    '(about 800 MB, several minutes). Nothing else on your computer is changed.'),
            ft.Text(f'{t("Folder")}: {self.root}', size=12, color=ft.Colors.GREY_600),
            self.tools_status, self.tools_btn, self.tools_bar, self.tools_log], spacing=10)
        self.next_btn.disabled = not ready

    def _install_tools(self, e=None):
        self.tools_btn.visible = False
        self.tools_bar.visible = True
        self._set_busy(True)
        self._say(self.tools_status, t('Installing... this can take 5 to 15 minutes. Please wait.'))

        def work():
            try:
                def log(line):
                    self.logs.append(line)
                    self.tools_log.value = '\n'.join(self.logs[-6:])
                    self.page.update()
                env_setup.create(self.root, log)
                self._say(self.tools_status, t('The training tools are installed.'), ft.Colors.GREEN_700)
            except Exception as exc:
                self.tools_btn.visible = True
                self._error(self.tools_status, exc)
            finally:
                self.tools_bar.visible = False
                self._set_busy(False)
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------ subprocess helper
    def _run_cli(self, args, on_progress=None, on_log=None, on_stage=None):
        """Run `python -m wakeword_trainer.cli ...` in the training environment; return its result dict."""
        cmd = [env_setup.trainer_python(self.root), '-m', 'wakeword_trainer.cli'] + args
        env = dict(os.environ, PYTHONUTF8='1', PYTHONUNBUFFERED='1', PYTHONPATH=APP_DIR)
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        self.proc = subprocess.Popen(cmd, cwd=APP_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding='utf-8', errors='replace', creationflags=flags)
        result, error, tail = None, None, []
        for line in self.proc.stdout:
            line = line.strip()
            try:
                msg = json.loads(line)
            except ValueError:
                tail.append(line); tail = tail[-5:]
                continue
            event = msg.pop('event', '')
            if event == 'progress' and on_progress:
                on_progress(msg['done'], msg['total'])
            elif event == 'log' and on_log:
                on_log(msg['msg'])
            elif event == 'stage' and on_stage:
                on_stage(msg['name'], msg['state'])
            elif event == 'result':
                result = msg
            elif event == 'error':
                error = msg['msg']
        code = self.proc.wait()
        if error or code != 0 or result is None:
            raise RuntimeError(error or ' | '.join(tail) or f'exit code {code}')
        return result

    # ------------------------------------------------------------------ step 3: synthetic voices
    def _view_2(self):
        s = self.ws.summary()
        self.voices_bar = ft.ProgressBar(value=0, visible=False)
        self.voices_status = ft.Text(size=13)
        self.voices_wait = ft.Text('Just wait: do not click or do anything else. This takes about 5 to 10 minutes.',
                                   size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700, visible=False)
        self.voices_btn = ft.FilledButton('Generate the voices', icon=ft.Icons.RECORD_VOICE_OVER,
                                          on_click=self._generate)
        done = s['synthetic_pos'] >= 50 and s['synthetic_neg'] >= 100
        self.voices_status.value = (f'{t("Ready")}: {s["synthetic_pos"]} + {s["synthetic_neg"]}'
                                    if done else t('Not generated yet.'))
        self.voices_btn.text = t('Generate again') if done else t('Generate the voices')
        self.body.content = ft.Column([
            ft.Text('The computer will now create thousands of short audio clips of your word (and of other '
                    'words and phrases that must NOT trigger it) using neural voices of the chosen language, '
                    'at different speeds and pitches. You only need to click the button once.'),
            self.voices_btn, self.voices_wait, self.voices_bar, self.voices_status], spacing=10)
        self.next_btn.disabled = not done

    def _generate(self, e=None):
        # the button disappears while it works, so it cannot be clicked twice
        self.voices_btn.visible = False
        self.voices_wait.visible = True
        self.voices_bar.visible = True
        self._say(self.voices_status, '')
        self._set_busy(True)

        def progress(done, total):
            self.voices_bar.value = done / max(1, total)
            self._say(self.voices_status, f'{done} / {total}')

        def work():
            ok = False
            try:
                self._run_cli(['generate', '--workspace', self.ws.root], on_progress=progress)
                s = self.ws.summary()
                ok = s['synthetic_pos'] >= 50 and s['synthetic_neg'] >= 100
                if ok:
                    self._say(self.voices_status, f'✓ {t("Ready")}: {s["synthetic_pos"]} + {s["synthetic_neg"]}',
                              ft.Colors.GREEN_700)
                else:
                    self._say(self.voices_status, t('Not enough voices were generated. Click the button to try again.'),
                              ft.Colors.RED_600)
            except Exception as exc:
                self._error(self.voices_status, exc)
                self.voices_status.value += '\n' + t('Click the button to try again.')
            finally:
                self.voices_wait.visible = False
                self.voices_bar.visible = False
                self.voices_btn.visible = not ok         # back only when it failed
                self.voices_btn.text = t('Try again') if not ok else t('Generate again')
                self._set_busy(False)
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------ step 4: record your voice
    def _view_3(self):
        self.rec_cards = {}
        cards = []
        for key, title, secs, text, minimum in RECORDINGS:
            status = ft.Text(size=12)
            bar = ft.ProgressBar(value=0, visible=False)
            counter = ft.Text(size=13, weight=ft.FontWeight.BOLD)
            btn = ft.FilledButton(f'{t("Start recording")} ({secs} s)', icon=ft.Icons.MIC,
                                  on_click=lambda e, k=key: self._record(k))
            self.rec_cards[key] = {'status': status, 'bar': bar, 'counter': counter, 'btn': btn}
            cards.append(ft.Card(content=ft.Container(padding=14, content=ft.Column([
                ft.Text(title, size=16, weight=ft.FontWeight.BOLD), ft.Text(text, size=12),
                ft.Row([btn, status], spacing=14), bar, counter], spacing=6))))
        self.rec_msg = ft.Text(size=12, color=ft.Colors.GREY_600)
        tip = ft.Text('Tip: pause GLaSSIST\'s wake word from the tray menu while you record, so it does not react. '
                      'The wizard asks to use your microphone only in this step and in the final test.',
                      size=12, color=ft.Colors.GREY_600)
        self.body.content = ft.Column([tip] + cards + [self.rec_msg], spacing=8, scroll=ft.ScrollMode.AUTO)
        self._refresh_recording_status()

    def _refresh_recording_status(self):
        s = self.ws.summary()
        counts = {'word': s['real_pos'], 'speech': s['real_neg'], 'quiet': 1 if s['has_ambient'] else 0,
                  'test': s['test_pos']}
        for key, title, secs, text, minimum in RECORDINGS:
            card = self.rec_cards[key]
            ok = counts[key] >= minimum
            label = {'word': 'clips of your word', 'speech': '2-second speech clips',
                     'quiet': 'room recording', 'test': 'exam clips'}[key]
            card['status'].value = f'{counts[key]} {t(label)}' + (f'  ✓' if ok and counts[key] else '')
            card['status'].color = ft.Colors.GREEN_700 if ok and counts[key] else None
        self.next_btn.disabled = self.busy or not self._can_continue()
        need = []
        if s['real_pos'] < MIN_WORD: need.append(f'{t("at least")} {MIN_WORD} {t("clips of your word")}')
        if s['real_neg'] < MIN_SPEECH: need.append(f'{t("at least")} {MIN_SPEECH} {t("speech clips")}')
        if s['test_pos'] < MIN_TEST: need.append(f'{t("at least")} {MIN_TEST} {t("exam clips")}')
        self.rec_msg.value = (t('Still needed') + ': ' + ', '.join(need)) if need else \
            t('You have enough recordings. More recordings make the result better.')
        self.page.update()

    def _record(self, key):
        spec = next(r for r in RECORDINGS if r[0] == key)
        _, title, secs, _, _ = spec
        card = self.rec_cards[key]
        card['bar'].visible = True
        card['btn'].disabled = True
        self._set_busy(True)
        self.stop_event.clear()

        def update(elapsed, level, n):
            card['bar'].value = level
            what = {'word': 'heard', 'test': 'heard'}.get(key)
            card['counter'].value = (f'{t("Recording")}... {int(secs - elapsed)} s ' +
                                     (f'· {t("heard")} {n}' if what else ''))
            self.page.update()

        def work():
            try:
                from wakeword_trainer import recorder
                card['counter'].value = t('Recording starts now: speak!')
                self.page.update()
                audio = recorder.record(secs, on_update=update, stop_event=self.stop_event)
                if key == 'word':
                    recorder.save_word_clips(audio, self.ws.real_pos, 'wizard')
                elif key == 'test':
                    recorder.save_word_clips(audio, self.ws.test_pos, 'wizard')
                elif key == 'speech':
                    recorder.save_speech_chunks(audio, self.ws.real_neg, 'wizard')
                else:
                    recorder.append_ambient(audio, self.ws.ambient)
                card['counter'].value = t('Saved.')
            except Exception as exc:
                self._error(card['counter'], exc)
            finally:
                card['bar'].visible = False
                card['btn'].disabled = False
                self.busy = False
                self.back_btn.disabled = False
                self._refresh_recording_status()
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------ step 5: train & evaluate
    def _view_4(self):
        s = self.ws.summary()
        trained = s['model'] is not None
        self.train_bar = ft.ProgressBar(value=0, visible=False)
        self.train_status = ft.Text(size=13)
        self.train_wait = ft.Text('Click once and wait: do not close this window. It takes about 15 to 20 minutes.',
                                  size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700, visible=False)
        self.verdict_box = ft.Column(spacing=6)
        self.train_btn = ft.FilledButton('Train the model', icon=ft.Icons.MODEL_TRAINING, on_click=self._train)
        self.stage_rows, self.stage_state, self.current_stage = {}, {}, None
        rows = []
        for key, label in TRAIN_STAGES:
            icon, name, detail = ft.Container(width=24, height=24), ft.Text(label, size=14), ft.Text(size=12, color=ft.Colors.GREY_600)
            self.stage_rows[key] = {'icon': icon, 'text': name, 'detail': detail}
            rows.append(ft.Row([icon, ft.Column([name, detail], spacing=0)], spacing=10))
            self._set_stage(key, 'pending')
        self.train_status.value = t('A trained model already exists for this word.') if trained else ''
        self.body.content = ft.Column([
            ft.Text('Now the computer learns your word from the synthetic voices and from your recordings, then '
                    'checks itself on the exam recordings it has never seen. It uses the CPU heavily; you can '
                    'leave it running.'),
            self.train_btn, self.train_wait, self.train_bar, ft.Column(rows, spacing=8),
            self.train_status, self.verdict_box], spacing=10, scroll=ft.ScrollMode.AUTO)
        self.next_btn.disabled = not trained

    def _set_stage(self, key, state, detail=''):
        """state: pending | running | done | failed. The icon shows what the computer is doing."""
        row = self.stage_rows[key]
        self.stage_state[key] = state
        if state == 'running':
            row['icon'].content = ft.ProgressRing(width=20, height=20, stroke_width=3)
        else:
            icon, color = {'done': (ft.Icons.CHECK_CIRCLE, ft.Colors.GREEN_600),
                           'failed': (ft.Icons.CANCEL, ft.Colors.RED_600)}.get(
                state, (ft.Icons.RADIO_BUTTON_UNCHECKED, ft.Colors.GREY_500))
            row['icon'].content = ft.Icon(icon, color=color, size=22)
        row['text'].weight = ft.FontWeight.BOLD if state == 'running' else ft.FontWeight.NORMAL
        row['text'].color = ft.Colors.RED_600 if state == 'failed' else None
        row['detail'].value = detail

    def _train(self, e=None):
        # one click: the button disappears and the stage list shows exactly what is happening
        self.train_btn.visible = False
        self.train_wait.visible = True
        self.train_bar.visible = True
        self.train_bar.value = None                  # indeterminate until we know the progress
        self.verdict_box.controls.clear()
        self._say(self.train_status, '')
        for key, _ in TRAIN_STAGES:
            self._set_stage(key, 'pending')
        self.current_stage = None
        self._set_busy(True)

        def on_stage(name, state):
            self.current_stage = name if state == 'start' else None
            self._set_stage(name, 'running' if state == 'start' else 'done')
            self.train_bar.value = None
            self.page.update()

        def on_log(msg):                              # e.g. "extracting audio features (...)"
            if self.current_stage == 'features':
                self.stage_rows['features']['detail'].value = msg[:90]
                self.page.update()

        def progress(done, total):
            if self.current_stage == 'train':
                self.train_bar.value = done / max(1, total)
                self.stage_rows['train']['detail'].value = f'{done} / {total}'
            elif self.current_stage == 'evaluate':
                self.stage_rows['evaluate']['detail'].value = f'{done} / {total}'
            self.page.update()

        def work():
            ok = False
            try:
                self._run_cli(['train', '--workspace', self.ws.root, '--rebuild'], progress, on_log, on_stage)
                self.evaluation = self._run_cli(['evaluate', '--workspace', self.ws.root], progress, on_log, on_stage)
                self._show_verdict(self.evaluation)
                if getattr(self, 'improve_before', None):          # came from the "Improve" step
                    self._set_stage_detail_scan()
                    after = self._run_cli(['scan', '--workspace', self.ws.root])
                    self._show_improvement(after)
                    self.improve_before = None
                self._say(self.train_status, t('Training finished.'), ft.Colors.GREEN_700)
                ok = True
            except Exception as exc:
                self._set_stage(self.current_stage or 'prepare', 'failed')
                self._error(self.train_status, exc)
                self.train_status.value += '\n' + t('Click the button to try again.')
            finally:
                self.train_wait.visible = False
                self.train_bar.visible = False
                self.train_btn.text = t('Train again') if ok else t('Try again')
                self.train_btn.visible = True
                self._set_busy(False)
        threading.Thread(target=work, daemon=True).start()

    def _set_stage_detail_scan(self):
        self.stage_rows['evaluate']['detail'].value = t('Comparing with the recorded everyday audio...')
        self.page.update()

    def _show_verdict(self, ev):
        v = ev['verdict']
        pos, neg = ev['test_pos'], ev['hold_real_neg']
        colors = {'good': ft.Colors.GREEN_700, 'ok': ft.Colors.ORANGE_700, 'poor': ft.Colors.RED_700}
        title = {'good': 'Good result', 'ok': 'Usable, but not perfect', 'poor': 'Not good enough yet'}[v['level']]
        rows = [ft.Text(t(title), size=18, weight=ft.FontWeight.BOLD, color=colors[v['level']])]
        if pos['clips']:
            rows.append(ft.Text(f'{t("Recognized in your exam recordings")}: {pos["above"]["0.5"]} / {pos["clips"]}'))
        if neg['clips']:
            rows.append(ft.Text(f'{t("Normal speech clips that triggered it by mistake")}: '
                                f'{neg["above"]["0.5"]} / {neg["clips"]}'))
        if 'ambient' in ev:
            rows.append(ft.Text(f'{t("False triggers in the room recording")}: {ev["ambient"]["windows_above_0_5"]}'))
        for r in v['reasons']:
            rows.append(ft.Text('• ' + t(r), size=12))
        if v['level'] != 'good':
            rows.append(ft.Text('To improve it: go back to "Your voice" and record more NORMAL SPEECH (this is what '
                                'reduces false triggers); if your word was not recognized well, record more clips of '
                                'the word too. You do not need to redo the voices. Then train again.',
                                size=12, color=ft.Colors.GREY_700))
        if v['level'] == 'ok':
            rows.append(ft.Text('You can already use it: raising the detection threshold in the settings also '
                                'reduces false triggers.', size=12, color=ft.Colors.GREY_700))
        self.verdict_box.controls = rows
        self.page.update()

    # ------------------------------------------------------------------ step 6: improve (optional)
    def _view_5(self):
        """Collect everyday audio (conversations, TV...) so the model learns what is NOT the word."""
        self.imp_minutes = ft.Dropdown(label='How long to record', value='30', width=240,
                                       options=[ft.dropdown.Option(key=m, text=f'{m} min') for m in IMPROVE_MINUTES])
        self.imp_privacy = ft.Text('Privacy: this records EVERYTHING the microphone hears, including other people '
                                   'talking. It stays on this computer and only the clips with sound are kept '
                                   '(not the silence). Tell the people around you.',
                                   size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_800)
        self.imp_wait = ft.Text('Keep doing your normal day. Do NOT say the wake word. You can stop at any time.',
                                size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700, visible=False)
        self.imp_btn = ft.FilledButton('Start recording', icon=ft.Icons.FIBER_MANUAL_RECORD, on_click=self._improve_record)
        self.imp_stop = ft.OutlinedButton('Stop now', icon=ft.Icons.STOP, visible=False,
                                          on_click=lambda e: self.stop_event.set())
        self.imp_bar = ft.ProgressBar(value=0, visible=False)
        self.imp_status = ft.Text(size=13)
        self.imp_result = ft.Column(spacing=6)
        self.imp_retrain = ft.FilledButton('Retrain with these examples', icon=ft.Icons.MODEL_TRAINING,
                                           visible=False, on_click=self._improve_retrain)
        self.improve_before = getattr(self, 'improve_before', None)
        self.body.content = ft.Column([
            ft.Text('Optional, but the best fix if your wake word triggers by mistake (conversations, TV, music). '
                    'Leave the microphone recording while you go about your day; the wizard keeps only the clips '
                    'with sound, measures how often the current model is fooled by them, and then retrains it '
                    'with them as examples of what is NOT your word.'),
            self.imp_privacy, ft.Row([self.imp_minutes, self.imp_btn, self.imp_stop], spacing=14),
            self.imp_wait, self.imp_bar, self.imp_status, self.imp_result, self.imp_retrain],
            spacing=10, scroll=ft.ScrollMode.AUTO)
        self.hint.value = t('You can skip this step.')
        self.next_btn.disabled = False

    def _improve_record(self, e=None):
        minutes = int(self.imp_minutes.value or '30')
        total = minutes * 60
        for c in (self.imp_btn, self.imp_minutes, self.imp_privacy):
            c.visible = False
        self.imp_wait.visible = self.imp_stop.visible = self.imp_bar.visible = True
        self.imp_retrain.visible = False
        self.imp_result.controls.clear()
        self.stop_event.clear()
        self._set_busy(True)

        def update(elapsed, level, saved):
            self.imp_bar.value = min(1.0, elapsed / total)
            self._say(self.imp_status, f'{int(elapsed // 60)}:{int(elapsed % 60):02d} / {minutes}:00   ·   '
                      f'{saved} {t("clips with sound saved")}')

        def work():
            ok = False
            try:
                from wakeword_trainer import recorder
                saved = recorder.record_ambient(total, self.ws.real_neg, 'env', on_update=update,
                                                stop_event=self.stop_event)
                self.imp_wait.visible = self.imp_stop.visible = False
                self.imp_bar.value = None
                self._say(self.imp_status, t('Measuring how often the current model is fooled...'))
                self.improve_before = self._run_cli(['scan', '--workspace', self.ws.root])
                self._show_before(self.improve_before, saved)
                ok = True
            except Exception as exc:
                self._error(self.imp_status, exc)
                self.imp_status.value += '\n' + t('Click the button to try again.')
            finally:
                self.imp_wait.visible = self.imp_stop.visible = self.imp_bar.visible = False
                self.imp_btn.text = t('Record more') if ok else t('Try again')
                self.imp_btn.visible = self.imp_minutes.visible = self.imp_privacy.visible = True
                self._set_busy(False)
        threading.Thread(target=work, daemon=True).start()

    def _show_before(self, scan, saved):
        n, k = scan['clips'], scan['triggers']
        rows = []
        if saved == 0:
            rows.append(ft.Text(t('No sound was recorded: check the microphone and try again.'), color=ft.Colors.RED_600))
        elif n == 0:
            rows.append(ft.Text(t('Recorded, but too few clips to measure yet. Record a bit longer.'), size=13))
        else:
            color = ft.Colors.GREEN_700 if k == 0 else ft.Colors.RED_700
            rows.append(ft.Text(f'{t("Recorded")}: {saved} {t("clips with sound")}.', size=13))
            rows.append(ft.Text(f'{t("Before")}: {k} {t("of")} {n} {t("clips the model had never heard triggered it by mistake")}.',
                                size=15, weight=ft.FontWeight.BOLD, color=color))
            if k:
                rows.append(ft.Text('Retraining with these clips teaches it that this is not your word.',
                                    size=12, color=ft.Colors.GREY_700))
        self.imp_result.controls = rows
        self.imp_retrain.visible = saved >= 10
        self._say(self.imp_status, '')

    def _improve_retrain(self, e=None):
        """Go to the Train step and start it: the new clips are now part of the training data."""
        self._show(4)
        self._train()

    def _show_improvement(self, after):
        """After retraining: show before / after on the same held-out clips."""
        before = self.improve_before
        if not before or not after['clips']:
            return
        better = after['triggers'] <= before['triggers']
        self.verdict_box.controls.append(ft.Text(
            f'{t("Before")}: {before["triggers"]} {t("of")} {before["clips"]}   →   '
            f'{t("After")}: {after["triggers"]} {t("of")} {after["clips"]}  {t("everyday clips that triggered it by mistake")}',
            size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700 if better else ft.Colors.ORANGE_700))

    # ------------------------------------------------------------------ step 7: test & add
    def _view_6(self):
        self.test_running = False
        self.score_bar = ft.ProgressBar(value=0, width=420)
        self.test_text = ft.Text(size=14)
        self.test_btn = ft.FilledButton('Yes, test it now', icon=ft.Icons.MIC, on_click=self._toggle_test)
        self.add_msg = ft.Text(size=13)
        self.add_row = ft.Row(wrap=True, spacing=10, visible=False)
        self.add_row.controls = [
            ft.FilledButton('Add it to my wake word list', icon=ft.Icons.PLAYLIST_ADD,
                            on_click=lambda e: self._add(replace=False)),
            ft.OutlinedButton('Use only this one', on_click=lambda e: self._add(replace=True)),
            ft.TextButton('Not now', on_click=lambda e: self._finish(False))]
        self.body.content = ft.Column([
            ft.Text('Your model is ready. Do you want to test it now? Say your word and watch the bar: when it '
                    'passes the middle, GLaSSIST would wake up.'),
            ft.Row([self.test_btn, ft.TextButton('Skip the test', on_click=lambda e: self._offer_add())]),
            self.score_bar, self.test_text, ft.Divider(), self.add_msg, self.add_row], spacing=10)

    def _toggle_test(self, e=None):
        if self.test_running:
            self.stop_event.set()
            return
        self.test_running = True
        self.stop_event.clear()
        self.test_btn.text = t('Stop the test')
        self.back_btn.disabled = True
        self.page.update()

        def work():
            detections = 0
            try:
                import numpy as np
                import pyaudio
                from openwakeword.model import Model
                model = Model(wakeword_models=[self.ws.model_path], inference_framework='onnx')
                pa = pyaudio.PyAudio()
                stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True,
                                 frames_per_buffer=1280)
                armed = True
                # the detector needs ~2 s of audio before its first reliable scores
                self._say(self.test_text, t('Getting ready... wait 2 seconds, then speak.'))
                frames = 0
                while not self.stop_event.is_set():
                    frame = np.frombuffer(stream.read(1280, exception_on_overflow=False), dtype=np.int16)
                    score = max(model.predict(frame).values())
                    frames += 1
                    if frames < 25:
                        continue
                    if frames == 25:
                        self._say(self.test_text, t('Listening... say your wake word.'))
                    self.score_bar.value = min(1.0, float(score))
                    self.score_bar.color = ft.Colors.GREEN_600 if score > 0.5 else None
                    if score > 0.5 and armed:
                        detections += 1
                        armed = False
                        self.test_text.value = f'{t("Detected")}: {detections}'
                    elif score < 0.2:
                        armed = True
                    self.page.update()
                stream.stop_stream(); stream.close(); pa.terminate()
            except Exception as exc:
                self._error(self.test_text, exc)
            finally:
                self.test_running = False
                self.test_btn.text = t('Test again')
                self.back_btn.disabled = False
                self.score_bar.value = 0
                self.page.update()
                self._offer_add()
        threading.Thread(target=work, daemon=True).start()

    def _offer_add(self):
        self.add_msg.value = t('Do you want to add this wake word to your list?')
        self.add_row.visible = True
        self.page.update()

    def _add(self, replace):
        try:
            result = install.install_model(self.ws.model_path, os.path.join(APP_DIR, 'models'),
                                           str(platform_utils.get_env_file_path()), self.ws.project.model_name,
                                           enable=True, replace=replace)
            self.add_row.visible = False
            self._say(self.add_msg, f'{t("Added")}: {", ".join(result["models"])}. '
                      + t('Restart GLaSSIST (or restart wake word detection from the tray menu) to use it.'),
                      ft.Colors.GREEN_700)
        except Exception as exc:
            self._error(self.add_msg, exc)

    def _finish(self, added):
        self.add_row.visible = False
        self._say(self.add_msg, t('Okay. Your model is saved in the wizard folder; you can add it later by running the wizard again.'))


def run(improve=False):
    wizard = WakeWordWizard(improve=improve)
    ft.app(target=wizard.main, view=ft.FLET_APP)


if __name__ == '__main__':
    run()
