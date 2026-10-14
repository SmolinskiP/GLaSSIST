"""Detection clips (TriggerRecorder): kept in memory, written only on a detection."""
import os
import sys
import wave

import pytest

np = pytest.importorskip('numpy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wakeword_trainer.capture import TriggerRecorder, default_folder  # noqa: E402

SR = 16000


def _chunk(seconds, value=1000):
    return np.full(int(seconds * SR), value, np.int16)


def test_nothing_is_written_until_a_detection(tmp_path):
    rec = TriggerRecorder(str(tmp_path))
    for _ in range(50):
        rec.push(_chunk(0.08))
    assert os.listdir(tmp_path) == []             # audio only lives in memory


def test_saves_the_last_three_seconds_as_a_wav(tmp_path):
    rec = TriggerRecorder(str(tmp_path), seconds=3.0)
    rec.push(_chunk(2.0, 1))                      # older audio that must be dropped
    rec.push(_chunk(3.0, 2))
    path = rec.save('bruna', 0.987, now=0)
    assert os.path.dirname(path).endswith('bruna') and path.endswith('_bruna_099.wav')
    with wave.open(path, 'rb') as w:
        assert w.getframerate() == SR and w.getnchannels() == 1 and w.getnframes() == 3 * SR
        data = np.frombuffer(w.readframes(w.getnframes()), np.int16)
    assert set(data.tolist()) == {2}              # only the last 3 s are kept


def test_too_little_audio_is_not_saved(tmp_path):
    rec = TriggerRecorder(str(tmp_path))
    rec.push(_chunk(0.5))
    assert rec.save('bruna', 0.9) is None


def test_model_names_cannot_escape_the_folder(tmp_path):
    rec = TriggerRecorder(str(tmp_path))
    rec.push(_chunk(2.0))
    path = rec.save('../../evil name', 0.9, now=0)
    assert os.path.abspath(path).startswith(os.path.abspath(tmp_path))


def test_old_clips_are_pruned(tmp_path):
    rec = TriggerRecorder(str(tmp_path), max_files=3)
    rec.push(_chunk(2.0))
    import time
    times = [1_700_000_000 + 1000 * i for i in range(6)]
    for t in times:
        rec.save('bruna', 0.9, now=t)
    kept = sorted(os.listdir(tmp_path / 'bruna'))
    stamps = [time.strftime('%Y%m%d_%H%M%S', time.localtime(t)) for t in times]
    assert len(kept) == 3
    assert all(any(s in name for name in kept) for s in stamps[-3:])         # the newest three survive
    assert not any(stamps[0] in name for name in kept)                       # the oldest was pruned


def test_default_folder_is_inside_the_ignored_workspace(tmp_path):
    assert default_folder(tmp_path) == os.path.join(str(tmp_path), 'wakeword_workspace', 'detections')
