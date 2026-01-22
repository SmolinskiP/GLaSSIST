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

def safe_print(text):
    """
    Print text safely, handling Unicode encoding issues on Windows.
    
    Args:
        text: The text to print (string)
    """
    try:
        print(text)
    except UnicodeEncodeError:
        # Handle encoding issues by encoding to UTF-8 with error replacement
        safe_text = str(text).encode('utf-8', errors='replace').decode('utf-8')
        print(safe_text)

def setup_logger():
    """Configure and return logger with optional file logging when DEBUG=true."""
    import sys
    
    class FlushHandler(logging.StreamHandler):
        def emit(self, record):
            super().emit(record)
            self.flush()
    
    handlers = [FlushHandler(sys.stdout)]
    
    # Add file handler if DEBUG mode is enabled
    debug_enabled = get_env_bool('DEBUG', False)
    if debug_enabled:
        try:
            log_dir = os.path.join(os.path.dirname(__file__), 'logs')
            os.makedirs(log_dir, exist_ok=True)
            
            log_file = os.path.join(log_dir, f'glasssist_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            handlers.append(file_handler)
            
            print(f"Debug logging enabled - logs saved to: {log_file}")
            
        except Exception as e:
            print(f"Warning: Could not setup file logging: {e}")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers,
        force=True  # Override any existing configuration
    )
    
    return logging.getLogger('haassist')

def get_env_bool(key, default=False):
    """Get environment variable as boolean with safe parsing."""
    value = get_env(key, str(default).lower())
    
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 'y', 't')
    else:
        return bool(value)

def get_env(key, default=None, as_type=str):
    """Get environment variable and optionally convert to specified type."""
    value = _read_from_env_file(key)
    
    if value is None:
        value = os.getenv(key, default)
    
    if value is None:
        return None
    
    if as_type == bool:
        # Safe boolean parsing
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'y', 't')
        else:
            return bool(value)
    
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

def get_output_device_index():
    """Return configured output device index or None for automatic selection."""
    output_device = get_env("HA_OUTPUT_DEVICE_INDEX", -1, int)
    if output_device is None or output_device < 0:
        return None
    return output_device

def get_output_sample_rate():
    """Return configured output sample rate or None for automatic selection."""
    output_rate = get_env("HA_OUTPUT_SAMPLE_RATE", -1, int)
    if output_rate is None or output_rate <= 0:
        return None
    return output_rate

def get_available_output_devices():
    """Return a list of available output devices."""
    devices = []
    try:
        for index, device_info in enumerate(sd.query_devices()):
            if device_info.get('max_output_channels', 0) > 0:
                device_name = device_info.get('name', f"Output {index}")
                if isinstance(device_name, bytes):
                    device_name = device_name.decode('utf-8', errors='replace')
                device_name = str(device_name).replace('\x00', '').strip()
                if not device_name:
                    device_name = f"Output {index}"
                
                devices.append({
                    'index': index,
                    'name': device_name,
                    'channels': device_info.get('max_output_channels', 0),
                    'sample_rate': device_info.get(
                        'default_samplerate',
                        device_info.get('defaultSampleRate', 'unknown')
                    )
                })
    except Exception as e:
        logger.error(f"Failed to query output devices: {e}")
    
    return devices

