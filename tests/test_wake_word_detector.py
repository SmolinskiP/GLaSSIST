"""
Tests for wake_word_detector module.
"""
import pytest
import os
import sys
import numpy as np
from unittest.mock import Mock, patch
import wake_word_detector


@pytest.fixture(autouse=True)
def clean_ha_env(monkeypatch):
    """utils loads the real .env into os.environ at import; drop it so defaults apply."""
    for key in [k for k in os.environ if k.startswith('HA_')]:
        monkeypatch.delenv(key)


@pytest.fixture
def mock_model_class():
    """Fake openwakeword package so tests never import onnxruntime or load models."""
    package = Mock()
    with patch.dict(sys.modules, {'openwakeword': package, 'openwakeword.model': package.model}):
        yield package.model.Model


def make_detector(callback=None):
    return wake_word_detector.WakeWordDetector(callback)


def touch(directory, *names):
    for name in names:
        (directory / name).write_bytes(b'')


class TestWakeWordDetector:
    """Test cases for WakeWordDetector class."""

    @patch.dict('os.environ', {
        'HA_WAKE_WORD_ENABLED': 'true',
        'HA_WAKE_WORD_MODELS': 'alexa,jarvis',
        'HA_WAKE_WORD_THRESHOLD': '0.6'
    })
    def test_init_enabled(self):
        """Test WakeWordDetector initialization when enabled."""
        callback = Mock()

        with patch('wake_word_detector.WakeWordDetector._init_openwakeword') as mock_init:
            detector = make_detector(callback)

            assert detector.enabled is True
            assert detector.detection_callback == callback
            assert detector.detection_threshold == 0.6
            assert detector.selected_models == ['alexa', 'jarvis']
            assert detector.sample_rate == 16000
            mock_init.assert_called_once()

    def test_init_disabled(self):
        """Test WakeWordDetector initialization when disabled."""
        detector = make_detector()

        assert detector.enabled is False
        assert detector.model is None
        assert detector.is_running is False

    @patch.dict('os.environ', {
        'HA_WAKE_WORD_ENABLED': '1',
        'HA_WAKE_WORD_MODELS': 'alexa'
    })
    def test_init_boolean_parsing(self):
        """Test boolean parsing for different string values."""
        with patch('wake_word_detector.WakeWordDetector._init_openwakeword'):
            detector = make_detector()
            assert detector.enabled is True

    def test_get_selected_models_string(self):
        """Test getting selected models from string."""
        with patch.dict('os.environ', {'HA_WAKE_WORD_MODELS': 'alexa, jarvis, hal'}):
            detector = make_detector()
            assert detector._get_selected_models() == ['alexa', 'jarvis', 'hal']

    def test_get_selected_models_default(self):
        """Test getting selected models with default."""
        detector = make_detector()
        assert detector._get_selected_models() == ['alexa']

    def test_ensure_models_directory_creates(self, tmp_path):
        """Test models directory creation."""
        detector = make_detector()
        detector.models_dir = str(tmp_path / 'models')

        detector._ensure_models_directory()

        assert os.path.isdir(detector.models_dir)

    def test_ensure_models_directory_exists(self, tmp_path):
        """Test when models directory already exists."""
        detector = make_detector()
        detector.models_dir = str(tmp_path)

        with patch('os.makedirs') as mock_makedirs:
            detector._ensure_models_directory()

        mock_makedirs.assert_not_called()

    def test_init_openwakeword_success(self, tmp_path, mock_model_class):
        """Test successful OpenWakeWord initialization with a local ONNX model."""
        touch(tmp_path, 'alexa.onnx')
        detector = make_detector()
        detector.models_dir = str(tmp_path)
        detector.noise_suppression = True

        with patch('wake_word_detector.check_wake_word_noise_suppression', return_value=True),              patch('wake_word_detector.platform.system', return_value='Windows'):
            result = detector._init_openwakeword()

        assert result is True
        assert detector.model == mock_model_class.return_value
        mock_model_class.assert_called_once_with(
            vad_threshold=0.3,
            enable_speex_noise_suppression=True,
            wakeword_models=[str(tmp_path / 'alexa.onnx')],
            inference_framework='onnx'
        )

    def test_init_openwakeword_defaults_when_no_local_models(self, tmp_path, mock_model_class):
        """Without local model files openWakeWord is asked for its default models."""
        detector = make_detector()
        detector.models_dir = str(tmp_path)

        with patch('wake_word_detector.platform.system', return_value='Windows'):
            assert detector._init_openwakeword() is True

        mock_model_class.assert_called_once_with(vad_threshold=0.3)

    def test_init_openwakeword_linux_without_tflite_uses_onnx(self, tmp_path, mock_model_class):
        """On Linux without the tflite runtime ONNX models are used."""
        touch(tmp_path, 'alexa.onnx', 'alexa.tflite')
        detector = make_detector()
        detector.models_dir = str(tmp_path)

        with patch('wake_word_detector.platform.system', return_value='Linux'),              patch('wake_word_detector._tflite_runtime_available', return_value=False):
            detector._init_openwakeword()

        kwargs = mock_model_class.call_args.kwargs
        assert kwargs['wakeword_models'] == [str(tmp_path / 'alexa.onnx')]
        assert kwargs['inference_framework'] == 'onnx'

    def test_init_openwakeword_tflite_error_falls_back_to_defaults(self, tmp_path, mock_model_class):
        """A tflite-related load error retries without custom models."""
        touch(tmp_path, 'alexa.onnx')
        detector = make_detector()
        detector.models_dir = str(tmp_path)
        fallback_model = Mock()
        mock_model_class.side_effect = [Exception("tflite missing"), fallback_model]

        with patch('wake_word_detector.platform.system', return_value='Windows'):
            result = detector._init_openwakeword()

        assert result is True
        assert detector.model == fallback_model
        assert mock_model_class.call_count == 2
        assert 'wakeword_models' not in mock_model_class.call_args.kwargs

    def test_init_openwakeword_model_error_disables(self, tmp_path, mock_model_class):
        """Other model errors disable wake word detection."""
        detector = make_detector()
        detector.models_dir = str(tmp_path)
        detector.enabled = True
        mock_model_class.side_effect = Exception("boom")

        result = detector._init_openwakeword()

        assert result is False
        assert detector.model is None
        assert detector.enabled is False

    def test_init_openwakeword_import_error(self):
        """Test OpenWakeWord initialization with import error."""
        detector = make_detector()
        detector.enabled = True

        with patch.dict(sys.modules, {'openwakeword': None}):
            result = detector._init_openwakeword()

        assert result is False
        assert detector.model is None
        assert detector.enabled is False

    def test_get_model_paths_success(self, tmp_path):
        """Test getting model paths successfully."""
        touch(tmp_path, 'alexa.onnx', 'jarvis.tflite', 'other.txt')
        detector = make_detector()
        detector.models_dir = str(tmp_path)
        detector.selected_models = ['alexa', 'jarvis']

        paths = detector._get_model_paths()

        assert paths == [str(tmp_path / 'alexa.onnx'), str(tmp_path / 'jarvis.tflite')]

    def test_get_model_paths_prefers_onnx_on_windows(self, tmp_path):
        """Windows prefers ONNX when both formats exist."""
        touch(tmp_path, 'alexa.onnx', 'alexa.tflite')
        detector = make_detector()
        detector.models_dir = str(tmp_path)
        detector.selected_models = ['alexa']

        with patch('wake_word_detector.platform.system', return_value='Windows'):
            paths = detector._get_model_paths()

        assert paths == [str(tmp_path / 'alexa.onnx')]

    def test_get_model_paths_prefers_tflite_on_linux_with_runtime(self, tmp_path):
        """Linux prefers tflite when the runtime is importable."""
        touch(tmp_path, 'alexa.onnx', 'alexa.tflite')
        detector = make_detector()
        detector.models_dir = str(tmp_path)
        detector.selected_models = ['alexa']

        with patch('wake_word_detector.platform.system', return_value='Linux'), \
             patch('wake_word_detector._tflite_runtime_available', return_value=True):
            paths = detector._get_model_paths()

        assert paths == [str(tmp_path / 'alexa.tflite')]

    def test_get_model_paths_missing_models(self, tmp_path):
        """Test getting model paths with missing models."""
        touch(tmp_path, 'alexa.onnx')
        detector = make_detector()
        detector.models_dir = str(tmp_path)
        detector.selected_models = ['alexa', 'nonexistent']

        paths = detector._get_model_paths()

        assert paths == [str(tmp_path / 'alexa.onnx')]

    def test_get_model_paths_no_directory(self, tmp_path):
        """Test getting model paths when directory doesn't exist."""
        detector = make_detector()
        detector.models_dir = str(tmp_path / 'missing')
        detector.selected_models = ['alexa']

        assert detector._get_model_paths() == []

    def test_find_microphone_uses_configured_index(self):
        """A configured microphone index with input channels is used."""
        detector = make_detector()
        detector.audio = Mock()
        detector.audio.get_device_info_by_index.return_value = {'name': 'Mic', 'maxInputChannels': 2}

        with patch.dict('os.environ', {'HA_MICROPHONE_INDEX': '3'}):
            assert detector._find_microphone() == 3

    def test_find_microphone_falls_back_to_default(self):
        """An unusable configured index falls back to the default input device."""
        detector = make_detector()
        detector.audio = Mock()
        detector.audio.get_device_info_by_index.return_value = {'name': 'Out', 'maxInputChannels': 0}
        detector.audio.get_default_input_device_info.return_value = {'index': 1, 'name': 'Default'}
        detector.audio.get_device_count.return_value = 0

        with patch.dict('os.environ', {'HA_MICROPHONE_INDEX': '3'}):
            assert detector._find_microphone() == 1

    def test_start_detection_success(self):
        """Test successful wake word detection start."""
        mock_audio = Mock()
        mock_audio.get_default_input_device_info.return_value = {'index': 2, 'name': 'Default'}
        mock_audio.get_device_count.return_value = 0
        mock_stream = mock_audio.open.return_value

        detector = make_detector()
        detector.enabled = True
        detector.model = Mock()

        with patch('wake_word_detector.pyaudio.PyAudio', return_value=mock_audio), \
             patch.object(detector, '_detection_loop') as mock_loop:
            result = detector.start_detection()
            detector.detection_thread.join(timeout=1)

        assert result is True
        assert detector.is_running is True
        assert detector.audio == mock_audio
        assert detector.stream == mock_stream
        assert mock_audio.open.call_args.kwargs['input_device_index'] == 2
        mock_loop.assert_called_once()

    def test_start_detection_disabled(self):
        """Test starting detection when disabled."""
        detector = make_detector()
        detector.enabled = False

        assert detector.start_detection() is False
        assert detector.is_running is False

    def test_start_detection_no_model(self):
        """Test starting detection without model."""
        detector = make_detector()
        detector.enabled = True
        detector.model = None

        assert detector.start_detection() is False
        assert detector.is_running is False

    def test_start_detection_already_running(self):
        """Test starting detection when already running."""
        detector = make_detector()
        detector.enabled = True
        detector.model = Mock()
        detector.is_running = True

        with patch('wake_word_detector.pyaudio.PyAudio') as mock_pyaudio:
            result = detector.start_detection()

        assert result is True
        mock_pyaudio.assert_not_called()

    def test_start_detection_audio_error(self):
        """Test starting detection with audio error."""
        detector = make_detector()
        detector.enabled = True
        detector.model = Mock()

        with patch('wake_word_detector.pyaudio.PyAudio', side_effect=Exception("Audio error")):
            result = detector.start_detection()

        assert result is False
        assert detector.is_running is False

    def test_start_detection_no_microphone(self):
        """Test starting detection when no input device exists."""
        mock_audio = Mock()
        mock_audio.get_default_input_device_info.side_effect = OSError("No default")
        mock_audio.get_device_count.return_value = 0

        detector = make_detector()
        detector.enabled = True
        detector.model = Mock()

        with patch('wake_word_detector.pyaudio.PyAudio', return_value=mock_audio):
            result = detector.start_detection()

        assert result is False
        assert detector.is_running is False
        mock_audio.open.assert_not_called()

    def test_stop_detection_success(self):
        """Test successful detection stop."""
        detector = make_detector()
        detector.is_running = True
        stream = detector.stream = Mock()
        audio = detector.audio = Mock()

        detector.stop_detection()

        assert detector.is_running is False
        stream.stop_stream.assert_called_once()
        stream.close.assert_called_once()
        audio.terminate.assert_called_once()
        assert detector.stream is None
        assert detector.audio is None

    def test_stop_detection_not_running(self):
        """Test stopping detection when not running."""
        detector = make_detector()
        detector.stream = Mock()

        detector.stop_detection()

        assert detector.is_running is False
        detector.stream.stop_stream.assert_not_called()

    def test_stop_detection_with_errors(self):
        """Test stopping detection with cleanup errors."""
        detector = make_detector()
        detector.is_running = True
        detector.stream = Mock()
        detector.audio = Mock()
        detector.stream.stop_stream.side_effect = Exception("Stream error")

        detector.stop_detection()

        assert detector.is_running is False

    def test_process_predictions_wake_word_detected(self):
        """Test prediction processing with wake word detection."""
        callback = Mock()
        detector = make_detector(callback)
        detector.selected_models = ['alexa', 'jarvis']
        detector.detection_threshold = 0.5

        with patch('wake_word_detector.time.sleep') as mock_sleep:
            detector._process_predictions({'alexa': 0.7, 'jarvis': 0.3})

        callback.assert_called_once_with('alexa', 0.7)
        mock_sleep.assert_called_once_with(0.5)

    def test_process_predictions_triggers_once(self):
        """Only the first model above threshold triggers the callback."""
        callback = Mock()
        detector = make_detector(callback)
        detector.selected_models = ['alexa', 'jarvis']
        detector.detection_threshold = 0.5

        with patch('wake_word_detector.time.sleep'):
            detector._process_predictions({'alexa': 0.7, 'jarvis': 0.9})

        callback.assert_called_once_with('alexa', 0.7)

    def test_process_predictions_no_detection(self):
        """Test prediction processing below threshold."""
        callback = Mock()
        detector = make_detector(callback)
        detector.selected_models = ['alexa', 'jarvis']
        detector.detection_threshold = 0.5

        detector._process_predictions({'alexa': 0.3, 'jarvis': 0.2})

        callback.assert_not_called()

    def test_process_predictions_ignores_unselected_model(self):
        """Models outside the selection never trigger the callback."""
        callback = Mock()
        detector = make_detector(callback)
        detector.selected_models = ['alexa']
        detector.detection_threshold = 0.5

        detector._process_predictions({'jarvis': 0.9})

        callback.assert_not_called()

    def test_process_predictions_callback_exception(self):
        """A failing callback does not propagate."""
        callback = Mock(side_effect=Exception("callback error"))
        detector = make_detector(callback)
        detector.selected_models = ['alexa']

        with patch('wake_word_detector.time.sleep'):
            detector._process_predictions({'alexa': 0.9})

        callback.assert_called_once()

    def test_detection_loop_reads_audio_and_processes_predictions(self):
        """The loop feeds audio frames to the model and processes its predictions."""
        callback = Mock()
        detector = make_detector(callback)
        detector.selected_models = ['alexa']
        detector.is_running = True
        detector.stream = Mock()
        detector.stream.read.return_value = np.zeros(detector.chunk_size, dtype=np.int16).tobytes()

        def predict(audio):
            detector.is_running = False
            assert audio.dtype == np.int16
            assert len(audio) == detector.chunk_size
            return {'alexa': 0.8}

        detector.model = Mock()
        detector.model.predict.side_effect = predict

        with patch('wake_word_detector.time.sleep'):
            detector._detection_loop()

        detector.stream.read.assert_called_once_with(detector.chunk_size, exception_on_overflow=False)
        callback.assert_called_once_with('alexa', 0.8)

    def test_detection_loop_model_exception_ends_loop(self):
        """A model error ends the loop without raising or firing the callback."""
        callback = Mock()
        detector = make_detector(callback)
        detector.is_running = True
        detector.stream = Mock()
        detector.stream.read.return_value = np.zeros(detector.chunk_size, dtype=np.int16).tobytes()
        detector.model = Mock()
        detector.model.predict.side_effect = Exception("Model error")

        detector._detection_loop()

        callback.assert_not_called()
        detector.model.predict.assert_called_once()

    def test_get_model_info_enabled(self):
        """Test getting model info when enabled."""
        detector = make_detector()
        detector.enabled = True
        detector.is_running = True
        detector.selected_models = ['alexa', 'jarvis']
        detector.detection_threshold = 0.5
        detector.vad_threshold = 0.3
        detector.noise_suppression = True

        with patch.object(detector, '_get_available_models', return_value=['alexa', 'jarvis', 'hal']):
            info = detector.get_model_info()

        assert info['enabled'] is True
        assert info['is_running'] is True
        assert info['selected_models'] == ['alexa', 'jarvis']
        assert info['detection_threshold'] == 0.5
        assert info['vad_threshold'] == 0.3
        assert info['noise_suppression'] is True
        assert info['available_models'] == ['alexa', 'jarvis', 'hal']

    def test_get_model_info_disabled(self):
        """Test getting model info when disabled."""
        detector = make_detector()

        info = detector.get_model_info()

        assert info['enabled'] is False
        assert info['is_running'] is False
        assert info['selected_models'] == ['alexa']

    def test_get_available_models(self, tmp_path):
        """Test getting available models."""
        touch(tmp_path, 'alexa.onnx', 'alexa.tflite', 'jarvis.onnx', 'hal.tflite', 'other.txt')
        detector = make_detector()
        detector.models_dir = str(tmp_path)

        models = detector._get_available_models()

        assert {'alexa', 'jarvis', 'hal'} <= set(models)
        assert 'other' not in models

    def test_get_available_models_no_directory(self, tmp_path):
        """A missing models directory yields no models."""
        detector = make_detector()
        detector.models_dir = str(tmp_path / 'missing')

        assert detector._get_available_models() == []

    def test_update_threshold(self):
        """Thresholds outside 0.0-1.0 are rejected."""
        detector = make_detector()

        assert detector.update_threshold(0.8) is True
        assert detector.detection_threshold == 0.8
        assert detector.update_threshold(1.5) is False
        assert detector.detection_threshold == 0.8

    def test_reload_models_success(self):
        """Test successful model reloading picks up new configuration."""
        detector = make_detector()
        detector.enabled = True
        detector.is_running = True

        with patch.object(detector, '_init_openwakeword', return_value=True) as mock_init, \
             patch.object(detector, 'stop_detection') as mock_stop, \
             patch.object(detector, 'start_detection', return_value=True), \
             patch.dict('os.environ', {
                 'HA_WAKE_WORD_MODELS': 'jarvis',
                 'HA_WAKE_WORD_THRESHOLD': '0.7'
             }):
            result = detector.reload_models()

        assert result is True
        assert detector.selected_models == ['jarvis']
        assert detector.detection_threshold == 0.7
        mock_stop.assert_called_once()
        mock_init.assert_called_once()

    def test_reload_models_disabled(self):
        """Test model reloading when disabled."""
        detector = make_detector()
        detector.enabled = False

        with patch.object(detector, '_init_openwakeword') as mock_init:
            result = detector.reload_models()

        assert result is False
        mock_init.assert_not_called()

    def test_reload_models_init_failure(self):
        """A failed re-initialization does not start detection."""
        detector = make_detector()
        detector.enabled = True

        with patch.object(detector, '_init_openwakeword', return_value=False), \
             patch.object(detector, 'start_detection') as mock_start:
            result = detector.reload_models()

        assert result is False
        mock_start.assert_not_called()

    def test_reload_models_start_failure(self):
        """Test model reloading with start failure."""
        detector = make_detector()
        detector.enabled = True

        with patch.object(detector, '_init_openwakeword', return_value=True), \
             patch.object(detector, 'start_detection', return_value=False):
            result = detector.reload_models()

        assert result is False

    def test_reload_models_noise_suppression_default_matches_init(self):
        """Reloading with no configuration should not flip the noise suppression default."""
        detector = make_detector()
        detector.enabled = True

        with patch.object(detector, '_init_openwakeword', return_value=True), \
             patch.object(detector, 'start_detection', return_value=True):
            detector.reload_models()

        assert detector.noise_suppression is False


