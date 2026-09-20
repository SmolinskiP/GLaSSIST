"""Configure application logging once, with bounded UTF-8 file rotation."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import threading

MAX_LOG_BYTES = 2 * 1024 * 1024
LOG_BACKUPS = 3
_lock = threading.Lock()


def configure_logging(debug_enabled, log_dir, root=None):
    root = root if root is not None else logging.getLogger()
    with _lock:
        if any(getattr(handler, '_glassist_handler', False) for handler in root.handlers):
            return
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        console._glassist_handler = True
        root.addHandler(console)
        root.setLevel(logging.INFO)
        if debug_enabled:
            try:
                directory = Path(log_dir)
                directory.mkdir(parents=True, exist_ok=True)
                handler = RotatingFileHandler(
                    directory / 'glasssist.log', maxBytes=MAX_LOG_BYTES,
                    backupCount=LOG_BACKUPS, encoding='utf-8', delay=True)
                handler.setFormatter(formatter)
                handler._glassist_handler = True
                root.addHandler(handler)
            except OSError:
                root.warning('Cannot initialize file logging; console logging remains available', exc_info=True)
