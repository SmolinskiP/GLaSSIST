"""
Audio handling module - recording and processing audio.
"""
import time
import pyaudio
import numpy as np
import utils
from vad import VoiceActivityDetector

logger = utils.setup_logger()

class AudioManager:
    """Audio management class - recording and processing audio."""
    
    def __init__(self):
        """Initialize audio manager."""
        self.sample_rate = utils.get_env("HA_SAMPLE_RATE", 16000, int)
        self.channels = utils.get_env("HA_CHANNELS", 1, int)
        
        # Use same logic as VAD to determine chunk size
        frame_duration_ms = utils.get_env("HA_FRAME_DURATION_MS", 30, int)
        self.chunk_size = int(self.sample_rate * frame_duration_ms / 1000)
        
        self.format = pyaudio.paInt16
        self.audio = None
        self.stream = None
        self.vad = VoiceActivityDetector()
        
        utils.validate_audio_format(self.sample_rate, self.channels)
        
        logger.info(f"AudioManager initialized: {self.sample_rate}Hz, {self.channels} channel(s), chunk {self.chunk_size}")
    
    def init_audio(self):
        """Initialize PyAudio and microphone stream."""
        try:
            self.audio = pyaudio.PyAudio()
            
            mic_device_index = self._find_best_microphone()
            
            if mic_device_index is None:
                logger.error("No microphone found")
                raise Exception("No microphone found")
            
            self.stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                input_device_index=mic_device_index
            )
            
            logger.info(f"Audio stream initialized: {self.sample_rate} Hz, {self.channels} channel(s), chunk {self.chunk_size}")
            return True
            
        except Exception as e:
            logger.exception(f"Audio initialization error: {e}")
            return False
    
    def _find_best_microphone(self):
        """Find best available microphone."""
        default_device = None
        best_device = None
        
        for i in range(self.audio.get_device_count()):
            try:
                device_info = self.audio.get_device_info_by_index(i)
                logger.debug(f"Audio device {i}: {device_info['name']} - input channels: {device_info.get('maxInputChannels', 0)}")
                
                if device_info.get('maxInputChannels', 0) > 0:
                    if i == self.audio.get_default_input_device_info()['index']:
                        default_device = i
                        logger.info(f"Found default microphone: {device_info['name']}")
                    
                    if best_device is None:
                        best_device = i
                        logger.info(f"Found microphone: {device_info['name']}")
                        
            except Exception as e:
                logger.debug(f"Error checking device {i}: {e}")
                continue
        
        return default_device if default_device is not None else best_device
    
    def close_audio(self):
        """Close audio stream and PyAudio."""
        try:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None
                logger.info("Audio stream closed")
            
            if self.audio:
                self.audio.terminate()
                self.audio = None
                logger.info("PyAudio terminated")
                
        except Exception as e:
            logger.error(f"Audio closing error: {e}")
    
    async def record_audio(self, on_chunk_callback, on_end_callback=None):
        """
        Record audio with voice activity detection.
        
        Args:
            on_chunk_callback: Function called for each audio chunk
            on_end_callback: Optional function called at end of recording
        """
        if not self.stream:
            logger.error("Audio stream not initialized")
            return False
        
        logger.info("Starting recording with VAD detection")
        
        self.vad.reset()
        
        start_time = time.time()
        chunks_processed = 0
        
        try:
            waiting_for_speech = True
            speech_active = False
            
            while True:
                try:
                    data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                    chunks_processed += 1
                    
                except Exception as e:
                    logger.error(f"Audio read error: {e}")
                    break
                
                process_chunk, is_end = self.vad.process_audio(data)
                
                if waiting_for_speech:
                    if process_chunk:
                        waiting_for_speech = False
                        speech_active = True
                        logger.info("Started speech processing")
                
                if speech_active:
                    if process_chunk:
                        try:
                            await on_chunk_callback(data)
                        except Exception as e:
                            logger.error(f"Audio chunk callback error: {e}")
                    
                    if is_end:
                        speech_active = False
                        duration = time.time() - start_time
                        logger.info(f"Recording completed after {utils.format_duration(duration)}, processed {chunks_processed} chunks")
                        
                        if on_end_callback:
                            try:
                                await on_end_callback()
                            except Exception as e:
                                logger.error(f"Audio end callback error: {e}")
                        break
        
        except Exception as e:
            logger.exception(f"Error during recording: {str(e)}")
            return False
        
        logger.info("Recording completed")
        return True
    
    def get_audio_level(self, audio_data):
        """Calculate volume level for given audio chunk."""
        try:
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Calculate RMS (Root Mean Square)
            rms = np.sqrt(np.mean(audio_array**2))
            
            # Normalize to 0-1 range
            # Maximum value for 16-bit audio is 32767
            level = min(rms / 32767.0, 1.0)
            
            return level
            
        except Exception as e:
            logger.error(f"Audio level calculation error: {e}")
            return 0.0
    
    def is_audio_stream_active(self):
        """Check if audio stream is active."""
        return self.stream is not None and self.stream.is_active()
    
    def get_device_info(self):
        """Return information about currently used audio device."""
        if not self.audio or not self.stream:
            return None
        
        try:
            device_index = self.stream._input_device_index
            return self.audio.get_device_info_by_index(device_index)
        except Exception as e:
            logger.error(f"Error getting device info: {e}")
            return None