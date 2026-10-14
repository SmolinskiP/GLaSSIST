"""Synthetic training audio with Microsoft Edge neural TTS voices (online, no API key)."""
import asyncio
import hashlib
import io
import itertools
import os
import random

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from . import SAMPLE_RATE, confusables

RATES = ['-25%', '-12%', '+0%', '+12%', '+25%']
PITCHES = ['-20Hz', '+0Hz', '+20Hz']


async def list_voices(locales, max_voices=8, seed=3):
    """Pick up to `max_voices` voices of the given locales, mixing genders and locales."""
    import edge_tts
    voices = await edge_tts.list_voices()
    chosen = [v for v in voices if v['Locale'] in locales]
    if not chosen:
        raise RuntimeError(f'no TTS voices found for locales {locales}')
    rng = random.Random(seed)
    rng.shuffle(chosen)
    chosen.sort(key=lambda v: (v['Locale'], v['Gender']))
    # round-robin over (locale, gender) groups so one locale cannot take every slot
    groups = {}
    for v in chosen:
        groups.setdefault((v['Locale'], v['Gender']), []).append(v['ShortName'])
    out = []
    while len(out) < max_voices and any(groups.values()):
        for key in list(groups):
            if groups[key] and len(out) < max_voices:
                out.append(groups[key].pop(0))
    return out


def _filename(folder, text, voice, rate, pitch, tag):
    h = hashlib.md5(f'{text}|{voice}|{rate}|{pitch}'.encode()).hexdigest()[:10]
    return os.path.join(folder, f'{tag}_{h}.wav')


async def _synth(text, voice, rate, pitch):
    import edge_tts
    stream = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).stream()
    buf = bytearray()
    async for chunk in stream:
        if chunk['type'] == 'audio':
            buf.extend(chunk['data'])
    data, sr = sf.read(io.BytesIO(bytes(buf)), dtype='float32', always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != SAMPLE_RATE:
        g = int(np.gcd(sr, SAMPLE_RATE))
        data = resample_poly(data, SAMPLE_RATE // g, sr // g).astype(np.float32)
    return data


def plan_jobs(ws, corpus, voices, n_pos=500, seed=7):
    """[(kind, text, voice, rate, pitch)] for positives and negatives."""
    rng = random.Random(seed)
    word = ws.project.word
    jobs = []
    combos = list(itertools.product(voices, RATES, PITCHES))
    for text in confusables.positive_phrases(word, corpus['wake_prefixes']):
        for combo in combos:
            jobs.append(('pos', text, *combo))
    rng.shuffle(jobs)
    jobs = jobs[:n_pos]
    for text, weight in confusables.negative_phrases(word, corpus):
        for _ in range(weight if weight > 1 else 2):
            jobs.append(('neg', text, rng.choice(voices), rng.choice(RATES), rng.choice(PITCHES)))
        if weight >= 3:
            jobs.extend(('neg', text, v, '+0%', '+0Hz') for v in voices)
    rng.shuffle(jobs)
    return jobs


async def generate(ws, corpus, progress=None, max_voices=8, workers=8):
    """Create the synthetic wavs (resumable: existing files are kept). Returns a stats dict."""
    voices = await list_voices(corpus['edge_locales'], max_voices)
    jobs = plan_jobs(ws, corpus, voices)
    stats = {'ok': 0, 'skipped': 0, 'errors': 0, 'total': len(jobs), 'voices': voices}
    queue = asyncio.Queue()
    for job in jobs:
        queue.put_nowait(job)
    for _ in range(workers):
        queue.put_nowait(None)

    async def worker():
        while True:
            job = await queue.get()
            if job is None:
                return
            kind, text, voice, rate, pitch = job
            folder, tag = (ws.pos, 'pos') if kind == 'pos' else (ws.neg, 'neg')
            path = _filename(folder, text, voice, rate, pitch, f'{tag}_{voice.split("-")[0][:2]}')
            if os.path.exists(path):
                stats['skipped'] += 1
                continue
            for attempt in range(3):
                try:
                    audio = await _synth(text, voice, rate, pitch)
                    if len(audio) > SAMPLE_RATE // 10:
                        sf.write(path, audio, SAMPLE_RATE, subtype='PCM_16')
                        stats['ok'] += 1
                    break
                except Exception:
                    if attempt == 2:
                        stats['errors'] += 1
                    await asyncio.sleep(1.5)

    tasks = [asyncio.create_task(worker()) for _ in range(workers)]
    while not all(t.done() for t in tasks):
        await asyncio.sleep(2)
        if progress:
            progress(stats['ok'] + stats['skipped'] + stats['errors'], stats['total'])
    if progress:
        progress(stats['total'], stats['total'])
    if stats['errors'] > 0.3 * stats['total']:
        raise RuntimeError(f"too many TTS errors ({stats['errors']}/{stats['total']}); check the internet connection")
    return stats
