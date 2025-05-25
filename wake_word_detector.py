"""
Wake Word Detection module using openWakeWord
"""
import os
import time
import threading
import numpy as np
import pyaudio
import utils

logger = utils.setup_logger()

class WakeWordDetector:
    """Wake word detector using openWakeWord library."""
    
    def __init__(self, callback=None):
        """Initialize wake word detector."""
        # Safe boolean parsing for enabled flag
        enabled_str = utils.get_env("HA_WAKE_WORD_ENABLED", "false")
        if isinstance(enabled_str, str):
            self.enabled = enabled_str.lower() in ('true', '1', 'yes', 'y', 't')
        else:
            self.enabled = bool(enabled_str)
            
        self.models_dir = os.path.join(os.path.dirname(__file__), 'models')
        self.sample_rate = 16000  # openWakeWord requires 16kHz
        self.chunk_size = int(self.sample_rate * 0.08)  # 80ms frames
        
        self.audio = None
        self.stream = None
        self.model = None
        self.is_running = False
        self.detection_callback = callback
        
        # Detection parameters
        self.detection_threshold = utils.get_env("HA_WAKE_WORD_THRESHOLD", 0.5, float)
        self.vad_threshold = utils.get_env("HA_WAKE_WORD_VAD_THRESHOLD", 0.3, float)
        
        # Safe boolean parsing for noise suppression
        noise_suppression_str = utils.get_env("HA_WAKE_WORD_NOISE_SUPPRESSION", "false")  # Default false for Windows
        if isinstance(noise_suppression_str, str):
            self.noise_suppression = noise_suppression_str.lower() in ('true', '1', 'yes', 'y', 't')
        else:
            self.noise_suppression = bool(noise_suppression_str)
        
        # Model configuration
        self.selected_models = self._get_selected_models()
        
        self._ensure_models_directory()
        
        if self.enabled:
            self._init_openwakeword()
    
    def _ensure_models_directory(self):
        """Ensure models directory exists."""
        if not os.path.exists(self.models_dir):
            os.makedirs(self.models_dir)
            logger.info(f"Created models directory: {self.models_dir}")
    
    def _get_selected_models(self):
        """Get list of selected wake word models."""
        models_config = utils.get_env("HA_WAKE_WORD_MODELS", "alexa")
        if isinstance(models_config, str):
            return [m.strip() for m in models_config.split(',') if m.strip()]
        return models_config if models_config else ["alexa"]
    
    def _init_openwakeword(self):
        """Initialize openWakeWord library."""
        try:
            print("DEBUG: Trying to import openwakeword...")
            import openwakeword
            print("DEBUG: openwakeword imported successfully")
            
            print("DEBUG: Trying to import Model...")
            from openwakeword.model import Model
            print("DEBUG: Model imported successfully")
            
            logger.info("Initializing openWakeWord...")
            
            # Try to use specific models if available, otherwise use defaults
            model_kwargs = {}
            
            # Set VAD threshold if enabled
            if self.vad_threshold > 0:
                model_kwargs['vad_threshold'] = self.vad_threshold
            
            # Set noise suppression if enabled (Linux only)
            if self.noise_suppression:
                try:
                    # Test if speexdsp_ns is available before enabling
                    import speexdsp_ns
                    model_kwargs['enable_speex_noise_suppression'] = True
                    print("DEBUG: Noise suppression enabled")
                except ImportError:
                    logger.warning("Noise suppression not available on this platform (speexdsp_ns not found)")
                    print("DEBUG: Noise suppression disabled - speexdsp_ns not found")
            
            # Try to load specific models first
            model_paths = self._get_model_paths()
            if model_paths:
                # Filter out .tflite models on Windows if tflite-runtime not available
                onnx_paths = [p for p in model_paths if p.endswith('.onnx')]
                tflite_paths = [p for p in model_paths if p.endswith('.tflite')]
                
                if tflite_paths and not onnx_paths:
                    logger.warning("Found .tflite models but tflite-runtime not available on Windows")
                    logger.info("Falling back to default openWakeWord models")
                else:
                    model_kwargs['wakeword_models'] = onnx_paths if onnx_paths else model_paths
                    logger.info(f"Loading specific models: {', '.join(self.selected_models)}")
            else:
                logger.info("Using default openWakeWord models")
            
            print(f"DEBUG: About to create Model with kwargs: {model_kwargs}")
            
            try:
                self.model = Model(**model_kwargs)
                print("DEBUG: Model created successfully")
            except Exception as model_error:
                print(f"DEBUG: Model creation failed: {model_error}")
                if "tflite" in str(model_error).lower() and "wakeword_models" in model_kwargs:
                    logger.warning(f"Failed to load custom models: {model_error}")
                    logger.info("Falling back to default openWakeWord models")
                    # Remove custom models and try with defaults
                    model_kwargs_fallback = {k: v for k, v in model_kwargs.items() if k != 'wakeword_models'}
                    print(f"DEBUG: Trying fallback with kwargs: {model_kwargs_fallback}")
                    self.model = Model(**model_kwargs_fallback)
                    print("DEBUG: Fallback model created successfully")
                else:
                    print(f"DEBUG: Re-raising model error: {model_error}")
                    raise model_error
            
            logger.info(f"✅ Wake word detection initialized")
            logger.info(f"   Models: {', '.join(self.selected_models)}")
            logger.info(f"   Threshold: {self.detection_threshold}")
            logger.info(f"   VAD threshold: {self.vad_threshold}")
            logger.info(f"   Noise suppression: {self.noise_suppression}")
            
            return True
            
        except ImportError as import_error:
            print(f"DEBUG: ImportError: {import_error}")
            logger.error("openWakeWord not installed. Run: pip install openwakeword")
            self.enabled = False
            return False
        except Exception as e:
            print(f"DEBUG: Other error: {e}")
            logger.error(f"Failed to initialize openWakeWord: {e}")
            self.enabled = False
            return False
    
    def _get_model_paths(self):
        """Get full paths to selected model files."""
        paths = []
        
        # Check if models exist in local models directory
        for model_name in self.selected_models:
            for ext in ['.onnx', '.tflite']:
                model_file = f"{model_name}{ext}"
                local_path = os.path.join(self.models_dir, model_file)
                
                if os.path.exists(local_path):
                    paths.append(local_path)
                    logger.info(f"Found local model: {local_path}")
                    break
            else:
                # Model not found locally, will use default if available
                logger.info(f"Model '{model_name}' not found locally, using default if available")
        
        return paths
    
    def start_detection(self):
        """Start wake word detection in background thread."""
        if not self.enabled or not self.model:
            logger.info("Wake word detection disabled or not initialized")
            return False
        
        if self.is_running:
            logger.warning("Wake word detection already running")
            return True
        
        try:
            self._init_audio_stream()
            self.is_running = True
            
            # Start detection thread
            self.detection_thread = threading.Thread(
                target=self._detection_loop, 
                daemon=True
            )
            self.detection_thread.start()
            
            logger.info("🎤 Wake word detection started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start wake word detection: {e}")
            return False
    
    def stop_detection(self):
        """Stop wake word detection."""
        if not self.is_running:
            return
        
        logger.info("Stopping wake word detection...")
        self.is_running = False
        
        if hasattr(self, 'detection_thread') and self.detection_thread.is_alive():
            self.detection_thread.join(timeout=2)
        
        self._close_audio_stream()
        logger.info("Wake word detection stopped")
    
    def _init_audio_stream(self):
        """Initialize audio stream for wake word detection."""
        try:
            self.audio = pyaudio.PyAudio()
            
            # Find microphone
            mic_device_index = self._find_microphone()
            if mic_device_index is None:
                raise Exception("No microphone found")
            
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                input_device_index=mic_device_index
            )
            
            logger.info(f"Audio stream initialized for wake word detection")
            
        except Exception as e:
            logger.error(f"Failed to initialize audio for wake word: {e}")
            raise
    
    def _find_microphone(self):
        """Find best available microphone."""
        if not self.audio:
            return None
        
        default_device = None
        
        try:
            default_info = self.audio.get_default_input_device_info()
            default_device = default_info['index']
        except:
            pass
        
        # Look for working microphone
        for i in range(self.audio.get_device_count()):
            try:
                device_info = self.audio.get_device_info_by_index(i)
                if device_info.get('maxInputChannels', 0) > 0:
                    if default_device is None:
                        default_device = i
                    break
            except:
                continue
        
        return default_device
    
    def _close_audio_stream(self):
        """Close audio stream."""
        try:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None
            
            if self.audio:
                self.audio.terminate()
                self.audio = None
                
        except Exception as e:
            logger.error(f"Error closing wake word audio stream: {e}")
    
    def _detection_loop(self):
        """Main detection loop running in background thread."""
        logger.info("Wake word detection loop started")
        
        try:
            while self.is_running:
                try:
                    # Read audio chunk
                    audio_data = self.stream.read(
                        self.chunk_size, 
                        exception_on_overflow=False
                    )
                    
                    # Convert to numpy array
                    audio_array = np.frombuffer(audio_data, dtype=np.int16)
                    
                    # Get predictions from openWakeWord
                    predictions = self.model.predict(audio_array)
                    
                    # Check for wake word detection
                    self._process_predictions(predictions)
                    
                except Exception as e:
                    if self.is_running:  # Only log if we're supposed to be running
                        logger.error(f"Error in wake word detection loop: {e}")
                    break
            
        except Exception as e:
            logger.error(f"Wake word detection loop crashed: {e}")
        finally:
            logger.info("Wake word detection loop ended")
    
    def _process_predictions(self, predictions):
        """Process wake word predictions and trigger callback if detected."""
        for model_name, score in predictions.items():
            if score >= self.detection_threshold:
                logger.info(f"🎯 Wake word detected: '{model_name}' (confidence: {score:.3f})")
                
                # Call detection callback
                if self.detection_callback:
                    try:
                        self.detection_callback(model_name, score)
                    except Exception as e:
                        logger.error(f"Error in wake word callback: {e}")
                
                # Small delay to avoid multiple rapid detections
                time.sleep(0.5)
                break
    
    def get_model_info(self):
        """Get information about loaded models."""
        info = {
            'enabled': self.enabled,
            'selected_models': self.selected_models,
            'available_models': self._get_available_models(),
            'detection_threshold': self.detection_threshold,
            'vad_threshold': self.vad_threshold,
            'noise_suppression': self.noise_suppression,
            'is_running': self.is_running
        }
        
        return info
    
    def _get_available_models(self):
        """Get list of available model files."""
        models = []
        if os.path.exists(self.models_dir):
            for filename in os.listdir(self.models_dir):
                if filename.endswith(('.onnx', '.tflite')):
                    model_name = os.path.splitext(filename)[0]
                    models.append(model_name)
        return models
    
    def update_threshold(self, new_threshold):
        """Update detection threshold dynamically."""
        if 0.0 <= new_threshold <= 1.0:
            self.detection_threshold = new_threshold
            logger.info(f"Wake word threshold updated to: {new_threshold}")
            return True
        return False
    
    def reload_models(self):
        """Reload wake word models with current configuration."""
        if self.is_running:
            self.stop_detection()
        
        self.selected_models = self._get_selected_models()
        self.detection_threshold = utils.get_env("HA_WAKE_WORD_THRESHOLD", 0.5, float)
        self.vad_threshold = utils.get_env("HA_WAKE_WORD_VAD_THRESHOLD", 0.3, float)
        
        # Safe boolean parsing for noise suppression
        noise_suppression_str = utils.get_env("HA_WAKE_WORD_NOISE_SUPPRESSION", "true")
        if isinstance(noise_suppression_str, str):
            self.noise_suppression = noise_suppression_str.lower() in ('true', '1', 'yes', 'y', 't')
        else:
            self.noise_suppression = bool(noise_suppression_str)
        
        if self.enabled:
            success = self._init_openwakeword()
            if success:
                return self.start_detection()
        
        return False


