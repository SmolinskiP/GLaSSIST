"""Honest evaluation of a trained model on audio that never took part in training."""
import glob
import os

import numpy as np
import soundfile as sf

from . import features as F

# A clip with sound is 2 s long, so N clips with sound ~ N*2 s of everyday audio.
CLIP_SECONDS = 2.0
MIN_CLIPS_FOR_GOOD = 60          # fewer held-out clips cannot prove a low false-trigger rate


class OnnxHead:
    def __init__(self, path):
        import onnxruntime as ort
        self.sess = ort.InferenceSession(path, providers=['CPUExecutionProvider'])
        self.name = self.sess.get_inputs()[0].name

    def scores(self, windows):
        if len(windows) == 0:
            return np.zeros(0, np.float32)
        return np.concatenate([self.sess.run(None, {self.name: windows[i:i + 1]})[0].ravel()
                               for i in range(len(windows))])


def clip_max_score(head, path):
    """Highest score the model gives anywhere inside a clip (one 'detection' per clip)."""
    a, _ = sf.read(path, dtype='float32')
    pad = np.zeros(16000, np.float32)
    wins = F.sliding_windows(F.embeddings(np.concatenate([pad, a, pad])))
    return float(head.scores(wins).max()) if len(wins) else 0.0


def _rates(scores, thresholds):
    s = np.asarray(scores)
    return {str(t): int((s > t).sum()) for t in thresholds}


def per_hour(false_clips, clips):
    """Estimated false triggers per hour of everyday SPEECH/sound (not per hour of the day)."""
    if not clips:
        return None
    return false_clips / clips * 3600 / CLIP_SECONDS


def evaluate(ws, model_path=None, thresholds=(0.5, 0.7, 0.9), progress=None):
    head = OnnxHead(model_path or ws.model_path)
    files = F.split_files(ws)
    result = {}
    steps = [('test_pos', files['test_pos']), ('hold_real_neg', files['hold_real_neg']),
             ('hold_neg', files['hold_neg'])]
    total = sum(len(v) for _, v in steps) + 1
    done = 0
    for name, group in steps:
        scores = []
        for f in group:
            scores.append(clip_max_score(head, f))
            done += 1
            if progress:
                progress(done, total)
        result[name] = {'clips': len(group), 'above': _rates(scores, thresholds),
                        'worst': sorted([(round(s, 3), os.path.basename(f)) for s, f in zip(scores, group)],
                                        reverse=True)[:5]}
    ambient = F.load_ambient(ws)
    if ambient is not None:
        s = head.scores(F.sliding_windows(F.embeddings(ambient)))
        result['ambient'] = {'seconds': round(len(ambient) / 16000, 1), 'windows_above_0_5': int((s > 0.5).sum()),
                             'max': round(float(s.max()), 3) if len(s) else 0.0}
    if progress:
        progress(total, total)
    result['verdict'] = verdict(result)
    return result


def scan_clips(ws, tag='env', holdout_only=True, threshold=0.5, model_path=None, progress=None):
    """How many recorded everyday-audio clips trigger the model? (None of them contain the wake word.)

    With holdout_only=True only the clips kept aside from training are scanned, so the number is
    honest both before and after retraining and the two can be compared.
    """
    head = OnnxHead(model_path or ws.model_path)
    files = sorted(glob.glob(os.path.join(ws.real_neg, f'real_{tag}_*.wav')))
    if holdout_only:
        files = [f for f in files if F.is_real_holdout(f)]
    scores = []
    for i, f in enumerate(files):
        scores.append(clip_max_score(head, f))
        if progress:
            progress(i + 1, len(files))
    triggers = int((np.asarray(scores) > threshold).sum()) if scores else 0
    return {'clips': len(files), 'triggers': triggers, 'rate': (triggers / len(files)) if files else None,
            'per_hour': per_hour(triggers, len(files)), 'threshold': threshold, 'holdout_only': holdout_only,
            'worst': sorted([(round(s, 3), os.path.basename(f)) for s, f in zip(scores, files)], reverse=True)[:5]}


def verdict(result):
    """Plain-language summary used by the wizard: 'good', 'ok' or 'poor' plus the reasons.

    The model will listen all day, so the false-trigger bar is strict and a small sample can never
    earn 'good': with few held-out clips a low rate proves nothing.
        good : recognizes >= 95%, <= 2% of everyday clips trigger it, at least 60 held-out clips
        ok   : recognizes >= 80%, <= 8% trigger it (or too few clips to be sure)
        poor : anything worse
    """
    pos = result['test_pos']
    detected = pos['above'].get('0.5', 0) / pos['clips'] if pos['clips'] else None
    neg = result['hold_real_neg']
    n_clips = neg['clips']
    n_false = neg['above'].get('0.5', 0)
    false_rate = n_false / n_clips if n_clips else None
    reasons, level = [], 'good'

    def worsen(new):
        nonlocal level
        order = ['good', 'ok', 'poor']
        level = order[max(order.index(level), order.index(new))]

    if detected is None:
        reasons.append('no test recordings of your voice were found'); worsen('ok')
    elif detected < 0.8:
        worsen('poor'); reasons.append(f'only {detected:.0%} of your test recordings were detected')
    elif detected < 0.95:
        worsen('ok'); reasons.append(f'{detected:.0%} of your test recordings were detected')

    if false_rate is None:
        reasons.append('no everyday speech was checked, so false triggers are unknown'); worsen('ok')
    else:
        if n_false:
            reasons.append(f'{n_false} of {n_clips} normal-speech clips triggered it')
        if false_rate > 0.08:
            worsen('poor')
        elif false_rate > 0.02:
            worsen('ok')
        if n_clips < MIN_CLIPS_FOR_GOOD:
            worsen('ok')
            reasons.append(f'only {n_clips} everyday clips were checked: record everyday audio '
                           f'("Improve") to be sure it does not trigger by mistake')
    return {'level': level, 'detected': detected, 'false_clip_rate': false_rate,
            'false_per_hour': per_hour(n_false, n_clips), 'reasons': reasons}
