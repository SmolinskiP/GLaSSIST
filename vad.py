"""
Voice Activity Detection (VAD) module.
"""
import time
import collections
import webrtcvad
import utils

logger = utils.setup_logger()

class VoiceActivityDetector:
    """Voice activity detection class using WebRTC VAD."""
    
    def __init__(self):
        """Initialize voice activity detector."""
        # WebRTC VAD requires sample rate of 8000, 16000 or 32000 Hz
        self.sample_rate = utils.get_env("HA_SAMPLE_RATE", 16000, int)
        if self.sample_rate not in [8000, 16000, 32000]:
            logger.warning(f"Incompatible sample rate: {self.sample_rate}Hz. WebRTC VAD requires 8000, 16000 or 32000 Hz")
            if self.sample_rate < 8000:
                self.sample_rate = 8000
            elif self.sample_rate < 16000:
                self.sample_rate = 8000
            elif self.sample_rate < 32000:
                self.sample_rate = 16000
            else:
                self.sample_rate = 32000
            logger.info(f"Adjusted sample rate to {self.sample_rate}Hz")
        
        self.vad_mode = utils.get_env("HA_VAD_MODE", 3, int)  # 0-3, higher = more aggressive
        
        # WebRTC VAD requires frame length of 10, 20 or 30 ms
        frame_duration_ms = utils.get_env("HA_FRAME_DURATION_MS", 30, int)
        if frame_duration_ms not in [10, 20, 30]:
            logger.warning(f"Incompatible frame duration: {frame_duration_ms}ms. WebRTC VAD requires 10, 20 or 30ms.")
            frame_duration_ms = 30
        
        # Calculate chunk size based on frame duration and sample rate
        self.chunk_size = int(self.sample_rate * frame_duration_ms / 1000)
        
        self.padding_ms = utils.get_env("HA_PADDING_MS", 300, int)  # ms silence at end
        self.silence_threshold_sec = utils.get_env("HA_SILENCE_THRESHOLD_SEC", 0.8, float)
        
        # Initialize WebRTC VAD
        self.vad = webrtcvad.Vad(self.vad_mode)
        
        # Buffer for storing voice frame history
        self.voiced_frames = collections.deque(maxlen=500)
        
        # Detector state
        self.is_speech_active = False
        self.last_voice_time = 0
        
        logger.info(f"VAD initialized: mode={self.vad_mode}, silence threshold={self.silence_threshold_sec}s, chunk size={self.chunk_size}")
    
    def is_speech(self, audio_chunk):
        """Check if given audio chunk contains speech."""
        expected_bytes = self.chunk_size * 2  # 16-bit = 2 bytes per sample
        if len(audio_chunk) != expected_bytes:
            logger.warning(f"Unexpected audio data length: {len(audio_chunk)} bytes, expected {expected_bytes}")
            return False
        
        try:
            return self.vad.is_speech(audio_chunk, self.sample_rate)
        except Exception as e:
            logger.error(f"VAD error: {str(e)}")
            return False
    
    def process_audio(self, audio_chunk):
        """
        Process audio chunk and determine if it's active speech.
        
        Returns:
            tuple: (should_process, should_end)
                - should_process: True if this chunk should be sent
                - should_end: True if this is the last chunk (end of speech)
        """
        try:
            is_speech_chunk = self.is_speech(audio_chunk)
            
            if is_speech_chunk:
                self.last_voice_time = time.time()
                
                if not self.is_speech_active:
                    logger.info("Speech start detected")
                    self.is_speech_active = True
                
                self.voiced_frames.append(audio_chunk)
                return True, False
            else:
                # This is silence - check if it's end of speech
                if self.is_speech_active:
                    silence_duration = time.time() - self.last_voice_time
                    
                    # Add silence chunks at the end
                    if silence_duration < self.silence_threshold_sec:
                        self.voiced_frames.append(audio_chunk)
                        return True, False
                    else:
                        logger.info(f"Speech end detected after {silence_duration:.2f}s silence")
                        self.is_speech_active = False
                        self.voiced_frames.clear()
                        return True, True
                
                # This is silence before speech detection - don't process
                return False, False
        except Exception as e:
            logger.exception(f"Error processing audio: {str(e)}")
            return True, False
    
    def reset(self):
        """Reset detector state."""
        self.is_speech_active = False
        self.last_voice_time = 0
        self.voiced_frames.clear()