def test_list_available_models(tmp_path):
    """Test listing available models returns sorted names without extensions."""
    models_dir = tmp_path / 'models'
    models_dir.mkdir()
    touch(models_dir, 'jarvis.onnx', 'alexa.tflite', 'other.txt')

    with patch.object(wake_word_detector, '__file__', str(tmp_path / 'wake_word_detector.py')):
        models = wake_word_detector.list_available_models()

    assert models == ['alexa', 'jarvis']


def test_validate_wake_word_config(mock_model_class):
    """Test wake word configuration validation."""
    with patch.dict('os.environ', {
        'HA_WAKE_WORD_ENABLED': 'true',
        'HA_WAKE_WORD_MODELS': 'alexa,jarvis',
        'HA_WAKE_WORD_THRESHOLD': '0.5'
    }):
        assert wake_word_detector.validate_wake_word_config() == []

def test_validate_wake_word_config_disabled():
    """Test wake word configuration validation when disabled."""
    with patch.dict('os.environ', {'HA_WAKE_WORD_ENABLED': 'false'}):
        assert wake_word_detector.validate_wake_word_config() == []

def test_validate_wake_word_config_library_missing():
    """Test wake word configuration validation without openwakeword installed."""
    with patch.dict('os.environ', {'HA_WAKE_WORD_ENABLED': 'true'}), \
         patch.dict(sys.modules, {'openwakeword': None}):
        issues = wake_word_detector.validate_wake_word_config()

    assert len(issues) == 1
    assert 'not installed' in issues[0]