def download_default_models():
    """Download default openWakeWord models."""
    try:
        import openwakeword
        logger.info("Downloading default wake word models...")
        openwakeword.utils.download_models()
        logger.info("✅ Default models downloaded successfully")
        return True
    except ImportError:
        logger.error("openWakeWord not installed")
        return False
    except Exception as e:
        logger.error(f"Failed to download models: {e}")
        return False


def list_available_models():
    """List all available wake word models."""
    models_dir = os.path.join(os.path.dirname(__file__), 'models')
    
    if not os.path.exists(models_dir):
        return []
    
    models = []
    for filename in os.listdir(models_dir):
        if filename.endswith(('.onnx', '.tflite')):
            model_name = os.path.splitext(filename)[0]
            models.append(model_name)
    
    return sorted(models)


def validate_wake_word_config():
    """Validate wake word configuration."""
    issues = []
    
    # Safe boolean parsing for enabled check
    enabled_str = utils.get_env("HA_WAKE_WORD_ENABLED", "false")
    if isinstance(enabled_str, str):
        enabled = enabled_str.lower() in ('true', '1', 'yes', 'y', 't')
    else:
        enabled = bool(enabled_str)
    
    if not enabled:
        return issues  # No validation needed if disabled
    
    try:
        import openwakeword
    except ImportError:
        issues.append("openWakeWord library not installed (pip install openwakeword)")
        return issues
    
    threshold = utils.get_env("HA_WAKE_WORD_THRESHOLD", 0.5, float)
    if not 0.0 <= threshold <= 1.0:
        issues.append(f"Invalid wake word threshold: {threshold} (must be 0.0-1.0)")
    
    vad_threshold = utils.get_env("HA_WAKE_WORD_VAD_THRESHOLD", 0.3, float)
    if vad_threshold < 0.0 or vad_threshold > 1.0:
        issues.append(f"Invalid VAD threshold: {vad_threshold} (must be 0.0-1.0)")
    
    models = utils.get_env("HA_WAKE_WORD_MODELS", "alexa")
    if not models:
        issues.append("No wake word models specified")
    
    return issues