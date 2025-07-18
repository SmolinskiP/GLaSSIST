"""
Tests for utils module.
"""
import pytest
import os
import tempfile
from unittest.mock import patch, Mock, mock_open
import utils


class TestUtils:
    """Test cases for utils module."""
    
    def test_get_env_string_default(self):
        """Test getting environment variable with string default."""
        with patch.dict(os.environ, {}, clear=True):
            result = utils.get_env("TEST_VAR", "default_value")
            assert result == "default_value"
    
    def test_get_env_string_exists(self):
        """Test getting existing environment variable."""
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            result = utils.get_env("TEST_VAR", "default_value")
            assert result == "test_value"
    
    def test_get_env_int_conversion(self):
        """Test environment variable conversion to int."""
        with patch.dict(os.environ, {"TEST_INT": "42"}):
            result = utils.get_env("TEST_INT", 0, int)
            assert result == 42
    
    def test_get_env_int_invalid(self):
        """Test environment variable with invalid int value."""
        with patch.dict(os.environ, {"TEST_INT": "invalid"}):
            result = utils.get_env("TEST_INT", 10, int)
            assert result == 10
    
    def test_get_env_bool_true_values(self):
        """Test boolean environment variables with true values."""
        true_values = ["true", "True", "TRUE", "1", "yes", "Y"]
        for value in true_values:
            with patch.dict(os.environ, {"TEST_BOOL": value}):
                result = utils.get_env_bool("TEST_BOOL", False)
                assert result is True, f"Failed for value: {value}"
    
    def test_get_env_bool_false_values(self):
        """Test boolean environment variables with false values."""
        false_values = ["false", "False", "FALSE", "0", "no", "N"]
        for value in false_values:
            with patch.dict(os.environ, {"TEST_BOOL": value}):
                result = utils.get_env_bool("TEST_BOOL", True)
                assert result is False, f"Failed for value: {value}"
    
    def test_get_env_bool_default(self):
        """Test boolean environment variable with default."""
        with patch.dict(os.environ, {}, clear=True):
            result = utils.get_env_bool("TEST_BOOL", True)
            assert result is True
    
    def test_validate_audio_format_valid(self):
        """Test audio format validation with valid parameters."""
        # Should not raise exception
        utils.validate_audio_format(16000, 1)
        utils.validate_audio_format(44100, 2)
    
    def test_validate_audio_format_invalid_sample_rate(self):
        """Test audio format validation with invalid sample rate."""
        with pytest.raises(ValueError, match="Unsupported sample rate"):
            utils.validate_audio_format(12000, 1)
    
    def test_validate_audio_format_invalid_channels(self):
        """Test audio format validation with invalid channels."""
        with pytest.raises(ValueError, match="Unsupported number of channels"):
            utils.validate_audio_format(16000, 5)
    
    @patch('utils.logger')
    def test_setup_logger(self, mock_logger):
        """Test logger setup."""
        # Test that logger is created
        logger = utils.setup_logger()
        assert logger is not None
    
    @patch('pygame.mixer.init')
    @patch('pygame.mixer.music.load')
    @patch('pygame.mixer.music.play')
    @patch('pygame.mixer.music.get_busy')
    @patch('os.path.exists')
    def test_play_feedback_sound_success(self, mock_exists, mock_busy, mock_play, mock_load, mock_init):
        """Test successful sound playback."""
        mock_exists.return_value = True
        mock_busy.side_effect = [True, True, False]  # Playing, then stops
        
        with patch.dict(os.environ, {"HA_SOUND_FEEDBACK": "true"}):
            result = utils.play_feedback_sound("activation")
            assert result is True
    
    @patch('pygame.mixer.init')
    @patch('os.path.exists')
    def test_play_feedback_sound_disabled(self, mock_exists, mock_init):
        """Test sound playback when disabled."""
        with patch.dict(os.environ, {"HA_SOUND_FEEDBACK": "false"}):
            result = utils.play_feedback_sound("activation")
            assert result is False
    
    @patch('os.path.exists')
    def test_play_feedback_sound_file_not_found(self, mock_exists):
        """Test sound playback with missing file."""
        mock_exists.return_value = False
        
        with patch.dict(os.environ, {"HA_SOUND_FEEDBACK": "true"}):
            result = utils.play_feedback_sound("activation")
            assert result is False
    
    @patch('requests.get')
    def test_play_audio_from_url_success(self, mock_get):
        """Test audio playback from URL."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"fake_audio_data"
        mock_get.return_value = mock_response
        
        with patch('tempfile.NamedTemporaryFile') as mock_temp:
            mock_temp.return_value.__enter__.return_value.name = "test.wav"
            with patch('pygame.mixer.init'), \
                 patch('pygame.mixer.music.load'), \
                 patch('pygame.mixer.music.play'), \
                 patch('pygame.mixer.music.get_busy', side_effect=[True, False]):
                
                result = utils.play_audio_from_url("http://test.com/audio.wav", "localhost:8123", Mock())
                assert result is True
    
    @patch('requests.get')
    def test_play_audio_from_url_http_error(self, mock_get):
        """Test audio playback from URL with HTTP error."""
        mock_get.return_value.status_code = 404
        
        result = utils.play_audio_from_url("http://test.com/audio.wav", "localhost:8123", Mock())
        assert result is False
    
    def test_convert_audio_chunk_to_float32(self):
        """Test audio chunk conversion to float32."""
        # Create test audio data (16-bit integers)
        import numpy as np
        audio_data = np.array([1000, -1000, 500, -500], dtype=np.int16)
        
        result = utils.convert_audio_chunk_to_float32(audio_data.tobytes())
        
        # Should return float32 numpy array
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float32
        assert len(result) == 4
        
        # Values should be normalized to [-1, 1] range
        assert all(abs(val) <= 1.0 for val in result)
    
    def test_convert_audio_chunk_to_float32_empty(self):
        """Test audio chunk conversion with empty data."""
        result = utils.convert_audio_chunk_to_float32(b"")
        assert len(result) == 0
        assert result.dtype == np.float32