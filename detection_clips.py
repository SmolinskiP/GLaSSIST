"""Optionally keep a short audio clip of every wake word detection.

A detection that was a mistake is the best possible training example for a custom wake word: it is
exactly the sound that fools the model. When HA_WAKE_WORD_SAVE_DETECTIONS=true the detector keeps the
last few seconds of audio in memory (a ring buffer, never written to disk) and, only when it triggers,
hands a copy to a background thread that writes it to
``<config dir>/detections/<model>/trig_<date>_<time>_<model>_<confidence>.wav``.

The detection loop only copies a small array and puts it in a queue, so file I/O can never delay
audio processing. Off by default; clips stay on this computer.
"""
import os
import queue
import threading
import time
import wave

import numpy as np

import utils

logger = utils.setup_logger()

SAMPLE_RATE = 16000
MIN_SECONDS = 1.0           # under this there is nothing useful to learn from
_ON = ('true', '1', 'yes', 'y', 't')


class DetectionClipRecorder:
    def __init__(self, folder, seconds=3.0, max_files=300, sample_rate=SAMPLE_RATE):
        self.folder = str(folder)
        self.sample_rate = sample_rate
        self.max_files = max_files
        self._ring = np.zeros(int(seconds * sample_rate), np.int16)
        self._filled = 0                      # samples written so far, capped at the ring size
        self._pos = 0                         # next write position
        self._queue = queue.Queue(maxsize=8)  # a burst of detections drops clips instead of blocking
        self._worker = None
        self._worker_lock = threading.Lock()

    def push(self, chunk):
        """Add int16 audio to the in-memory ring buffer. Cheap: no allocation, no disk."""
        chunk = np.asarray(chunk, np.int16)
        n = len(chunk)
        size = len(self._ring)
        if n >= size:
            self._ring[:] = chunk[-size:]
            self._pos, self._filled = 0, size
            return
        end = self._pos + n
        if end <= size:
            self._ring[self._pos:end] = chunk
        else:
            first = size - self._pos
            self._ring[self._pos:] = chunk[:first]
            self._ring[:n - first] = chunk[first:]
        self._pos = end % size
        self._filled = min(size, self._filled + n)

    def _snapshot(self):
        if self._filled < len(self._ring):
            return self._ring[:self._filled].copy()
        return np.concatenate([self._ring[self._pos:], self._ring[:self._pos]])

    def save(self, model_name, score, now=None):
        """Queue the buffered audio for writing. Returns False when skipped (too little audio or busy)."""
        if self._filled < MIN_SECONDS * self.sample_rate:
            return False
        item = (self._snapshot(), model_name, float(score), time.time() if now is None else now)
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            logger.debug('Detection clip skipped: writer is busy')
            return False
        self._ensure_worker()
        return True

    def _ensure_worker(self):
        with self._worker_lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run, name='detection-clips', daemon=True)
                self._worker.start()

    def _run(self):
        while True:
            try:
                item = self._queue.get(timeout=5)
            except queue.Empty:
                return                        # restarted on the next detection
            try:
                self._write(*item)
            except Exception as e:
                logger.warning(f'Could not save detection clip: {e}')

    def flush(self, timeout=5.0):
        """Wait until queued clips are written (for tests and shutdown)."""
        end = time.time() + timeout
        while time.time() < end:
            if self._queue.empty() and self._queue.unfinished_tasks == 0:
                return True
            time.sleep(0.01)
        return False

    def _write(self, audio, model_name, score, now):
        try:
            safe = ''.join(c for c in model_name if c.isalnum() or c in '_-') or 'model'
            folder = os.path.join(self.folder, safe)
            os.makedirs(folder, exist_ok=True)
            stamp = time.strftime('%Y%m%d_%H%M%S', time.localtime(now))
            path = os.path.join(folder, f'trig_{stamp}_{safe}_{int(round(score * 100)):03d}.wav')
            with wave.open(path, 'wb') as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(self.sample_rate)
                w.writeframes(audio.tobytes())
            self._prune(folder)
            return path
        finally:
            self._queue.task_done()

    def _prune(self, folder):
        files = sorted(f for f in os.listdir(folder) if f.endswith('.wav'))
        for old in files[:max(0, len(files) - self.max_files)]:
            try:
                os.remove(os.path.join(folder, old))
            except OSError:
                pass


def default_folder():
    import platform_utils
    return os.path.join(str(platform_utils.get_config_dir()), 'detections')


def from_env():
    """A recorder when HA_WAKE_WORD_SAVE_DETECTIONS is on, else None (the default)."""
    if str(utils.get_env('HA_WAKE_WORD_SAVE_DETECTIONS', 'false')).lower() not in _ON:
        return None
    try:
        return DetectionClipRecorder(default_folder())
    except Exception as e:
        logger.warning(f'Could not enable detection clips: {e}')
        return None
