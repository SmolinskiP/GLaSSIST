"""Language corpora: text used to build negatives and the TTS voices (locales) to use."""
import json
import os
import sys

# PyInstaller unpacks bundled data under sys._MEIPASS; otherwise use the source folder.
_BASE = os.path.join(getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     'wakeword_trainer')
CORPORA_DIR = os.path.join(_BASE, 'corpora')


def available_languages():
    """[(code, display name)] for every corpus file shipped in corpora/."""
    out = []
    for name in sorted(os.listdir(CORPORA_DIR)):
        if name.endswith('.json'):
            code = name[:-5]
            try:
                out.append((code, load_corpus(code)['name']))
            except (OSError, ValueError, KeyError):
                continue
    return out


def load_corpus(code_or_path):
    """Load a corpus by language code (e.g. 'pt') or from a custom JSON file path."""
    path = code_or_path
    if not os.path.isfile(path):
        path = os.path.join(CORPORA_DIR, f'{code_or_path}.json')
    with open(path, encoding='utf-8') as f:
        corpus = json.load(f)
    for key in ('name', 'edge_locales', 'words', 'phrases', 'verbs', 'objects', 'carriers'):
        if key not in corpus:
            raise KeyError(f"corpus {code_or_path!r} is missing '{key}'")
    corpus.setdefault('wake_prefixes', [])
    return corpus
