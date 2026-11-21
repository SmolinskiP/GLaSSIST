"""Optional detection clips: ring buffer, background writer, and the hooks in both detection loops."""
import asyncio
import os
import threading
import time
import wave
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest

import detection_clips
from detection_clips import DetectionClipRecorder
from multi_room import MultiRoomManager, RoomConfig

SR = 16000


@pytest.fixture(autouse=True)
def clean_ha_env(monkeypatch):
    for key in [k for k in os.environ if k.startswith('HA_')]:
        monkeypatch.delenv(key)


def _read(path):
    with wave.open(path, 'rb') as w:
        assert w.getnchannels() == 1 and w.getframerate() == SR and w.getsampwidth() == 2
        return np.frombuffer(w.readframes(w.getnframes()), np.int16)


def test_off_by_default_and_on_with_the_setting(monkeypatch):
    assert detection_clips.from_env() is None
    monkeypatch.setenv('HA_WAKE_WORD_SAVE_DETECTIONS', 'true')
    assert isinstance(detection_clips.from_env(), DetectionClipRecorder)


def test_ring_buffer_keeps_the_last_seconds_in_order(tmp_path):
    rec = DetectionClipRecorder(tmp_path, seconds=1)                # 16000 samples
    rec.push(np.arange(0, 10000, dtype=np.int16))                   # not full yet
    assert np.array_equal(rec._snapshot(), np.arange(0, 10000, dtype=np.int16))
    rec.push(np.arange(10000, 25000, dtype=np.int16))               # wraps: keeps the last 16000
    assert np.array_equal(rec._snapshot(), np.arange(9000, 25000, dtype=np.int16))
    rec.push(np.arange(0, 20000, dtype=np.int16))                   # one chunk larger than the buffer
    assert np.array_equal(rec._snapshot(), np.arange(4000, 20000, dtype=np.int16))


def test_nothing_is_written_when_there_is_too_little_audio(tmp_path):
    rec = DetectionClipRecorder(tmp_path)
    rec.push(np.zeros(SR // 2, np.int16))
    assert rec.save('bruna', 0.9) is False
    assert not os.listdir(tmp_path)


def test_clip_is_written_on_another_thread_with_a_safe_name(tmp_path):
    rec = DetectionClipRecorder(tmp_path)
    rec.push(np.full(3 * SR, 7, np.int16))
    writers = []
    real = rec._write
    rec._write = lambda *a: writers.append(threading.current_thread().name) or real(*a)
    assert rec.save('../evil name', 0.874, now=0) is True
    assert rec.flush()
    assert writers and writers[0] == 'detection-clips'            # never the detection thread
    (folder,) = os.listdir(tmp_path)
    assert folder == 'evilname'
    (name,) = os.listdir(tmp_path / folder)
    assert name.startswith('trig_') and name.endswith('_evilname_087.wav')
    assert len(_read(str(tmp_path / folder / name))) == 3 * SR


def test_saving_does_not_wait_for_slow_disk(tmp_path):
    rec = DetectionClipRecorder(tmp_path)
    rec.push(np.zeros(3 * SR, np.int16))
    release = threading.Event()
    real = rec._write
    rec._write = lambda *a: release.wait(5) and real(*a)
    start = time.time()
    for _ in range(20):                                           # more than the queue holds
        rec.save('bruna', 0.9)
    assert time.time() - start < 1.0                              # returned at once, extra clips dropped
    release.set()
    assert rec.flush()


def test_old_clips_are_pruned(tmp_path):
    rec = DetectionClipRecorder(tmp_path, max_files=3)
    rec.push(np.zeros(2 * SR, np.int16))
    for i in range(5):
        rec.save('bruna', 0.9, now=1000 * i)
        assert rec.flush()
    files = sorted(os.listdir(tmp_path / 'bruna'))
    assert len(files) == 3


def test_a_failing_write_does_not_break_detection(tmp_path):
    rec = DetectionClipRecorder(tmp_path / 'file')
    (tmp_path / 'file').write_text('not a folder')               # makedirs will fail
    rec.push(np.zeros(2 * SR, np.int16))
    assert rec.save('bruna', 0.9) is True
    assert rec.flush()


# ---- hooks
def test_detector_feeds_and_saves_only_when_enabled(monkeypatch, tmp_path):
    import wake_word_detector
    clips = Mock()
    with patch('detection_clips.from_env', return_value=clips), \
         patch.object(wake_word_detector.WakeWordDetector, '_init_openwakeword'):
        detector = wake_word_detector.WakeWordDetector()
    detector.selected_models = ['bruna']
    detector.detection_threshold = 0.5
    audio = np.zeros(1280, np.int16)
    detector.record_audio(audio)
    clips.push.assert_called_once_with(audio)
    with patch('wake_word_detector.time.sleep'):
        detector._process_predictions({'bruna': 0.2})
        clips.save.assert_not_called()
        detector._process_predictions({'bruna': 0.9, 'other': 0.99})
    clips.save.assert_called_once_with('bruna', 0.9)


def test_detector_without_the_setting_has_no_recorder():
    import wake_word_detector
    with patch.object(wake_word_detector.WakeWordDetector, '_init_openwakeword'):
        detector = wake_word_detector.WakeWordDetector()
    assert detector.clips is None
    detector.record_audio(np.zeros(10, np.int16))              # no-ops
    detector.record_detection('bruna', 0.9)


def test_multi_room_mode_feeds_and_saves_too():
    manager = MultiRoomManager([RoomConfig('a', 'A', 1, 2, 6053)], Mock())
    manager._loop = Mock()
    stream = Mock()
    chunks = [b'\x01\x00' * 1280, b'\x02\x00' * 1280]

    def read(*a, **k):
        if not chunks:
            manager._stop.set()
            return b'\x00\x00' * 1280
        return chunks.pop(0)
    stream.read.side_effect = read
    detector = Mock(detection_threshold=0.5, selected_models=['bruna'])
    detector.model.predict.side_effect = [{'bruna': 0.2}, {'bruna': 0.8, 'x': 0.9}, {'bruna': 0.1}]
    future = Mock()
    future.result.return_value = True
    with patch('asyncio.run_coroutine_threadsafe', return_value=future), patch.object(manager, '_feed', Mock()):
        manager._capture(manager.rooms[0], stream, detector, Mock())
    assert detector.record_audio.call_count == 3                 # every chunk, listening or not
    detector.record_detection.assert_called_once_with('bruna', 0.8)
