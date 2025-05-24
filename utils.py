"""
Application utility functions module.
"""
import os
import logging
import time
import threading
from datetime import datetime
from dotenv import load_dotenv
import requests
import sounddevice as sd
import soundfile as sf
import numpy as np
import io

load_dotenv()

def setup_logger():
    """Configure and return logger."""
    import sys
    
    class FlushHandler(logging.StreamHandler):
        def emit(self, record):
            super().emit(record)
            self.flush()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[FlushHandler(sys.stdout)]
    )
    
    return logging.getLogger('haassist')

def get_env(key, default=None, as_type=str):
    """Get environment variable and optionally convert to specified type."""
    value = _read_from_env_file(key)
    
    if value is None:
        value = os.getenv(key, default)
    
    if value is None:
        return None
    
    if as_type == bool:
        return value.lower() in ('true', '1', 'yes', 'y', 't')
    
    try:
        return as_type(value)
    except (ValueError, TypeError):
        logger.warning(f"Cannot convert '{value}' to type {as_type.__name__} for key {key}")
        return default

def _read_from_env_file(key):
    """Read value directly from .env file."""
    possible_paths = [
        os.path.join(os.path.dirname(__file__), '.env'),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),
        '.env'
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            parts = line.split('=', 1)
                            if len(parts) == 2:
                                env_key, env_value = parts
                                if env_key.strip() == key:
                                    return env_value.strip()
            except Exception as e:
                logger.warning(f"Error reading .env file: {e}")
    
    return None

def get_timestamp():
    """Return current timestamp in milliseconds."""
    return int(time.time() * 1000)

def get_datetime_string():
    """Return formatted date and time string."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def play_audio_from_url(url, host, animation_server=None):
    """
    Play audio from given URL using sounddevice and soundfile.
    Optionally send FFT data to animation server during playback.
    """
    logger = setup_logger()
    
    if not url:
        logger.error("No audio file URL provided")
        return False
    
    try:
        if url.startswith('/'):
            if host.startswith(('localhost', '127.0.0.1', '192.168.', '10.', '172.')):
                protocol = "http"
            else:
                protocol = "https"
            full_url = f"{protocol}://{host}{url}"
        else:
            full_url = url
        
        logger.info(f"Downloading audio from: {full_url}")
        
        response = requests.get(full_url, timeout=10)
        if response.status_code != 200:
            logger.error(f"Audio download error: {response.status_code}")
            return False
        
        audio_buffer = io.BytesIO(response.content)
        
        logger.info("Reading audio file...")
        data, samplerate = sf.read(audio_buffer)
        
        if animation_server:
            logger.info(f"Playing with FFT analysis (samplerate: {samplerate})...")
            return _play_with_fft_analysis(data, samplerate, animation_server)
        else:
            logger.info(f"Standard playback (samplerate: {samplerate})...")
            sd.play(data, samplerate)
            sd.wait()
            logger.info("Audio playback completed")
            return True
            
    except Exception as e:
        logger.exception(f"Audio playback error: {str(e)}")
        return False

def _play_with_fft_analysis(audio_data, samplerate, animation_server):
    """
    Play audio and simultaneously send FFT data to animation server.
    """
    logger = setup_logger()
    
    try:
        chunk_size = 1024  # FFT chunk size (smaller = faster response)
        
        # Convert stereo to mono if needed
        if len(audio_data.shape) > 1:
            audio_data = np.mean(audio_data, axis=1)
        
        # Convert to int16 for compatibility
        if audio_data.dtype != np.int16:
            audio_data = (audio_data * 32767).astype(np.int16)
        
        total_samples = len(audio_data)
        samples_played = 0
        
        def audio_callback(outdata, frames, time, status):
            nonlocal samples_played
            
            if status:
                logger.warning(f"Audio callback status: {status}")
            
            if samples_played >= total_samples:
                outdata.fill(0)
                return
            
            samples_to_play = min(frames, total_samples - samples_played)
            
            if len(audio_data.shape) == 1:
                if outdata.shape[1] == 2:
                    outdata[:samples_to_play, 0] = audio_data[samples_played:samples_played + samples_to_play]
                    outdata[:samples_to_play, 1] = audio_data[samples_played:samples_played + samples_to_play]
                else:
                    outdata[:samples_to_play, 0] = audio_data[samples_played:samples_played + samples_to_play]
            
            if samples_to_play < frames:
                outdata[samples_to_play:].fill(0)
            
            # FFT analysis - use smaller chunk for better responsiveness
            fft_chunk_size = min(chunk_size, samples_to_play)
            if fft_chunk_size > 0:
                chunk_data = audio_data[samples_played:samples_played + fft_chunk_size]
                
                threading.Thread(
                    target=_send_fft_to_animation, 
                    args=(chunk_data, animation_server), 
                    daemon=True
                ).start()
            
            samples_played += samples_to_play
        
        logger.info("Starting playback with FFT analysis...")
        
        with sd.OutputStream(
            samplerate=samplerate,
            channels=2,  # Stereo output
            callback=audio_callback,
            dtype=np.int16
        ):
            duration = len(audio_data) / samplerate
            logger.info(f"Audio duration: {duration:.2f}s")
            time.sleep(duration + 0.5)
        
        logger.info("FFT analysis playback completed")
        return True
        
    except Exception as e:
        logger.exception(f"FFT analysis playback error: {str(e)}")
        return False

def _send_fft_to_animation(audio_chunk, animation_server):
    """
    Perform FFT analysis and send data to animation server.
    Called in separate thread.
    """
    try:
        if len(audio_chunk) == 0:
            return
            
        if audio_chunk.dtype != np.int16:
            audio_chunk = audio_chunk.astype(np.int16)
        audio_chunk = (audio_chunk * 0.6).astype(np.int16)
        audio_bytes = audio_chunk.tobytes()
        
        animation_server.send_audio_data(audio_bytes, 16000)
        
    except Exception as e:
        pass

def validate_audio_format(sample_rate, channels=1):
    """Validate audio parameters."""
    valid_rates = [8000, 16000, 22050, 44100, 48000]
    if sample_rate not in valid_rates:
        logger = setup_logger()
        logger.warning(f"Unusual sample rate: {sample_rate}Hz")
    
    if channels not in [1, 2]:
        logger = setup_logger()
        logger.warning(f"Unusual channel count: {channels}")
    
    return True

def play_feedback_sound(sound_name):
    """
    Play feedback sound (activation.wav, deactivation.wav) from 'sound' folder.
    
    Args:
        sound_name: Sound name ('activation' or 'deactivation')
    """
    sound_enabled = get_env('HA_SOUND_FEEDBACK', 'true')
    if sound_enabled.lower() not in ('true', '1', 'yes', 'y', 't'):
        return False
    
    logger = setup_logger()
    
    try:
        sound_dir = os.path.join(os.path.dirname(__file__), 'sound')
        sound_file = os.path.join(sound_dir, f"{sound_name}.wav")
        
        if not os.path.exists(sound_file):
            logger.warning(f"Sound file not found: {sound_file}")
            return False
        
        def play_thread():
            try:
                data, samplerate = sf.read(sound_file)
                sd.play(data, samplerate)
                
            except Exception as e:
                logger.error(f"Error playing sound {sound_name}: {e}")
        
        thread = threading.Thread(target=play_thread, daemon=True)
        thread.start()
        
        logger.debug(f"Playing sound: {sound_name}")
        return True
        
    except Exception as e:
        logger.error(f"Feedback sound playback error {sound_name}: {e}")
        return False

def format_duration(seconds):
    """Format duration in seconds to readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}h {minutes}m {secs:.1f}s"

logger = setup_logger()