def test_validate_wake_word_config_no_models(mock_model_class):
    """Test wake word configuration validation with an empty model list."""
    with patch.dict('os.environ', {
        'HA_WAKE_WORD_ENABLED': 'true',
        'HA_WAKE_WORD_MODELS': ''
    }):
        issues = wake_word_detector.validate_wake_word_config()

    assert issues == ["No wake word models specified"]

def test_validate_wake_word_config_invalid_threshold(mock_model_class):
    """Test wake word configuration validation with invalid threshold."""
    with patch.dict('os.environ', {
        'HA_WAKE_WORD_ENABLED': 'true',
        'HA_WAKE_WORD_THRESHOLD': '1.5'
    }):
        issues = wake_word_detector.validate_wake_word_config()

    assert len(issues) == 1
    assert 'threshold' in issues[0].lower()

def test_validate_wake_word_config_invalid_vad_threshold(mock_model_class):
    """Test wake word configuration validation with invalid VAD threshold."""
    with patch.dict('os.environ', {
        'HA_WAKE_WORD_ENABLED': 'true',
        'HA_WAKE_WORD_VAD_THRESHOLD': '-0.1'
    }):
        issues = wake_word_detector.validate_wake_word_config()

    assert len(issues) == 1
    assert 'VAD' in issues[0]
