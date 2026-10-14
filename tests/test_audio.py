"""
Tests for audio module.
"""
import pytest
import numpy as np
from unittest.mock import Mock, AsyncMock, patch
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
        mock_audio.get_default_input_device_info.return_value = {'index': 0}

        mock_stream = Mock()
        mock_audio.open.return_value = mock_stream

        manager = audio.AudioManager()
        result = manager.init_audio()

        assert result is True
        assert manager.audio == mock_audio
        assert manager.stream == mock_stream
        mock_audio.open.assert_called_once()
        assert mock_audio.open.call_args.kwargs['input_device_index'] == 0

    @patch('pyaudio.PyAudio')
    def test_init_audio_no_microphone(self, mock_pyaudio):
        """Test audio initialization with no microphone."""
        mock_audio = Mock()
        mock_pyaudio.return_value = mock_audio
        mock_audio.get_device_count.return_value = 0

        manager = audio.AudioManager()
        result = manager.init_audio()

        assert result is False
        mock_audio.open.assert_not_called()

    @patch('pyaudio.PyAudio')
    def test_init_audio_exception(self, mock_pyaudio):
        """Test audio initialization with exception."""
        mock_pyaudio.side_effect = Exception("Audio error")

        manager = audio.AudioManager()
        result = manager.init_audio()

        assert result is False

    def test_auto_find_microphone_no_default_device(self):
        """Test fallback to first input device when PyAudio has no default input."""
        manager = audio.AudioManager()
        manager.audio = Mock()
        manager.audio.get_device_count.return_value = 1
        manager.audio.get_device_info_by_index.return_value = {'name': 'Microphone', 'maxInputChannels': 1}
        manager.audio.get_default_input_device_info.side_effect = IOError("No Default Input Device Available")

        assert manager._auto_find_microphone() == 0

    @patch.dict('os.environ', {'HA_MICROPHONE_INDEX': '1'})
    def test_find_best_microphone_specific_index(self):
        """Test finding microphone with specific index."""
        manager = audio.AudioManager()
        manager.audio = Mock()
        manager.audio.get_device_info_by_index.return_value = {
            'name': 'Selected Microphone',
            'maxInputChannels': 1
        }

        result = manager._find_best_microphone()

        assert result == 1
        manager.audio.get_device_info_by_index.assert_called_with(1)

    @patch.dict('os.environ', {'HA_MICROPHONE_INDEX': '1'})
    def test_find_best_microphone_invalid_index(self):
        """Test fallback to auto-detection when selected index is unavailable."""
        manager = audio.AudioManager()
        manager.audio = Mock()
        manager.audio.get_device_info_by_index.side_effect = Exception("Invalid index")

        with patch.object(manager, '_auto_find_microphone', return_value=0) as mock_auto:
            result = manager._find_best_microphone()

        assert result == 0
        mock_auto.assert_called_once()

    @patch.dict('os.environ', {'HA_MICROPHONE_INDEX': '1'})
    def test_find_best_microphone_index_without_input(self):
        """Test fallback to auto-detection when selected device has no input channels."""
        manager = audio.AudioManager()
        manager.audio = Mock()
        manager.audio.get_device_info_by_index.return_value = {'name': 'Speaker', 'maxInputChannels': 0}

        with patch.object(manager, '_auto_find_microphone', return_value=2):
            assert manager._find_best_microphone() == 2

    @patch.dict('os.environ', {'HA_MICROPHONE_INDEX': '-1'})
    def test_find_best_microphone_auto(self):
        """Test that negative index goes straight to auto-detection."""
        manager = audio.AudioManager()
        manager.audio = Mock()

        with patch.object(manager, '_auto_find_microphone', return_value=3):
            assert manager._find_best_microphone() == 3
        manager.audio.get_device_info_by_index.assert_not_called()

    def test_auto_find_microphone_prefers_default(self):
        """Test auto-detection prefers the default input device over the first one."""
        manager = audio.AudioManager()
        manager.audio = Mock()
        manager.audio.get_device_count.return_value = 3
        manager.audio.get_device_info_by_index.side_effect = [
            {'name': 'Speaker', 'maxInputChannels': 0},
            {'name': 'Microphone 1', 'maxInputChannels': 1},
            {'name': 'Microphone 2', 'maxInputChannels': 1}
        ]
        manager.audio.get_default_input_device_info.return_value = {'index': 2}

        assert manager._auto_find_microphone() == 2

    def test_auto_find_microphone_first_input_when_default_not_input(self):
        """Test auto-detection falls back to the first input device."""
        manager = audio.AudioManager()
        manager.audio = Mock()
        manager.audio.get_device_count.return_value = 2
        manager.audio.get_device_info_by_index.side_effect = [
            {'name': 'Speaker', 'maxInputChannels': 0},
            {'name': 'Microphone', 'maxInputChannels': 1}
        ]
        manager.audio.get_default_input_device_info.return_value = {'index': 0}

        assert manager._auto_find_microphone() == 1

    def test_auto_find_microphone_none_found(self):
        """Test auto-detection when no input device is available."""
        manager = audio.AudioManager()
        manager.audio = Mock()
        manager.audio.get_device_count.return_value = 1
        manager.audio.get_device_info_by_index.return_value = {'name': 'Speaker', 'maxInputChannels': 0}
        manager.audio.get_default_input_device_info.return_value = {'index': 0}

        assert manager._auto_find_microphone() is None

    def test_flush_input_buffer_drains_backlog(self):
        """Test flushing reads whole chunks until less than one chunk remains."""
        manager = audio.AudioManager()
        manager.stream = Mock()
        manager.stream.get_read_available.side_effect = [1000, 500, 100]

        manager._flush_input_buffer()

        assert manager.stream.read.call_count == 2
        manager.stream.read.assert_called_with(manager.chunk_size, exception_on_overflow=False)

    def test_flush_input_buffer_no_stream(self):
        """Test flushing without a stream does nothing."""
        manager = audio.AudioManager()

        manager._flush_input_buffer()

    def test_flush_input_buffer_swallows_errors(self):
        """Test flushing errors do not propagate."""
        manager = audio.AudioManager()
        manager.stream = Mock()
        manager.stream.get_read_available.side_effect = Exception("Stream error")

        manager._flush_input_buffer()

    def _recording_manager(self, vad_results):
        manager = audio.AudioManager()
        manager.stream = Mock()
        manager.stream.get_read_available.return_value = 0
        manager.stream.read.return_value = b'\x01\x02' * manager.chunk_size
        manager.vad = Mock()
        manager.vad.silence_threshold_sec = 0.8
        manager.vad.process_audio.side_effect = vad_results
        return manager

    async def test_record_audio_success(self):
        """Test successful audio recording."""
        manager = self._recording_manager([(False, False), (True, False), (True, True)])
        chunk_callback = AsyncMock()
        end_callback = AsyncMock()

        result = await manager.record_audio(chunk_callback, end_callback)

        assert result is True
        assert chunk_callback.await_count == 2
        end_callback.assert_awaited_once()
        manager.vad.reset.assert_called_once()

    async def test_record_audio_skips_chunks_before_speech(self):
        """Test chunks before speech start are not passed to the callback."""
        manager = self._recording_manager([(False, False), (False, False), (True, True)])
        chunk_callback = AsyncMock()

        result = await manager.record_audio(chunk_callback)

        assert result is True
        assert chunk_callback.await_count == 1

    async def test_record_audio_no_stream(self):
        """Test recording without an initialized stream."""
        manager = audio.AudioManager()
        chunk_callback = AsyncMock()

        result = await manager.record_audio(chunk_callback)

        assert result is False
        chunk_callback.assert_not_awaited()

    async def test_record_audio_read_error_before_speech(self):
        """Test a stream read error ends recording without calling callbacks."""
        manager = self._recording_manager([(False, False)])
        manager.stream.read.side_effect = [b'\x01\x02' * manager.chunk_size, Exception("Read error")]
        chunk_callback = AsyncMock()
        end_callback = AsyncMock()

        await manager.record_audio(chunk_callback, end_callback)

        chunk_callback.assert_not_awaited()
        end_callback.assert_not_awaited()

    async def test_record_audio_callback_errors_do_not_abort(self):
        """Test callback exceptions are logged and recording continues."""
        manager = self._recording_manager([(True, False), (True, True)])
        chunk_callback = AsyncMock(side_effect=Exception("Callback error"))
        end_callback = AsyncMock(side_effect=Exception("End error"))

        result = await manager.record_audio(chunk_callback, end_callback)

        assert result is True
        assert chunk_callback.await_count == 2
        end_callback.assert_awaited_once()

    async def test_record_audio_async_success(self):
        """Test conversation recording returns joined speech chunks."""
        manager = self._recording_manager([(False, False), (True, False), (True, False), (True, True)])

        result = await manager.record_audio_async(timeout=5, min_audio_length=0.05)

        assert result == manager.stream.read.return_value * 3
        manager.vad.reset.assert_called_once()

    async def test_record_audio_async_restores_vad_threshold(self):
        """Test the custom silence threshold is applied only during recording."""
        manager = self._recording_manager([])
        seen = []

        def process_audio(data):
            seen.append(manager.vad.silence_threshold_sec)
            return True, True

        manager.vad.process_audio.side_effect = process_audio

        await manager.record_audio_async(silence_threshold=0.3, min_audio_length=0.01)

        assert set(seen) == {0.3}
        assert manager.vad.silence_threshold_sec == 0.8

    async def test_record_audio_async_no_stream(self):
        """Test conversation recording without an initialized stream."""
        manager = audio.AudioManager()

        assert await manager.record_audio_async() is None

    async def test_record_audio_async_timeout(self):
        """Test conversation recording returns None when the timeout expires."""
        manager = self._recording_manager([(False, False)])

        result = await manager.record_audio_async(timeout=-1)

        assert result is None
        manager.stream.read.assert_not_called()

    async def test_record_audio_async_read_error(self):
        """Test conversation recording returns None on read error without speech."""
        manager = self._recording_manager([])
        manager.stream.read.side_effect = Exception("Read error")

        assert await manager.record_audio_async() is None

    def test_get_audio_level_silence(self):
        """Test audio level of silence."""
        manager = audio.AudioManager()

        assert manager.get_audio_level(np.zeros(480, dtype=np.int16).tobytes()) == 0.0

    def test_get_audio_level_loud(self):
        """Test audio level of a constant-amplitude signal."""
        manager = audio.AudioManager()
        samples = np.full(480, 16384, dtype=np.int16)

        assert manager.get_audio_level(samples.tobytes()) == pytest.approx(16384 / 32767.0, rel=1e-3)

    def test_get_audio_level_invalid_data(self):
        """Test audio level of malformed data returns 0."""
        manager = audio.AudioManager()

        assert manager.get_audio_level(b'\x01\x02\x03') == 0.0

    def test_is_audio_stream_active(self):
        """Test stream activity check."""
        manager = audio.AudioManager()
        assert not manager.is_audio_stream_active()

        manager.stream = Mock()
        manager.stream.is_active.return_value = True
        assert manager.is_audio_stream_active()

    def test_get_device_info(self):
        """Test device info lookup for the active stream."""
        manager = audio.AudioManager()
        assert manager.get_device_info() is None

        manager.audio = Mock()
        manager.stream = Mock()
        manager.stream._input_device_index = 4
        manager.audio.get_device_info_by_index.return_value = {'name': 'Microphone'}

        assert manager.get_device_info() == {'name': 'Microphone'}
        manager.audio.get_device_info_by_index.assert_called_once_with(4)

    def test_close_audio_success(self):
        """Test successful audio cleanup."""
        manager = audio.AudioManager()
        stream = manager.stream = Mock()
        pa = manager.audio = Mock()

        manager.close_audio()

        stream.stop_stream.assert_called_once()
        stream.close.assert_called_once()
        pa.terminate.assert_called_once()
        assert manager.stream is None
        assert manager.audio is None

    def test_close_audio_with_errors(self):
        """Test audio cleanup with errors does not raise."""
        manager = audio.AudioManager()
        manager.stream = Mock()
        manager.audio = Mock()
        manager.stream.stop_stream.side_effect = Exception("Stream error")

        manager.close_audio()

    def test_close_audio_releases_resources_after_error(self):
        """Test audio cleanup still terminates PyAudio when the stream fails to stop."""
        manager = audio.AudioManager()
        manager.stream = Mock()
        pa = manager.audio = Mock()
        manager.stream.stop_stream.side_effect = Exception("Stream error")

        manager.close_audio()

        pa.terminate.assert_called_once()
        assert manager.stream is None
        assert manager.audio is None

    def test_close_audio_no_resources(self):
        """Test cleanup when no resources are initialized."""
        manager = audio.AudioManager()

        manager.close_audio()

        assert manager.stream is None
        assert manager.audio is None
