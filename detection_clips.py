"""Optionally keep a short audio clip of every wake word detection.

A detection that was a mistake is the best possible training example for a custom wake word: it is
exactly the sound that fools the model. When HA_WAKE_WORD_SAVE_DETECTIONS=true the detector keeps the
last few seconds of audio in memory (a ring buffer, never written to disk) and, only when it triggers,
hands a copy to a background thread that writes it to
``<config dir>/detections/<model>/trig_<date>_<time>_<ms>[_<room>]_<model>_<confidence>.wav``.

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
COOLDOWN_SECONDS = 2.0      # one utterance can trigger several frames in a row


class DetectionClipRecorder:
    def __init__(self, folder, seconds=3.0, max_files=300, sample_rate=SAMPLE_RATE, label=''):
        self.folder = str(folder)
        self.sample_rate = sample_rate
        self.max_files = max_files
        self.label = _safe_name(label)
        self._last_save = {}                  # model -> time of the last queued clip
        self._ring = np.zeros(int(seconds * sample_rate), np.int16)
        self._filled = 0                      # samples written so far, capped at the ring size
        self._pos = 0                         # next write position
        self._queue = queue.Queue(maxsize=8)  # a burst of detections drops clips instead of blocking
        self._worker = None
        self._worker_lock = threading.Lock()

    def push(self, chunk):
        """Add int16 audio to the in-memory ring buffer. Cheap: no allocation, no disk."""
        try:
            self._push(chunk)
        except Exception as e:
            # A diagnostic feature must never stop wake word detection.
            logger.warning(f'Detection clip buffer failed: {e}')

    def _push(self, chunk):
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
        """Queue the buffered audio for writing.

        Returns False when skipped: too little audio, a repeat of the same utterance, a busy writer
        or an error (logged; detection keeps running).
        """
        try:
            now = time.time() if now is None else now
            if self._filled < MIN_SECONDS * self.sample_rate:
                return False
            if now - self._last_save.get(model_name, float('-inf')) < COOLDOWN_SECONDS:
                return False
            item = (self._snapshot(), model_name, float(score), now)
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                logger.debug('Detection clip skipped: writer is busy')
                return False
            self._last_save[model_name] = now
            self._ensure_worker()
            return True
        except Exception as e:
            logger.warning(f'Detection clip not saved: {e}')
            return False

    def _ensure_worker(self):
        with self._worker_lock:
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, name='detection-clips', daemon=True)
                self._worker.start()

    def _run(self):
        while True:
            item = self._queue.get()
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
            safe = _safe_name(model_name) or 'model'
            folder = os.path.join(self.folder, safe)
            os.makedirs(folder, exist_ok=True)
            stamp = time.strftime('%Y%m%d_%H%M%S', time.localtime(now)) + f'_{int(now * 1000) % 1000:03d}'
            room = f'_{self.label}' if self.label else ''
            base = f'trig_{stamp}{room}_{safe}_{int(round(score * 100)):03d}'
            for attempt in range(100):
                path = os.path.join(folder, f'{base}_{attempt}.wav' if attempt else f'{base}.wav')
                try:
                    # 'x' never overwrites a clip another room wrote in the same millisecond.
                    f = open(path, 'xb')
                    break
                except FileExistsError:
                    continue
            else:
                raise FileExistsError(path)
            with f, wave.open(f, 'wb') as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(self.sample_rate)
                w.writeframes(audio.tobytes())
            self._prune(folder)
            return path
        finally:
            self._queue.task_done()

    def _prune(self, folder):
        """Remove the oldest of our own clips; files the user added or renamed are never touched."""
        paths = [os.path.join(folder, f) for f in os.listdir(folder)
                 if f.startswith('trig_') and f.endswith('.wav')]
        paths.sort(key=lambda path: (os.path.getmtime(path), path))
        for old in paths[:max(0, len(paths) - self.max_files)]:
            try:
                os.remove(old)
            except OSError:
                pass


def _safe_name(name):
    """File-name-safe text: letters, digits, '_', '-' and inner dots (no '..' path tricks)."""
    return ''.join(c for c in str(name) if c.isalnum() or c in '_-.').strip('.').replace('..', '.')


def default_folder():
    import platform_utils
    return os.path.join(str(platform_utils.get_config_dir()), 'detections')


def from_env(label=''):
    """A recorder when HA_WAKE_WORD_SAVE_DETECTIONS is on, else None (the default)."""
    if not utils.get_env_bool('HA_WAKE_WORD_SAVE_DETECTIONS', False):
        return None
    try:
        return DetectionClipRecorder(default_folder(), label=label)
    except Exception as e:
        logger.warning(f'Could not enable detection clips: {e}')
        return None
