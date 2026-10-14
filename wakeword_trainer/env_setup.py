"""A separate Python environment for training, so GLaSSIST itself does not pull in PyTorch.

Created on demand in <config dir>/wakeword_trainer/venv with CPU-only PyTorch (the network is tiny:
a GPU does not help; feature extraction on the CPU is the slow part).
"""
import os
import shutil
import subprocess
import sys

REQUIREMENTS = ['numpy<2.3', 'scipy', 'soundfile', 'onnx', 'onnxruntime', 'openwakeword==0.6.0',
                'edge-tts', 'tqdm']
TORCH_CPU_INDEX = 'https://download.pytorch.org/whl/cpu'
SUPPORTED = ((3, 9), (3, 12))       # PyTorch/openWakeWord wheels exist for these Python versions


def venv_dir(root):
    return os.path.join(root, 'venv')


def trainer_python(root):
    sub = 'Scripts' if os.name == 'nt' else 'bin'
    exe = 'python.exe' if os.name == 'nt' else 'python'
    return os.path.join(venv_dir(root), sub, exe)


def ready_marker(root):
    return os.path.join(venv_dir(root), '.glassist-trainer-ready')


def is_ready(root):
    return os.path.exists(trainer_python(root)) and os.path.exists(ready_marker(root))


def _version_ok(cmd):
    try:
        out = subprocess.run(cmd + ['-c', 'import sys;print(sys.version_info[0], sys.version_info[1])'],
                             capture_output=True, text=True, timeout=20).stdout.split()
        return SUPPORTED[0] <= (int(out[0]), int(out[1])) <= SUPPORTED[1]
    except Exception:
        return False


def find_python():
    """A Python 3.9-3.12 interpreter to build the environment with (command list), or None."""
    candidates = []
    if not getattr(sys, 'frozen', False):
        candidates.append([sys.executable])
    if os.name == 'nt':
        candidates += [['py', f'-3.{v}'] for v in (12, 11, 10, 9)]
    candidates += [[f'python3.{v}'] for v in (12, 11, 10, 9)] + [['python3'], ['python']]
    for cmd in candidates:
        if shutil.which(cmd[0]) and _version_ok(cmd):
            return cmd
    return None


def _run(cmd, log):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace')
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            log(line)
    if proc.wait() != 0:
        raise RuntimeError(f'command failed ({proc.returncode}): {" ".join(cmd[:4])} ...')


def create(root, log=print):
    """Create the environment (idempotent). Raises RuntimeError with a readable message."""
    if is_ready(root):
        return
    base = find_python()
    if base is None:
        raise RuntimeError('Python 3.9 to 3.12 was not found. Install Python 3.11 (python.org) and try again.')
    os.makedirs(root, exist_ok=True)
    log('Creating the training environment...')
    _run(base + ['-m', 'venv', venv_dir(root)], log)
    py = trainer_python(root)
    _run([py, '-m', 'pip', 'install', '--upgrade', 'pip'], log)
    log('Installing PyTorch (CPU)...')
    if sys.platform == 'darwin':
        _run([py, '-m', 'pip', 'install', 'torch'], log)
    else:
        _run([py, '-m', 'pip', 'install', 'torch', '--index-url', TORCH_CPU_INDEX], log)
    log('Installing audio and TTS tools...')
    _run([py, '-m', 'pip', 'install'] + REQUIREMENTS, log)
    log('Downloading the openWakeWord base models...')
    _run([py, '-c', 'import openwakeword; openwakeword.utils.download_models()'], log)
    with open(ready_marker(root), 'w', encoding='utf-8') as f:
        f.write('ok')
    log('Training environment ready.')
