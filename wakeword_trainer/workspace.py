"""Folder layout and settings of one wake-word training project."""
import json
import os
import re
from dataclasses import dataclass, asdict


def slugify(word):
    """Safe model file name: letters, digits and underscores (what GLaSSIST expects)."""
    import unicodedata
    text = unicodedata.normalize('NFKD', word).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^A-Za-z0-9]+', '_', text).strip('_').lower()
    return text or 'my_wake_word'


@dataclass
class Project:
    word: str                 # what the user says, e.g. "Bruninha"
    language: str             # corpus code ("pt") or a path to a custom corpus JSON
    model_name: str = ''      # file name without extension

    def __post_init__(self):
        if not self.model_name:
            self.model_name = slugify(self.word)


class Workspace:
    """data/pos, data/neg (synthetic) · data/real_pos, real_neg, test_pos (recorded) · out/"""

    def __init__(self, root, project=None):
        self.root = os.path.abspath(root)
        self.project = project or self.load_project()
        for d in (self.pos, self.neg, self.real_pos, self.real_neg, self.test_pos, self.out):
            os.makedirs(d, exist_ok=True)

    def _p(self, *parts):
        return os.path.join(self.root, *parts)

    @property
    def pos(self): return self._p('data', 'pos')
    @property
    def neg(self): return self._p('data', 'neg')
    @property
    def real_pos(self): return self._p('data', 'real_pos')
    @property
    def real_neg(self): return self._p('data', 'real_neg')
    @property
    def test_pos(self): return self._p('data', 'test_pos')
    @property
    def ambient(self): return self._p('data', 'ambient.wav')
    @property
    def cache(self): return self._p('cache_features.pkl')
    @property
    def out(self): return self._p('out')
    @property
    def model_path(self): return os.path.join(self.out, f'{self.project.model_name}.onnx')
    @property
    def project_file(self): return self._p('project.json')

    def save_project(self):
        os.makedirs(self.root, exist_ok=True)
        with open(self.project_file, 'w', encoding='utf-8') as f:
            json.dump(asdict(self.project), f, ensure_ascii=False, indent=2)

    def load_project(self):
        with open(self.project_file, encoding='utf-8') as f:
            return Project(**json.load(f))

    def count(self, folder):
        return len([n for n in os.listdir(folder) if n.endswith('.wav')])

    def summary(self):
        return {
            'synthetic_pos': self.count(self.pos), 'synthetic_neg': self.count(self.neg),
            'real_pos': self.count(self.real_pos), 'real_neg': self.count(self.real_neg),
            'test_pos': self.count(self.test_pos), 'has_ambient': os.path.exists(self.ambient),
            'model': self.model_path if os.path.exists(self.model_path) else None,
        }
