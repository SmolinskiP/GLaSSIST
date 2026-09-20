import logging
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

import pytest

from logging_config import configure_logging


@pytest.fixture
def root():
    logger = logging.Logger('isolated-log-test')
    yield logger
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()


def test_repeated_and_concurrent_initialization_is_idempotent(tmp_path, root):
    external = logging.NullHandler()
    root.addHandler(external)
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: configure_logging(True, tmp_path, root), range(40)))
    assert len(root.handlers) == 3
    assert external in root.handlers
    root.info('one message')
    assert list(tmp_path.iterdir()) == [tmp_path / 'glasssist.log']
    assert (tmp_path / 'glasssist.log').read_text(encoding='utf-8').count('one message') == 1


def test_debug_disabled_creates_no_files(tmp_path, root):
    directory = tmp_path / 'logs'
    configure_logging(False, directory, root)
    root.info('console only')
    assert not directory.exists()
    assert len(root.handlers) == 1


def test_rotation_is_bounded_and_utf8(tmp_path, root):
    with patch('logging_config.MAX_LOG_BYTES', 200):
        configure_logging(True, tmp_path, root)
    for i in range(60):
        root.info('Głośniki — zażółć gęślą jaźń %s', i)
    assert {p.name for p in tmp_path.iterdir()} == {
        'glasssist.log', 'glasssist.log.1', 'glasssist.log.2', 'glasssist.log.3'}
    assert 'jaźń 59' in (tmp_path / 'glasssist.log').read_text(encoding='utf-8')
    for path in tmp_path.iterdir():
        path.read_text(encoding='utf-8')


def test_next_run_appends_to_same_file(tmp_path):
    for i in range(2):
        logger = logging.Logger(f'run-{i}')
        configure_logging(True, tmp_path, logger)
        logger.info('run %s', i)
        for handler in logger.handlers:
            handler.close()
    text = (tmp_path / 'glasssist.log').read_text(encoding='utf-8')
    assert 'run 0' in text and 'run 1' in text
    assert len(list(tmp_path.iterdir())) == 1


def test_unwritable_directory_keeps_console(tmp_path, root):
    with patch('logging_config.Path.mkdir', side_effect=PermissionError('test')), \
         patch.object(root, 'warning') as warning:
        configure_logging(True, tmp_path, root)
    warning.assert_called_once()
    assert len(root.handlers) == 1
