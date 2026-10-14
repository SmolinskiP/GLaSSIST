"""Microphone recording for the wizard: your own voice is the most valuable training data."""
import os
import threading
import time

import numpy as np
import soundfile as sf

from . import SAMPLE_RATE

CHUNK = 320                 # 20 ms
STEP = 0.01                 # envelope resolution in seconds


def list_input_devices():
    import pyaudio
    pa = pyaudio.PyAudio()
    try:
        out = []
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info.get('maxInputChannels', 0) > 0:
                out.append((i, info['name']))
        return out
    finally:
        pa.terminate()


def default_input_index():
    import pyaudio
    pa = pyaudio.PyAudio()
    try:
        return int(pa.get_default_input_device_info()['index'])
    finally:
        pa.terminate()


class LiveCounter:
    """Counts utterances while recording (energy based), so the UI can show 'heard 12 so far'."""

    def __init__(self):
        self.floor = None
        self.calib = []
        self.in_speech = False
        self.last_active = 0.0
        self.count = 0
        self.start = 0.0

    def feed(self, rms, t):
        if self.floor is None:
            self.calib.append(rms)
            if t >= 0.8:
                self.floor = float(np.percentile(self.calib, 50))
            return self.count
        active = rms > max(self.floor * 4.0, 0.01)
        if active:
            if not self.in_speech:
                self.in_speech, self.start = True, t
            self.last_active = t
        elif self.in_speech and t - self.last_active > 0.35:
            self.in_speech = False
            if 0.25 <= self.last_active - self.start <= 3.0:
                self.count += 1
        return self.count


def record(seconds, device=None, on_update=None, stop_event=None):
    """Record `seconds` of mono 16 kHz audio. on_update(elapsed, level 0..1, utterances)."""
    import pyaudio
    pa = pyaudio.PyAudio()
    dev = default_input_index() if device is None else device
    stream = pa.open(format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE, input=True,
                     input_device_index=dev, frames_per_buffer=CHUNK)
    chunks, counter, t0 = [], LiveCounter(), time.time()
    try:
        while time.time() - t0 < seconds and not (stop_event and stop_event.is_set()):
            data = np.frombuffer(stream.read(CHUNK, exception_on_overflow=False), dtype=np.int16)
            chunks.append(data)
            x = data.astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(x ** 2)))
            n = counter.feed(rms, time.time() - t0)
            if on_update:
                on_update(time.time() - t0, min(1.0, rms * 8), n)
    finally:
        stream.stop_stream(); stream.close(); pa.terminate()
    return np.concatenate(chunks).astype(np.float32) / 32768.0 if chunks else np.zeros(0, np.float32)


