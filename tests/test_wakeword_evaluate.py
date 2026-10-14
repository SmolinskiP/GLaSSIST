"""The verdict shown by the wizard (pure logic, no audio)."""
import os
import sys

pytest = __import__('pytest')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# evaluate.py imports numpy/soundfile at module level: skip when they are not installed
np = pytest.importorskip('numpy')
pytest.importorskip('soundfile')
from wakeword_trainer.evaluate import verdict  # noqa: E402


def _result(pos_ok, pos_n, neg_false, neg_n):
    return {'test_pos': {'clips': pos_n, 'above': {'0.5': pos_ok}},
            'hold_real_neg': {'clips': neg_n, 'above': {'0.5': neg_false}}}


def test_good_when_everything_is_clean():
    v = verdict(_result(29, 30, 0, 60))
    assert v['level'] == 'good' and v['reasons'] == []


def test_few_false_triggers_are_usable_not_poor_and_report_counts():
    v = verdict(_result(52, 53, 2, 20))
    assert v['level'] == 'ok'
    assert '2 of 20 normal-speech clips triggered it' in v['reasons']
    assert any('not very reliable' in r for r in v['reasons'])      # small sample is disclosed


def test_many_false_triggers_or_missed_word_is_poor():
    assert verdict(_result(30, 30, 10, 40))['level'] == 'poor'      # 25% false
    assert verdict(_result(20, 30, 0, 60))['level'] == 'poor'       # only 67% recognized


def test_missing_exam_recordings_are_reported():
    v = verdict(_result(0, 0, 0, 60))
    assert v['level'] == 'ok' and 'no test recordings of your voice were found' in v['reasons']
