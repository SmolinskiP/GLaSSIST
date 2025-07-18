"""
Tests for audio module.
"""
import pytest
import numpy as np
from unittest.mock import Mock, patch, MagicMock
import audio


class TestAudioManager:
    """Test cases for AudioManager class."""
    
    @patch.dict('os.environ', {
        'HA_SAMPLE_RATE': '16000',
        'HA_CHANNELS': '1',
        'HA_FRAME_DURATION_MS': '30'
    })
    def test_init(self):
        """Test AudioManager initialization."""
        manager = audio.AudioManager()
        
        assert manager.sample_rate == 16000
        assert manager.channels == 1
        assert manager.chunk_size == 480  # 16000 * 30 / 1000
        assert manager.audio is None
        assert manager.stream is None
        assert manager.vad is not None
    
    @patch('audio.VoiceActivityDetector')
    @patch('audio.utils.validate_audio_format')
    def test_init_with_custom_params(self, mock_validate, mock_vad):
        """Test AudioManager initialization with custom parameters."""
        with patch.dict('os.environ', {
            'HA_SAMPLE_RATE': '44100',
            'HA_CHANNELS': '2',
            'HA_FRAME_DURATION_MS': '20'
        }):
            manager = audio.AudioManager()
            
            assert manager.sample_rate == 44100
            assert manager.channels == 2
            assert manager.chunk_size == 882  # 44100 * 20 / 1000
            mock_validate.assert_called_once_with(44100, 2)
    
    def test_get_available_microphones_no_audio(self):
        """Test getting microphones when audio is not initialized."""
        manager = audio.AudioManager()
        microphones = manager.get_available_microphones()
        assert microphones == []
    
    @patch('pyaudio.PyAudio')
    def test_get_available_microphones_success(self, mock_pyaudio):
        """Test getting available microphones successfully."""
        mock_audio = Mock()
        mock_pyaudio.return_value = mock_audio
        mock_audio.get_device_count.return_value = 3
        
        # Mock device info
        mock_audio.get_device_info_by_index.side_effect = [
            {'name': 'Speaker', 'maxInputChannels': 0, 'defaultSampleRate': 44100},
            {'name': 'Microphone 1', 'maxInputChannels': 1, 'defaultSampleRate': 16000},
            {'name': 'Microphone 2', 'maxInputChannels': 2, 'defaultSampleRate': 44100}
        ]
        
        manager = audio.AudioManager()
        manager.audio = mock_audio
        
        microphones = manager.get_available_microphones()
        
        assert len(microphones) == 2  # Only input devices
        assert microphones[0]['name'] == 'Microphone 1'
        assert microphones[0]['channels'] == 1
        assert microphones[1]['name'] == 'Microphone 2'
        assert microphones[1]['channels'] == 2
    
    @patch('pyaudio.PyAudio')
    def test_get_available_microphones_with_errors(self, mock_pyaudio):
        """Test getting microphones with some device errors."""
        mock_audio = Mock()
        mock_pyaudio.return_value = mock_audio
        mock_audio.get_device_count.return_value = 2
        
        # First device throws error, second is valid
        mock_audio.get_device_info_by_index.side_effect = [
            Exception("Device error"),
            {'name': 'Microphone', 'maxInputChannels': 1, 'defaultSampleRate': 16000}
        ]
        
        manager = audio.AudioManager()
        manager.audio = mock_audio
        
        microphones = manager.get_available_microphones()
        
        assert len(microphones) == 1
        assert microphones[0]['name'] == 'Microphone'
    
    @patch('pyaudio.PyAudio')
    def test_init_audio_success(self, mock_pyaudio):
        """Test successful audio initialization."""
        mock_audio = Mock()
        mock_pyaudio.return_value = mock_audio
        mock_audio.get_device_count.return_value = 1
        mock_audio.get_device_info_by_index.return_value = {
            'name': 'Test Microphone',
            'maxInputChannels': 1,
            'defaultSampleRate': 16000
        }
        
        mock_stream = Mock()
        mock_audio.open.return_value = mock_stream
        
        manager = audio.AudioManager()
        result = manager.init_audio()
        
        assert result is True
        assert manager.audio == mock_audio
        assert manager.stream == mock_stream
        mock_audio.open.assert_called_once()
    
    @patch('pyaudio.PyAudio')
    def test_init_audio_no_microphone(self, mock_pyaudio):
        """Test audio initialization with no microphone."""
        mock_audio = Mock()
        mock_pyaudio.return_value = mock_audio
        mock_audio.get_device_count.return_value = 0
        
        manager = audio.AudioManager()
        result = manager.init_audio()
        
        assert result is False
    
    @patch('pyaudio.PyAudio')
    def test_init_audio_exception(self, mock_pyaudio):
        """Test audio initialization with exception."""
        mock_pyaudio.side_effect = Exception("Audio error")
        
        manager = audio.AudioManager()
        result = manager.init_audio()
        
        assert result is False
    
    @patch.dict('os.environ', {'HA_MICROPHONE_INDEX': '1'})
    @patch('pyaudio.PyAudio')
    def test_find_best_microphone_specific_index(self, mock_pyaudio):
        """Test finding microphone with specific index."""
        mock_audio = Mock()
        mock_pyaudio.return_value = mock_audio
        mock_audio.get_device_info_by_index.return_value = {
            'name': 'Selected Microphone',
            'maxInputChannels': 1
        }
        
        manager = audio.AudioManager()
        manager.audio = mock_audio
        
        result = manager._find_best_microphone()
        
        assert result == 1
        mock_audio.get_device_info_by_index.assert_called_with(1)
    
    @patch.dict('os.environ', {'HA_MICROPHONE_INDEX': '1'})
    @patch('pyaudio.PyAudio')
    def test_find_best_microphone_invalid_index(self, mock_pyaudio):
        """Test finding microphone with invalid specific index."""
        mock_audio = Mock()
        mock_pyaudio.return_value = mock_audio
        mock_audio.get_device_info_by_index.side_effect = Exception("Invalid index")
        mock_audio.get_device_count.return_value = 1
        mock_audio.get_device_info_by_index.side_effect = [
            Exception("Invalid index"),  # First call for specific index
            {'name': 'Default Microphone', 'maxInputChannels': 1}  # Second call for fallback
        ]
        
        manager = audio.AudioManager()
        manager.audio = mock_audio
        
        with patch.object(manager, '_find_default_microphone', return_value=0):
            result = manager._find_best_microphone()
            assert result == 0
    
    @patch('pyaudio.PyAudio')
    def test_find_default_microphone_success(self, mock_pyaudio):
        """Test finding default microphone successfully."""
        mock_audio = Mock()
        mock_pyaudio.return_value = mock_audio
        mock_audio.get_device_count.return_value = 2
        mock_audio.get_device_info_by_index.side_effect = [
            {'name': 'Speaker', 'maxInputChannels': 0},  # Not input device
            {'name': 'Microphone', 'maxInputChannels': 1}  # Input device
        ]
        
        manager = audio.AudioManager()
        manager.audio = mock_audio
        
        result = manager._find_default_microphone()
        
        assert result == 1
    
    @patch('pyaudio.PyAudio')
    def test_find_default_microphone_none_found(self, mock_pyaudio):
        """Test finding default microphone when none available."""
        mock_audio = Mock()
        mock_pyaudio.return_value = mock_audio
        mock_audio.get_device_count.return_value = 1
        mock_audio.get_device_info_by_index.return_value = {
            'name': 'Speaker',
            'maxInputChannels': 0
        }
        
        manager = audio.AudioManager()
        manager.audio = mock_audio
        
        result = manager._find_default_microphone()
        
        assert result is None
    
    @patch('asyncio.sleep')
    async def test_record_audio_success(self, mock_sleep):
        """Test successful audio recording."""
        mock_sleep.return_value = None
        
        manager = audio.AudioManager()
        manager.stream = Mock()
        manager.vad = Mock()
        
        # Mock audio data
        audio_data = b'\x00\x01\x02\x03' * 100
        manager.stream.read.return_value = audio_data
        
        # Mock VAD responses
        manager.vad.is_speech.side_effect = [True, True, False]  # Speech detected, then silence
        
        chunk_callback = Mock()
        end_callback = Mock()
        
        result = await manager.record_audio(chunk_callback, end_callback)
        
        assert result is True
        assert chunk_callback.call_count >= 1
        end_callback.assert_called_once()
    
    @patch('asyncio.sleep')
    async def test_record_audio_no_speech(self, mock_sleep):
        """Test audio recording with no speech detected."""
        mock_sleep.return_value = None
        
        manager = audio.AudioManager()
        manager.stream = Mock()
        manager.vad = Mock()
        
        # Mock audio data
        audio_data = b'\x00\x01\x02\x03' * 100
        manager.stream.read.return_value = audio_data
        
        # Mock VAD - no speech detected
        manager.vad.is_speech.return_value = False
        
        chunk_callback = Mock()
        end_callback = Mock()
        
        # Should timeout after no speech
        with patch.dict('os.environ', {'HA_NO_SPEECH_TIMEOUT_SEC': '1'}):
            result = await manager.record_audio(chunk_callback, end_callback)
            
            assert result is False
    
    def test_close_audio_success(self):
        """Test successful audio cleanup."""
        manager = audio.AudioManager()
        manager.stream = Mock()
        manager.audio = Mock()
        
        manager.close_audio()
        
        manager.stream.stop_stream.assert_called_once()
        manager.stream.close.assert_called_once()
        manager.audio.terminate.assert_called_once()
        assert manager.stream is None
        assert manager.audio is None
    
    def test_close_audio_with_errors(self):
        """Test audio cleanup with errors."""
        manager = audio.AudioManager()
        manager.stream = Mock()
        manager.audio = Mock()
        
        # Mock exceptions during cleanup
        manager.stream.stop_stream.side_effect = Exception("Stream error")
        manager.audio.terminate.side_effect = Exception("Audio error")
        
        # Should not raise exceptions
        manager.close_audio()
        
        assert manager.stream is None
        assert manager.audio is None
    
    def test_close_audio_no_resources(self):
        """Test cleanup when no resources are initialized."""
        manager = audio.AudioManager()
        
        # Should not raise exceptions
        manager.close_audio()
        
        assert manager.stream is None
        assert manager.audio is None