def _resample_audio(audio_data, original_rate, target_rate):
    """Resample audio data to the target rate."""
    if original_rate == target_rate or target_rate is None:
        return audio_data

    try:
        from scipy.signal import resample_poly
    except Exception as e:
        logger.warning(f"Resampling unavailable: {e}")
        return audio_data

    try:
        import math
        original_rate = int(original_rate)
        target_rate = int(target_rate)
        if original_rate <= 0 or target_rate <= 0:
            return audio_data

        divisor = math.gcd(original_rate, target_rate)
        up = target_rate // divisor
        down = original_rate // divisor

        data = audio_data
        if data.dtype == np.int16:
            data = data.astype(np.float32) / 32768.0
        elif data.dtype.kind in ("i", "u"):
            data = data.astype(np.float32)
        else:
            data = data.astype(np.float32)

        return resample_poly(data, up, down, axis=0)
    except Exception as e:
        logger.warning(f"Failed to resample audio: {e}")
        return audio_data

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
        import tempfile
        data = None
        samplerate = None

        # Try audioread first (better MP3 support via system codecs)
        try:
            import audioread
            audio_buffer.seek(0)

            # Save to temp file for audioread
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
                tmp_path = tmp_file.name
                tmp_file.write(response.content)

            with audioread.audio_open(tmp_path) as f:
                samplerate = f.samplerate
                channels = f.channels
                # Read all audio data
                audio_bytes = b''.join(f)

            # Convert bytes to numpy array (16-bit signed integers)
            data = np.frombuffer(audio_bytes, dtype=np.int16)
            # Normalize to float32 [-1, 1]
            data = data.astype(np.float32) / 32768.0
            if channels == 2:
                data = data.reshape((-1, 2))
            logger.info(f"Decoded with audioread: {len(data)} samples, {samplerate}Hz, {channels}ch")

            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except:
                pass
        except Exception as e:
            logger.warning(f"audioread failed, falling back to soundfile: {e}")
            audio_buffer.seek(0)
            data, samplerate = sf.read(audio_buffer)
        output_device_index = get_output_device_index()
        output_sample_rate = get_output_sample_rate()
        if output_device_index is not None:
            logger.debug(f"Using output device index: {output_device_index}")
        if output_sample_rate is not None and output_sample_rate != samplerate:
            logger.info(f"Resampling audio from {samplerate}Hz to {output_sample_rate}Hz")
            data = _resample_audio(data, samplerate, output_sample_rate)
            samplerate = output_sample_rate
        if animation_server:
            logger.info(f"Playing with FFT analysis (samplerate: {samplerate})...")
            return _play_with_fft_analysis(
                data,
                samplerate,
                animation_server,
                output_device_index
            )
        else:
            logger.info(f"Standard playback (samplerate: {samplerate})...")
            if output_device_index is not None:
                sd.play(data, samplerate, device=output_device_index)
            else:
                sd.play(data, samplerate)
            sd.wait()
            logger.info("Audio playback completed")
            return True
            
    except Exception as e:
        logger.exception(f"Audio playback error: {str(e)}")
        return False

def _play_with_fft_analysis(audio_data, samplerate, animation_server, output_device_index=None):
    """
    Play audio and simultaneously send FFT data to animation server.
    Uses simple sd.play() + sd.wait() for reliable playback.
    """
    logger = setup_logger()

    try:
        chunk_size = 1024  # FFT chunk size

        # Convert stereo to mono for FFT analysis (keep original for playback)
        if len(audio_data.shape) > 1:
            fft_data = np.mean(audio_data, axis=1)
        else:
            fft_data = audio_data

        # Convert FFT data to int16 for animation
        if fft_data.dtype != np.int16:
            if np.abs(fft_data).max() <= 1.0:
                fft_data = (fft_data * 32767).astype(np.int16)
            else:
                fft_data = fft_data.astype(np.int16)

        total_samples = len(fft_data)
        duration = total_samples / samplerate
        logger.info(f"Starting playback with FFT analysis... Duration: {duration:.2f}s")

        # Start FFT analysis in background thread
        stop_fft = threading.Event()

        def fft_thread_func():
            """Send FFT data to animation server during playback."""
            samples_sent = 0
            start_time = time.time()

            while not stop_fft.is_set() and samples_sent < total_samples:
                elapsed = time.time() - start_time
                target_sample = int(elapsed * samplerate)

                if target_sample > samples_sent and samples_sent < total_samples:
                    chunk_end = min(samples_sent + chunk_size, total_samples)
                    chunk_data = fft_data[samples_sent:chunk_end]

                    if len(chunk_data) > 0:
                        _send_fft_to_animation(chunk_data, animation_server)

                    samples_sent = chunk_end

                time.sleep(0.02)  # ~50 FPS for smooth animation

        fft_thread = threading.Thread(target=fft_thread_func, daemon=True)
        fft_thread.start()

        # Play audio using simple sd.play() + sd.wait()
        # This is the most reliable method
        play_kwargs = {}
        if output_device_index is not None:
            play_kwargs['device'] = output_device_index

        sd.play(audio_data, samplerate, **play_kwargs)
        sd.wait()  # Block until playback is complete

        # Stop FFT thread
        stop_fft.set()
        fft_thread.join(timeout=1.0)

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
    output_device_index = get_output_device_index()
    output_sample_rate = get_output_sample_rate()
    
    try:
        sound_dir = os.path.join(os.path.dirname(__file__), 'sound')
        sound_file = os.path.join(sound_dir, f"{sound_name}.wav")
        
        if not os.path.exists(sound_file):
            logger.warning(f"Sound file not found: {sound_file}")
            return False
        
        def play_thread():
            try:
                data, samplerate = sf.read(sound_file)
                if output_sample_rate is not None and output_sample_rate != samplerate:
                    logger.info(
                        f"Resampling feedback sound from {samplerate}Hz to {output_sample_rate}Hz"
                    )
                    data = _resample_audio(data, samplerate, output_sample_rate)
                    samplerate = output_sample_rate
                if output_device_index is not None:
                    sd.play(data, samplerate, device=output_device_index)
                else:
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
