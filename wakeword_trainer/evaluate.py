"""Honest evaluation of a trained model on audio that never took part in training."""
import os

import numpy as np
import soundfile as sf

from . import features as F


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


def verdict(result):
    """Plain-language summary used by the wizard: 'good', 'ok' or 'poor' plus the reasons."""
    pos = result['test_pos']
    detected = pos['above'].get('0.5', 0) / pos['clips'] if pos['clips'] else None
    neg = result['hold_real_neg']
    false_rate = neg['above'].get('0.5', 0) / neg['clips'] if neg['clips'] else None
    reasons = []
    level = 'good'
    if detected is None:
        reasons.append('no test recordings of your voice were found')
        level = 'ok'
    elif detected < 0.8:
        level = 'poor'; reasons.append(f'only {detected:.0%} of your test recordings were detected')
    elif detected < 0.95:
        level = 'ok'; reasons.append(f'{detected:.0%} of your test recordings were detected')
    if false_rate is not None:
        n_false = neg['above'].get('0.5', 0)
        if n_false:
            reasons.append(f'{n_false} of {neg["clips"]} normal-speech clips triggered it')
        if false_rate > 0.15:
            level = 'poor'
        elif false_rate > 0.03 and level == 'good':
            level = 'ok'
        if neg['clips'] < 40 and n_false:
            reasons.append('only a few speech clips were checked, so this number is not very reliable: '
                           'record more normal speech to check it better')
    return {'level': level, 'detected': detected, 'false_clip_rate': false_rate, 'reasons': reasons}
