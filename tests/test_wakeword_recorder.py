"""Everyday-audio collection (AmbientCollector) and the stable hold-out split. No microphone needed."""
import os
import sys

import pytest

np = pytest.importorskip('numpy')
sf = pytest.importorskip('soundfile')
pytest.importorskip('scipy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wakeword_trainer import features as F  # noqa: E402
from wakeword_trainer.recorder import AmbientCollector  # noqa: E402
from wakeword_trainer.workspace import Project, Workspace  # noqa: E402

SR = 16000


def _noise(seconds, level, seed=0):
    return (np.random.default_rng(seed).standard_normal(int(seconds * SR)) * level).astype(np.float32)


def test_keeps_only_clips_louder_than_the_room(tmp_path):
    c = AmbientCollector(str(tmp_path), 'env')
    c.feed(_noise(30, 0.002))                    # 30 s of quiet room: calibrates, nothing is kept
    assert c.saved == 0 and c.seen == 15
    c.feed(_noise(4, 0.1, seed=1))               # two loud clips (a conversation)
    c.feed(_noise(10, 0.002, seed=2))            # quiet again
    assert c.saved == 2
    files = sorted(os.listdir(tmp_path))
    assert files == ['real_env_0000.wav', 'real_env_0001.wav']
    data, sr = sf.read(os.path.join(tmp_path, files[0]), dtype='float32')
    assert sr == SR and len(data) == 2 * SR


def test_buffers_partial_chunks_between_feeds(tmp_path):
    c = AmbientCollector(str(tmp_path), 'env')
    for _ in range(30):                          # many tiny writes, like a microphone stream
        c.feed(_noise(1.0, 0.002))
    assert c.seen == 15 and c.saved == 0


def test_numbering_continues_after_a_restart(tmp_path):
    for i in range(3):
        sf.write(os.path.join(tmp_path, f'real_env_{i:04d}.wav'), _noise(2, 0.1), SR)
    c = AmbientCollector(str(tmp_path), 'env')
    c.feed(_noise(30, 0.002)); c.feed(_noise(2, 0.1, seed=3))
    assert 'real_env_0003.wav' in os.listdir(tmp_path)


def test_holdout_is_decided_by_name_not_by_position():
    names = [f'real_env_{i:04d}.wav' for i in range(300)]
    held = {n for n in names if F.is_real_holdout(n)}
    assert 70 < len(held) < 130                  # about one third
    # adding more recordings never moves an existing clip between train and hold-out
    more = names + [f'real_env_{i:04d}.wav' for i in range(300, 400)]
    assert held == {n for n in more[:300] if F.is_real_holdout(n)}


def test_split_files_uses_the_stable_holdout(tmp_path):
    ws = Workspace(tmp_path / 'p', Project(word='Bruninha', language='pt'))
    for i in range(60):
        sf.write(os.path.join(ws.real_neg, f'real_env_{i:04d}.wav'), _noise(0.2, 0.01), SR)
    files = F.split_files(ws)
    assert len(files['train_real_neg']) + len(files['hold_real_neg']) == 60
    assert not set(files['train_real_neg']) & set(files['hold_real_neg'])
    assert all(F.is_real_holdout(f) for f in files['hold_real_neg'])
