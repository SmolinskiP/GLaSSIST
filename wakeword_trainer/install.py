"""Put a finished model into GLaSSIST: copy it to models/ and add it to HA_WAKE_WORD_MODELS."""
import os
import re
import shutil


def _read_env(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return f.read().splitlines()


def _set_key(lines, key, value):
    pattern = re.compile(rf'^\s*{re.escape(key)}\s*=')
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = f'{key}={value}'
            return
    lines.append(f'{key}={value}')


def _get_key(lines, key, default=''):
    pattern = re.compile(rf'^\s*{re.escape(key)}\s*=(.*)$')
    for line in lines:
        m = pattern.match(line)
        if m:
            return m.group(1).strip()
    return default


def list_models(env_path):
    lines = _read_env(env_path)
    return [m.strip() for m in _get_key(lines, 'HA_WAKE_WORD_MODELS').split(',') if m.strip()]


def install_model(model_path, models_dir, env_path, name, enable=True, replace=False):
    """Copy `model_path` to `models_dir/<name>.onnx` and register it in the .env file.

    replace=True makes it the only active wake word; otherwise it is added to the existing list.
    Returns {'file': ..., 'models': [...]}.
    """
    if not os.path.isfile(model_path):
        raise FileNotFoundError(model_path)
    os.makedirs(models_dir, exist_ok=True)
    dest = os.path.join(models_dir, f'{name}.onnx')
    if os.path.abspath(model_path) != os.path.abspath(dest):
        shutil.copyfile(model_path, dest)
    lines = _read_env(env_path)
    models = [] if replace else [m.strip() for m in _get_key(lines, 'HA_WAKE_WORD_MODELS', '').split(',') if m.strip()]
    if name not in models:
        models.append(name)
    _set_key(lines, 'HA_WAKE_WORD_MODELS', ','.join(models))
    if enable:
        _set_key(lines, 'HA_WAKE_WORD_ENABLED', 'true')
    tmp = env_path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    os.replace(tmp, env_path)
    return {'file': dest, 'models': models}
