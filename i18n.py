"""
Minimal i18n for GLaSSIST Desktop.

Translations live in locales/<code>.json as {"English text": "translated text"}.
The language is chosen with HA_LANGUAGE in .env (e.g. "pt_BR"); "en" or an unknown
code leaves every text untouched.

Instead of touching every UI call, patch_flet() wraps the Flet controls so the
user-visible text arguments are translated when the control is built (and when
Text.value is assigned later). Texts with no translation stay in English.
"""
import json
import os
import re
import sys

LANGUAGES = {
    'en': 'English',
    'pt_BR': 'Português (Brasil)',
}

# PyInstaller unpacks bundled data under sys._MEIPASS; otherwise use the source folder.
_BASE_DIR = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.abspath(__file__))
_LOCALES_DIR = os.path.join(_BASE_DIR, 'locales')
_current = 'en'
_table = {}
_prefixes = []
_patterns = []
_patched = False
_initialized = False


def normalize(code):
    code = (code or 'en').strip().replace('-', '_')
    if code.lower() in ('pt', 'pt_br', 'ptbr'):
        return 'pt_BR'
    return code if code in LANGUAGES else 'en'


def set_language(code):
    """Load the translation table for `code` (falls back to English)."""
    global _current, _table, _prefixes, _patterns, _initialized
    _initialized = True
    _current = normalize(code)
    _table = {}
    _patterns = []
    if _current != 'en':
        path = os.path.join(_LOCALES_DIR, f'{_current}.json')
        try:
            with open(path, encoding='utf-8') as f:
                _table = json.load(f)
        except (OSError, ValueError):
            _table = {}
    # Keys ending in ": " (or "v") work as prefixes for dynamic texts such as "Current: 0.5".
    _prefixes = sorted(
        (k for k in _table if k.endswith((': ', ' v')) and len(k) > 2),
        key=len, reverse=True,
    )
    # Keys with "{}" are patterns for texts that embed values, e.g. "{} microphones found."
    _patterns = [
        (re.compile('^' + '(.+?)'.join(re.escape(part) for part in k.split('{}')) + '$', re.S), _table[k])
        for k in _table if '{}' in k
    ]


def get_language():
    return _current


def t(text):
    """Translate a UI string; returns it unchanged when there is no translation."""
    if not _initialized:
        init_from_env()
    if not isinstance(text, str) or not text or not _table:
        return text
    hit = _table.get(text)
    if hit is not None:
        return hit
    for prefix in _prefixes:
        if text.startswith(prefix):
            return _table[prefix] + text[len(prefix):]
    for regex, translated in _patterns:
        match = regex.match(text)
        if match:
            for value in match.groups():
                translated = translated.replace('{}', value, 1)
            return translated
    return text


_TEXT_KWARGS = ('text', 'label', 'hint_text', 'helper_text', 'tooltip', 'error_text')


def _wrap(base, positional_text=False, extra_kwargs=()):
    kwargs_to_translate = _TEXT_KWARGS + tuple(extra_kwargs)

    class Translated(base):
        def __init__(self, *args, **kwargs):
            if positional_text and args:
                args = (t(args[0]),) + tuple(args[1:])
            for key in kwargs_to_translate:
                if isinstance(kwargs.get(key), str):
                    kwargs[key] = t(kwargs[key])
            super().__init__(*args, **kwargs)

    Translated.__name__ = base.__name__
    Translated.__qualname__ = base.__qualname__
    return Translated


def patch_flet(ft):
    """Wrap Flet controls so their visible text goes through t(). Safe to call twice."""
    global _patched
    if _patched or _current == 'en':
        return
    _patched = True

    base_text = ft.Text

    class TranslatedText(base_text):
        def __init__(self, *args, **kwargs):
            if args and isinstance(args[0], str):
                args = (t(args[0]),) + tuple(args[1:])
            if isinstance(kwargs.get('value'), str):
                kwargs['value'] = t(kwargs['value'])
            for key in ('tooltip',):
                if isinstance(kwargs.get(key), str):
                    kwargs[key] = t(kwargs[key])
            super().__init__(*args, **kwargs)

        @property
        def value(self):
            return base_text.value.fget(self)

        @value.setter
        def value(self, v):
            base_text.value.fset(self, t(v) if isinstance(v, str) else v)

    TranslatedText.__name__ = 'Text'
    TranslatedText.__qualname__ = 'Text'
    ft.Text = TranslatedText

    for name in ('ElevatedButton', 'FilledButton', 'FilledTonalButton', 'TextButton', 'OutlinedButton'):
        base = getattr(ft, name, None)
        if base is not None:
            setattr(ft, name, _wrap(base, positional_text=True))
    for name in ('TextField', 'Dropdown', 'Checkbox', 'Switch', 'Slider', 'IconButton',
                 'Tab', 'Chip', 'ListTile', 'Radio', 'FloatingActionButton'):
        base = getattr(ft, name, None)
        if base is not None:
            setattr(ft, name, _wrap(base))
    option = getattr(getattr(ft, 'dropdown', None), 'Option', None)
    if option is not None:
        # Option(key, text): the first positional is the value key and must stay untouched;
        # only the label (second positional or text=) is translated.
        class TranslatedOption(option):
            def __init__(self, *args, **kwargs):
                if len(args) > 1 and isinstance(args[1], str):
                    args = (args[0], t(args[1])) + tuple(args[2:])
                if isinstance(kwargs.get('text'), str):
                    kwargs['text'] = t(kwargs['text'])
                super().__init__(*args, **kwargs)

        TranslatedOption.__name__ = option.__name__
        TranslatedOption.__qualname__ = option.__qualname__
        ft.dropdown.Option = TranslatedOption


def init_from_env():
    """Read HA_LANGUAGE (env or .env via utils) and load the table."""
    code = os.environ.get('HA_LANGUAGE')
    if not code:
        try:
            import utils
            code = utils.get_env('HA_LANGUAGE', 'en')
        except Exception:
            code = 'en'
    set_language(code)
    return _current
