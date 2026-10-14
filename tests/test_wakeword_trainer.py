"""Tests for the pure-Python parts of the wake-word trainer (no NumPy/PyTorch needed)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wakeword_trainer import confusables as C  # noqa: E402
from wakeword_trainer import languages as L  # noqa: E402
from wakeword_trainer.workspace import Project, Workspace, slugify  # noqa: E402


def test_shipped_languages_are_valid():
    codes = dict(L.available_languages())
    assert {'pt', 'en', 'es'} <= set(codes)
    for code in codes:
        corpus = L.load_corpus(code)
        assert len(corpus['words']) > 50 and len(corpus['phrases']) > 30
        assert all('{w}' in c for c in corpus['carriers'])
        assert corpus['edge_locales']


def test_corpus_missing_key_is_reported(tmp_path):
    bad = tmp_path / 'bad.json'
    bad.write_text('{"name": "x"}', encoding='utf-8')
    with pytest.raises(KeyError):
        L.load_corpus(str(bad))


@pytest.mark.parametrize('text,expected', [
    ('Bruninha!', 'bruninha'), ('Ôi, Zé', 'oi_ze'), ('  Hey  Jarvis ', 'hey_jarvis'), ('???', 'my_wake_word'),
])
def test_slugify(text, expected):
    assert slugify(text) == expected


def test_normalize_strips_accents_and_case():
    assert C.normalize('Ôi, Zé!') == 'oi ze'
    assert C.similarity('Bruna', 'bruna') == 1.0


def test_confusables_exclude_the_word_and_near_twins():
    corpus = L.load_corpus('pt')
    words = corpus['words'] + ['Bruninho', 'Bruninha', 'Bruninhas']
    picks = C.pick_confusables('Bruninha', words)
    norm = [C.normalize(p) for p in picks]
    assert 'bruninha' not in norm
    assert 'bruninho' not in norm        # near-twin: not a useful negative
    assert any(p.endswith('inha') for p in picks)   # words ending alike are the hard negatives


def test_fragments_and_positive_phrases():
    assert C.fragments('Bruninha') == ['Brun', 'inha']
    assert C.fragments('ok') == []
    pos = C.positive_phrases('Bruninha', ['ei', 'oi'])
    assert 'Bruninha' in pos and 'ei Bruninha' in pos and len(pos) == len(set(pos))


@pytest.mark.parametrize('code,word', [('pt', 'Bruninha'), ('en', 'Jarvis'), ('es', 'Casita')])
def test_negatives_never_contain_the_wake_word(code, word):
    corpus = L.load_corpus(code)
    negatives = C.negative_phrases(word, corpus)
    assert len(negatives) > 200
    assert all(not C.contains_word(text, word) for text, _ in negatives)
    assert all(weight >= 1 for _, weight in negatives)


def test_negatives_are_deterministic():
    corpus = L.load_corpus('pt')
    assert C.negative_phrases('Bruninha', corpus) == C.negative_phrases('Bruninha', corpus)


def test_install_model_adds_to_list_and_enables(tmp_path):
    from wakeword_trainer.install import install_model, list_models
    model = tmp_path / 'out' / 'bruninha.onnx'
    model.parent.mkdir()
    model.write_bytes(b'onnx')
    env = tmp_path / '.env'
    env.write_text('HA_HOST=x\nHA_WAKE_WORD_ENABLED=false\nHA_WAKE_WORD_MODELS=alexa\n', encoding='utf-8')
    result = install_model(str(model), str(tmp_path / 'models'), str(env), 'bruninha')
    assert result['models'] == ['alexa', 'bruninha']
    assert (tmp_path / 'models' / 'bruninha.onnx').read_bytes() == b'onnx'
    text = env.read_text(encoding='utf-8')
    assert 'HA_HOST=x' in text and 'HA_WAKE_WORD_ENABLED=true' in text
    assert list_models(str(env)) == ['alexa', 'bruninha']
    # idempotent, and replace keeps only the new model
    assert install_model(str(model), str(tmp_path / 'models'), str(env), 'bruninha')['models'] == ['alexa', 'bruninha']
    assert install_model(str(model), str(tmp_path / 'models'), str(env), 'bruninha', replace=True)['models'] == ['bruninha']


def test_install_model_creates_env_when_missing(tmp_path):
    from wakeword_trainer.install import install_model
    model = tmp_path / 'm.onnx'
    model.write_bytes(b'x')
    env = tmp_path / 'new.env'
    install_model(str(model), str(tmp_path / 'models'), str(env), 'm')
    assert 'HA_WAKE_WORD_MODELS=m' in env.read_text(encoding='utf-8')


def test_workspace_layout_and_project_roundtrip(tmp_path):
    ws = Workspace(tmp_path / 'proj', Project(word='Bruninha', language='pt'))
    ws.save_project()
    assert ws.project.model_name == 'bruninha'
    assert os.path.isdir(ws.real_pos) and os.path.isdir(ws.test_pos)
    again = Workspace(tmp_path / 'proj')
    assert again.project == ws.project
    assert again.summary()['real_pos'] == 0 and again.summary()['model'] is None
