"""openWakeWord embeddings and labelled 16x96 training windows.

Each clip is padded with silence, augmented (gain, reverb, muffled mic, noise at 5-30 dB SNR,
real room noise when available) and turned into sliding windows of 16 embeddings.
Positive window: it ENDS between 0.2 s before and 0.4 s after the end of the word.
Windows ending inside the word are ambiguous and skipped; everything else is negative.
"""
import glob
import hashlib
import os

import numpy as np
import soundfile as sf
from scipy.signal import fftconvolve, lfilter

from . import FRAME, SAMPLE_RATE as SR, WINDOW

rng = np.random.default_rng(1234)
_features = None


def audio_features():
    global _features
    if _features is None:
        from openwakeword.utils import AudioFeatures
        _features = AudioFeatures(inference_framework='onnx')
    return _features


def embeddings(audio):
    """float32 audio in [-1, 1] -> embeddings (T, 96), one every 80 ms."""
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    pad = (-len(pcm)) % FRAME                # openWakeWord needs a multiple of 1280 samples
    if pad:
        pcm = np.concatenate([pcm, np.zeros(pad, np.int16)])
    return audio_features().embed_clips(pcm[None, :], batch_size=1)[0]


def sliding_windows(emb):
    if len(emb) < WINDOW:
        return np.zeros((0, WINDOW, emb.shape[-1]), np.float32)
    return np.stack([emb[i - WINDOW:i] for i in range(WINDOW, len(emb) + 1)]).astype(np.float32)


def word_bounds(a, thr=0.02):
    env = np.abs(a)
    if env.max() < 1e-4:
        return 0, len(a)
    idx = np.where(env > thr * env.max())[0]
    return int(idx[0]), int(idx[-1]) + 1


def _pink(n):
    w = rng.standard_normal(n)
    p = lfilter([0.049922035, -0.095993537, 0.050612699, -0.004408786],
                [1, -2.494956002, 2.017265875, -0.522189400], w)
    return p / (np.abs(p).max() + 1e-9)


def _rir():
    n = int(SR * rng.uniform(0.1, 0.6))
    ir = rng.standard_normal(n) * np.exp(-6.9 * np.arange(n) / n)
    ir[0] = 1.0
    return ir / np.abs(ir).max()


def augment(a, ambient=None):
    a = a.astype(np.float32)
    if rng.random() < 0.5:
        a = a + fftconvolve(a, _rir() * rng.uniform(0.05, 0.4), mode='full')[:len(a)].astype(np.float32)
    if rng.random() < 0.3:
        a = lfilter([0.3], [1, -0.7], a).astype(np.float32)       # muffled / weak microphone
    a = a / (np.abs(a).max() + 1e-9) * rng.uniform(0.08, 0.9)
    snr = rng.uniform(5, 30)
    if ambient is not None and len(ambient) > len(a) and rng.random() < 0.6:
        s = int(rng.integers(0, len(ambient) - len(a)))
        noise = ambient[s:s + len(a)]
    else:
        noise = _pink(len(a)) if rng.random() < 0.7 else rng.standard_normal(len(a))
    noise = noise.astype(np.float32)
    ps, pn = np.mean(a ** 2) + 1e-12, np.mean(noise ** 2) + 1e-12
    return np.clip(a + noise * np.sqrt(ps / (pn * 10 ** (snr / 10))), -1, 1).astype(np.float32)


def clip_windows(a, is_pos, ambient=None, n_aug=3):
    X, y = [], []
    start, end = word_bounds(a)
    for _ in range(n_aug):
        pre = int(rng.uniform(0.6, 1.6) * SR)
        post = int(rng.uniform(0.2, 0.8) * SR)
        x = augment(np.concatenate([np.zeros(pre, np.float32), a, np.zeros(post, np.float32)]), ambient)
        wins = sliding_windows(embeddings(x))
        w_start, w_end = (pre + start) / SR, (pre + end) / SR
        for k, win in enumerate(wins):
            t_end = (WINDOW + k) * FRAME / SR + 0.12   # approximate end of window k (mel latency)
            if not is_pos:
                X.append(win); y.append(0)
            elif w_end - 0.20 <= t_end <= w_end + 0.40:
                X.append(win); y.append(1)
            elif t_end < w_start - 0.05 or t_end > w_end + 0.9:
                X.append(win); y.append(0)
    return X, y


def build(files_pos, files_neg, ambient=None, n_aug_pos=4, n_aug_neg=2, max_neg_per_clip=40):
    Xp, Xn = [], []
    for f in files_pos:
        a, sr = sf.read(f, dtype='float32')
        X, y = clip_windows(a, True, ambient, n_aug_pos)
        for x, label in zip(X, y):
            (Xp if label else Xn).append(x)
    for f in files_neg:
        a, sr = sf.read(f, dtype='float32')
        X, _ = clip_windows(a, False, ambient, n_aug_neg)
        cap = max_neg_per_clip * n_aug_neg
        if len(X) > cap:
            X = [X[i] for i in rng.choice(len(X), cap, replace=False)]
        Xn.extend(X)
    empty = np.zeros((0, WINDOW, 96), np.float32)
    return (np.array(Xp, np.float32) if Xp else empty), (np.array(Xn, np.float32) if Xn else empty)


# ---- train / hold-out split shared by training and evaluation -------------------------------
def is_synthetic_holdout(path):
    return int(hashlib.md5(os.path.basename(path).encode()).hexdigest(), 16) % 10 == 0


def is_real_holdout(path):
    """1 in 3 recorded speech clips is kept for the final check. Decided by the file NAME, so the
    choice never changes when more recordings are added later (no leakage between runs)."""
    return int(hashlib.md5(os.path.basename(path).encode()).hexdigest(), 16) % 3 == 0


def split_files(ws):
    """Everything the model is allowed to train on, and what is kept aside for the final exam."""
    wav = lambda folder: sorted(glob.glob(os.path.join(folder, '*.wav')))
    pos, neg = wav(ws.pos), wav(ws.neg)
    real_neg = wav(ws.real_neg)
    return {
        'train_pos': [f for f in pos if not is_synthetic_holdout(f)],
        'hold_pos': [f for f in pos if is_synthetic_holdout(f)],
        'train_neg': [f for f in neg if not is_synthetic_holdout(f)],
        'hold_neg': [f for f in neg if is_synthetic_holdout(f)],
        'train_real_pos': wav(ws.real_pos),
        'train_real_neg': [f for f in real_neg if not is_real_holdout(f)],
        'hold_real_neg': [f for f in real_neg if is_real_holdout(f)],
        'test_pos': wav(ws.test_pos),
    }


def load_ambient(ws):
    if os.path.exists(ws.ambient):
        return sf.read(ws.ambient, dtype='float32')[0]
    return None