def segment_words(audio, min_len=0.25, max_len=3.0, gap=0.35):
    """[(start, end)] sample ranges of separate utterances (energy based)."""
    if len(audio) < CHUNK * 4:
        return []
    env = np.sqrt(np.convolve(audio ** 2, np.ones(CHUNK) / CHUNK, mode='same'))[::CHUNK // 2]
    thr = max(np.percentile(env, 20) * 4.0, 0.01)
    active = env > thr
    segs, i, n, hole = [], 0, len(active), int(gap / STEP)
    while i < n:
        if not active[i]:
            i += 1
            continue
        j = last = i
        while j < n and (active[j] or j - last < hole):
            if active[j]:
                last = j
            j += 1
        segs.append((i, last + 1)); i = j
    pad = int(0.12 * SAMPLE_RATE)
    out = []
    for a, b in segs:
        if min_len <= (b - a) * STEP <= max_len:
            out.append((max(0, int(a * STEP * SAMPLE_RATE) - pad), min(len(audio), int(b * STEP * SAMPLE_RATE) + pad)))
    return out


class AmbientCollector:
    """Turns a continuous recording into 2-second clips and keeps only the ones with sound.

    Used to collect what the model hears in everyday life (conversations, TV, music) so it can learn
    that this is NOT the wake word. The noise floor is tracked over the last ~5 minutes, so a clip is
    kept when it is clearly louder than the room's background.
    """

    def __init__(self, folder, tag='env', chunk_seconds=2, history=150, factor=3.0, minimum=0.008):
        self.folder, self.tag = folder, tag
        self.size = int(chunk_seconds * SAMPLE_RATE)
        self.factor, self.minimum = factor, minimum
        self.levels = []
        self.history = history
        self.buffer = np.zeros(0, np.float32)
        self.saved = 0
        self.seen = 0
        os.makedirs(folder, exist_ok=True)
        self._index = _next_index(folder, tag)

    def feed(self, audio):
        """Add float32 audio; returns the number of clips saved by this call."""
        self.buffer = np.concatenate([self.buffer, audio])
        saved = 0
        while len(self.buffer) >= self.size:
            clip, self.buffer = self.buffer[:self.size], self.buffer[self.size:]
            level = float(np.sqrt(np.mean(clip ** 2)))
            self.seen += 1
            floor = float(np.percentile(self.levels, 30)) if len(self.levels) >= 10 else None
            self.levels = (self.levels + [level])[-self.history:]
            if floor is None:
                continue                       # first ~20 s only calibrate the room noise
            if level > max(floor * self.factor, self.minimum):
                sf.write(os.path.join(self.folder, f'real_{self.tag}_{self._index:04d}.wav'), clip,
                         SAMPLE_RATE, subtype='PCM_16')
                self._index += 1
                self.saved += 1
                saved += 1
        return saved


def record_ambient(seconds, folder, tag='env', device=None, on_update=None, stop_event=None, max_clips=None):
    """Record for `seconds` (or until stop_event is set, or `max_clips` clips were saved) and keep
    only the clips with sound.

    on_update(elapsed, level 0..1, clips_saved) is called about every 100 ms. Returns the number of
    clips saved. Nothing but those clips is written to disk.
    """
    import pyaudio
    pa = pyaudio.PyAudio()
    dev = default_input_index() if device is None else device
    stream = pa.open(format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE, input=True,
                     input_device_index=dev, frames_per_buffer=CHUNK * 5)
    collector, t0 = AmbientCollector(folder, tag), time.time()
    try:
        while time.time() - t0 < seconds and not (stop_event and stop_event.is_set()):
            if max_clips and collector.saved >= max_clips:
                break
            data = np.frombuffer(stream.read(CHUNK * 5, exception_on_overflow=False), dtype=np.int16)
            x = data.astype(np.float32) / 32768.0
            collector.feed(x)
            if on_update:
                on_update(time.time() - t0, min(1.0, float(np.sqrt(np.mean(x ** 2))) * 8), collector.saved)
    finally:
        stream.stop_stream(); stream.close(); pa.terminate()
    return collector.saved


def _next_index(folder, tag):
    return len([n for n in os.listdir(folder) if n.startswith(f'real_{tag}_')])


def save_word_clips(audio, folder, tag):
    """Cut `audio` into one wav per utterance. Returns the number of clips saved."""
    os.makedirs(folder, exist_ok=True)
    k = _next_index(folder, tag)
    clips = segment_words(audio)
    for s, e in clips:
        sf.write(os.path.join(folder, f'real_{tag}_{k:04d}.wav'), audio[s:e], SAMPLE_RATE, subtype='PCM_16')
        k += 1
    return len(clips)


def save_speech_chunks(audio, folder, tag, seconds=2):
    """Normal speech (negatives): consecutive 2-second pieces."""
    os.makedirs(folder, exist_ok=True)
    k = _next_index(folder, tag)
    step = seconds * SAMPLE_RATE
    n = 0
    for s in range(0, len(audio) - step, step):
        sf.write(os.path.join(folder, f'real_{tag}_{k:04d}.wav'), audio[s:s + step], SAMPLE_RATE, subtype='PCM_16')
        k += 1; n += 1
    return n


def append_ambient(audio, path):
    if os.path.exists(path):
        audio = np.concatenate([sf.read(path, dtype='float32')[0], audio])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sf.write(path, audio, SAMPLE_RATE, subtype='PCM_16')
    return len(audio) / SAMPLE_RATE
