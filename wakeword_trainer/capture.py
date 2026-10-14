"""Keep a short audio clip of every wake word detection, to learn from false triggers.

A detection that was a mistake is the best possible training example: it is exactly the sound that
fools the model. When HA_WAKE_WORD_SAVE_DETECTIONS=true the detector keeps the last few seconds of
audio in memory (never written to disk) and saves them only when it triggers.
Clips go to <folder>/<model>/trig_<date>_<time>_<model>_<confidence>.wav; the oldest are pruned.
"""
import os
import time
import wave

import numpy as np

SAMPLE_RATE = 16000


class TriggerRecorder:
    def __init__(self, folder, seconds=3.0, max_files=300, sample_rate=SAMPLE_RATE):
        self.folder = folder
        self.sample_rate = sample_rate
        self.size = int(seconds * sample_rate)
        self.max_files = max_files
        self.buffer = np.zeros(0, np.int16)

    def push(self, chunk):
        """Add int16 audio to the in-memory ring buffer (nothing is written to disk here)."""
        self.buffer = np.concatenate([self.buffer, np.asarray(chunk, np.int16)])[-self.size:]

    def save(self, model_name, score, now=None):
        """Write the buffered audio for a detection. Returns the path, or None if too little audio."""
        if len(self.buffer) < self.sample_rate:            # under 1 s: nothing useful to learn from
            return None
        safe = ''.join(c for c in model_name if c.isalnum() or c in '_-') or 'model'
        folder = os.path.join(self.folder, safe)
        os.makedirs(folder, exist_ok=True)
        stamp = time.strftime('%Y%m%d_%H%M%S', time.localtime(now if now is not None else time.time()))
        path = os.path.join(folder, f'trig_{stamp}_{safe}_{int(round(score * 100)):03d}.wav')
        with wave.open(path, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sample_rate)
            w.writeframes(self.buffer.tobytes())
        self._prune(folder)
        return path

    def _prune(self, folder):
        files = sorted(f for f in os.listdir(folder) if f.endswith('.wav'))
        for old in files[:max(0, len(files) - self.max_files)]:
            try:
                os.remove(os.path.join(folder, old))
            except OSError:
                pass


def default_folder(config_dir):
    """Where the detector stores its clips: next to the wizard's workspace (git-ignored)."""
    return os.path.join(str(config_dir), 'wakeword_workspace', 'detections')
