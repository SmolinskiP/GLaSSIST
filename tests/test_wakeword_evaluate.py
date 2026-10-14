"""The verdict shown by the wizard (pure logic, no audio)."""
import os
import sys

pytest = __import__('pytest')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# evaluate.py imports numpy/soundfile at module level: skip when they are not installed
np = pytest.importorskip('numpy')
pytest.importorskip('soundfile')
from wakeword_trainer.evaluate import MIN_CLIPS_FOR_GOOD, per_hour, verdict  # noqa: E402


def _result(pos_ok, pos_n, neg_false, neg_n):
    return {'test_pos': {'clips': pos_n, 'above': {'0.5': pos_ok}},
            'hold_real_neg': {'clips': neg_n, 'above': {'0.5': neg_false}}}


def test_good_needs_a_clean_result_on_enough_everyday_clips():
    v = verdict(_result(29, 30, 0, 80))
    assert v['level'] == 'good' and v['reasons'] == []
    assert v['false_per_hour'] == 0


def test_a_small_sample_can_never_be_good():
    v = verdict(_result(30, 30, 0, 20))                       # perfect, but only 20 everyday clips
    assert v['level'] == 'ok'
    assert any('everyday clips were checked' in r and 'Improve' in r for r in v['reasons'])
    assert verdict(_result(30, 30, 0, MIN_CLIPS_FOR_GOOD - 1))['level'] == 'ok'
    assert verdict(_result(30, 30, 0, MIN_CLIPS_FOR_GOOD))['level'] == 'good'


def test_false_triggers_are_judged_strictly_because_it_listens_all_day():
    assert verdict(_result(30, 30, 1, 100))['level'] == 'good'      # 1%
    assert verdict(_result(30, 30, 5, 100))['level'] == 'ok'        # 5%
    v = verdict(_result(52, 53, 2, 20))                             # the real "bruna" case: 10%
    assert v['level'] == 'poor'
    assert '2 of 20 normal-speech clips triggered it' in v['reasons']


def test_many_false_triggers_or_missed_word_is_poor():
    assert verdict(_result(30, 30, 40, 100))['level'] == 'poor'
    assert verdict(_result(20, 30, 0, 100))['level'] == 'poor'      # only 67% recognized
    assert verdict(_result(27, 30, 0, 100))['level'] == 'ok'        # 90% recognized


def test_missing_data_is_reported_not_hidden():
    v = verdict(_result(0, 0, 0, 100))
    assert v['level'] == 'ok' and 'no test recordings of your voice were found' in v['reasons']
    v = verdict(_result(30, 30, 0, 0))
    assert v['level'] == 'ok' and any('false triggers are unknown' in r for r in v['reasons'])


def test_per_hour_estimate():
    assert per_hour(0, 50) == 0
    assert per_hour(1, 100) == pytest.approx(18.0)       # 1% of 2-second clips ~ 18 per hour of sound
    assert per_hour(1, 0) is None
