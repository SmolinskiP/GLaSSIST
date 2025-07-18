"""
Pytest configuration and fixtures for GLaSSIST tests.
"""
import pytest
import os
import sys
import tempfile
import shutil
from unittest.mock import Mock, patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)

@pytest.fixture
def mock_env_vars():
    """Mock environment variables for testing."""
    return {
        'HA_HOST': 'localhost:8123',
        'HA_TOKEN': 'test_token_123',
        'HA_SAMPLE_RATE': '16000',
        'HA_CHANNELS': '1',
        'HA_VAD_MODE': '3',
        'HA_HOTKEY': 'ctrl+shift+h',
        'HA_WAKE_WORD_ENABLED': 'true',
        'HA_WAKE_WORD_MODELS': 'alexa,jarvis',
        'HA_WAKE_WORD_THRESHOLD': '0.5',
        'HA_ANIMATIONS_ENABLED': 'true',
        'DEBUG': 'false'
    }

@pytest.fixture
def mock_pyaudio():
    """Mock PyAudio for testing."""
    with patch('pyaudio.PyAudio') as mock_audio:
        mock_instance = Mock()
        mock_audio.return_value = mock_instance
        mock_instance.get_device_count.return_value = 2
        mock_instance.get_device_info_by_index.return_value = {
            'name': 'Test Microphone',
            'maxInputChannels': 1,
            'defaultSampleRate': 16000.0
        }
        mock_instance.open.return_value = Mock()
        yield mock_instance

@pytest.fixture
def mock_websocket():
    """Mock websocket for testing."""
    with patch('websockets.connect') as mock_connect:
        mock_ws = Mock()
        mock_connect.return_value = mock_ws
        mock_ws.recv.return_value = '{"type": "auth_required"}'
        mock_ws.send = Mock()
        yield mock_ws

@pytest.fixture
def mock_openwakeword():
    """Mock OpenWakeWord for testing."""
    with patch('openwakeword.model.Model') as mock_model:
        mock_instance = Mock()
        mock_model.return_value = mock_instance
        mock_instance.predict.return_value = {'alexa': 0.3, 'jarvis': 0.7}
        mock_instance.prediction_buffer = {'alexa': [0.1, 0.2, 0.3], 'jarvis': [0.5, 0.6, 0.7]}
        yield mock_instance

@pytest.fixture
def mock_webview():
    """Mock webview for testing."""
    with patch('webview.create_window') as mock_create:
        mock_window = Mock()
        mock_create.return_value = mock_window
        yield mock_window