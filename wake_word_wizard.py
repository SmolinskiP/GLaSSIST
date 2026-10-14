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
STEP_NAMES = ['Language & word', 'Training tools', 'Voices', 'Your voice', 'Train', 'Test']

# (key, title, seconds, instructions, minimum clips, destination)
RECORDINGS = [
    ('word', 'Say your wake word', 120,
     'Say the wake word about once every 3 seconds, with a pause in between. Vary it: normal, quiet, loud, '
     'fast, near and far from the microphone.', 25),
    ('speech', 'Talk normally', 120,
     'Talk about anything (tell about your day, read something aloud, let a video play). '
     'Do NOT say the wake word. This teaches the model what is not the word.', 30),
    ('quiet', 'Stay quiet', 30,
     'Do not speak. This records the sound of your room (fan, hum, keyboard).', 0),
    ('test', 'Final exam: say it once more', 75,
     'Say the wake word again, about once every 3 seconds. These recordings are never used for training: '
     'they are only used to check honestly how well the model works.', 10),
]


class WakeWordWizard:
    def __init__(self):
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
        self._show(0)

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
        self.next_btn.visible = step < len(STEP_NAMES) - 1
        self.next_btn.disabled = False
        getattr(self, f'_view_{step}')()
        self.page.update()

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
            return s['real_pos'] >= 25 and s['real_neg'] >= 30 and s['test_pos'] >= 10
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
    def _run_cli(self, args, on_progress=None, on_log=None):
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
        self.voices_btn = ft.FilledButton('Generate the voices', icon=ft.Icons.RECORD_VOICE_OVER,
                                          on_click=self._generate)
        done = s['synthetic_pos'] >= 50 and s['synthetic_neg'] >= 100
        self.voices_status.value = (f'{t("Ready")}: {s["synthetic_pos"]} + {s["synthetic_neg"]}'
                                    if done else t('Not generated yet.'))
        self.voices_btn.text = t('Generate again') if done else t('Generate the voices')
        self.body.content = ft.Column([
            ft.Text('The computer will now create thousands of short audio clips of your word (and of other '
                    'words and phrases that must NOT trigger it) using neural voices of the chosen language, '
                    'at different speeds and pitches. Takes about 5 to 10 minutes.'),
            self.voices_status, self.voices_btn, self.voices_bar], spacing=10)
        self.next_btn.disabled = not done

    def _generate(self, e=None):
        self.voices_bar.visible = True
        self._set_busy(True)

        def progress(done, total):
            self.voices_bar.value = done / max(1, total)
            self._say(self.voices_status, f'{done} / {total}')

        def work():
            try:
                self._run_cli(['generate', '--workspace', self.ws.root], on_progress=progress)
                s = self.ws.summary()
                self._say(self.voices_status, f'{t("Ready")}: {s["synthetic_pos"]} + {s["synthetic_neg"]}',
                          ft.Colors.GREEN_700)
            except Exception as exc:
                self._error(self.voices_status, exc)
            finally:
                self.voices_bar.visible = False
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
        if s['real_pos'] < 25: need.append(t('at least 25 clips of your word'))
        if s['real_neg'] < 30: need.append(t('at least 30 speech clips'))
        if s['test_pos'] < 10: need.append(t('at least 10 exam clips'))
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
        self.train_bar = ft.ProgressBar(value=0, visible=False)
        self.train_status = ft.Text(size=13)
        self.train_log = ft.Text(size=11, color=ft.Colors.GREY_600, max_lines=6)
        self.verdict_box = ft.Column(spacing=6)
        self.train_btn = ft.FilledButton('Train the model', icon=ft.Icons.MODEL_TRAINING, on_click=self._train)
        trained = s['model'] is not None
        self.train_status.value = t('A trained model already exists for this word.') if trained else ''
        self.body.content = ft.Column([
            ft.Text('Now the computer learns your word from the synthetic voices and from your recordings, then '
                    'checks itself on the exam recordings it has never seen. This takes about 15 to 20 minutes '
                    'and uses the CPU heavily. You can leave it running.'),
            self.train_btn, self.train_bar, self.train_status, self.train_log, self.verdict_box],
            spacing=10, scroll=ft.ScrollMode.AUTO)
        self.next_btn.disabled = not trained

    def _train(self, e=None):
        self.train_bar.visible = True
        self.train_btn.disabled = True
        self.verdict_box.controls.clear()
        self._set_busy(True)
        lines = []

        def log(msg):
            lines.append(msg)
            self.train_log.value = '\n'.join(lines[-5:])
            self.page.update()

        def progress(done, total):
            self.train_bar.value = done / max(1, total)
            self.page.update()

        def work():
            try:
                self._say(self.train_status, t('Training... (extracting audio features is the slow part)'))
                self._run_cli(['train', '--workspace', self.ws.root, '--rebuild'], progress, log)
                self.train_bar.value = None
                self._say(self.train_status, t('Checking the model on your exam recordings...'))
                self.evaluation = self._run_cli(['evaluate', '--workspace', self.ws.root], progress, log)
                self._show_verdict(self.evaluation)
                self._say(self.train_status, t('Training finished.'), ft.Colors.GREEN_700)
            except Exception as exc:
                self._error(self.train_status, exc)
            finally:
                self.train_bar.visible = False
                self.train_btn.disabled = False
                self.train_btn.text = t('Train again')
                self._set_busy(False)
        threading.Thread(target=work, daemon=True).start()

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
            rows.append(ft.Text('To improve it: go back to "Your voice", record more clips of your word and more '
                                'normal speech, then train again.', size=12, color=ft.Colors.GREY_700))
        self.verdict_box.controls = rows
        self.page.update()

    # ------------------------------------------------------------------ step 6: test & add
    def _view_5(self):
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
                self._say(self.test_text, t('Listening... say your wake word.'))
                while not self.stop_event.is_set():
                    frame = np.frombuffer(stream.read(1280, exception_on_overflow=False), dtype=np.int16)
                    score = max(model.predict(frame).values())
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


def run():
    wizard = WakeWordWizard()
    ft.app(target=wizard.main, view=ft.FLET_APP)


if __name__ == '__main__':
    run()
