"""
Wake Word Detection module using openWakeWord
"""
import os
import time
import threading
import numpy as np
import pyaudio
import utils
import platform
import re
from platform_utils import check_wake_word_noise_suppression

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
            
        self.local_models_dir = os.path.join(os.path.dirname(__file__), 'models')
        # Keep models_dir for backward compatibility with existing code paths.
        self.models_dir = self.local_models_dir
        self.default_model_dirs = []
        self.model_search_dirs = [self.local_models_dir]
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
        if not os.path.exists(self.local_models_dir):
            os.makedirs(self.local_models_dir)
            logger.info(f"Created models directory: {self.local_models_dir}")

    def _discover_openwakeword_model_dirs(self, openwakeword_module):
        """Find default model directories used by installed openWakeWord."""
        dirs = []
        package_dir = os.path.dirname(openwakeword_module.__file__)

        candidates = [
            os.path.join(package_dir, "resources", "models"),
            os.path.join(package_dir, "resources"),
            os.path.join(os.path.expanduser("~"), ".cache", "openwakeword", "models"),
            os.path.join(os.path.expanduser("~"), ".cache", "openwakeword"),
        ]

        # Try to read known attributes from openwakeword.utils if present.
        try:
            ow_utils = openwakeword_module.utils
            for attr in ("MODELS_DIR", "MODEL_DIR", "PRETRAINED_MODELS_DIR"):
                value = getattr(ow_utils, attr, None)
                if isinstance(value, str) and value.strip():
                    candidates.append(value.strip())
        except Exception:
            pass

        seen = set()
        for path in candidates:
            norm = os.path.normpath(path)
            if norm not in seen:
                seen.add(norm)
                dirs.append(norm)
        return dirs

    def _list_model_files(self, directory):
        """List model files in a directory."""
        files = []
        if not directory or not os.path.isdir(directory):
            return files
        try:
            for filename in os.listdir(directory):
                if filename.endswith((".onnx", ".tflite")):
                    files.append(os.path.join(directory, filename))
        except Exception:
            pass
        return files

    def _ensure_default_models_available(self, openwakeword_module):
        """Download default models if installed openWakeWord has no model files."""
        existing = []
        for model_dir in self.default_model_dirs:
            existing.extend(self._list_model_files(model_dir))
        if existing:
            return

        logger.warning("No default openWakeWord model files found; attempting download")
        try:
            openwakeword_module.utils.download_models()
        except Exception as e:
            logger.warning(f"Default model download failed: {e}")

        # Refresh directories after potential download
        self.default_model_dirs = self._discover_openwakeword_model_dirs(openwakeword_module)
        self.model_search_dirs = [self.local_models_dir] + [
            d for d in self.default_model_dirs if d != self.local_models_dir
        ]
    
    def _get_selected_models(self):
        """Get list of selected wake word models."""
        models_config = utils.get_env("HA_WAKE_WORD_MODELS", "alexa")
        if isinstance(models_config, str):
            return [m.strip() for m in models_config.split(',') if m.strip()]
        return models_config if models_config else ["alexa"]

    def _normalize_model_name(self, model_name):
        """Normalize model names (e.g., hey_mycroft_v0.1 -> hey_mycroft)."""
        name = os.path.splitext(str(model_name))[0].lower().strip()
        name = re.sub(r"_v\d+(?:\.\d+)?$", "", name)
        return name

    def _find_model_file(self, model_name, extension):
        """Find best matching model file in configured search directories."""
        # 1) Exact filename match first
        exact_filename = f"{model_name}{extension}"
        for search_dir in self.model_search_dirs:
            candidate = os.path.join(search_dir, exact_filename)
            if os.path.exists(candidate):
                return candidate

        # 2) Fallback to versioned filenames (e.g., hey_mycroft_v0.1.onnx)
        prefix = f"{model_name}_v"
        matches = []
        for search_dir in self.model_search_dirs:
            if not os.path.isdir(search_dir):
                continue
            try:
                for filename in os.listdir(search_dir):
                    if filename.startswith(prefix) and filename.endswith(extension):
                        matches.append(os.path.join(search_dir, filename))
            except Exception:
                continue
        if matches:
            return sorted(matches)[-1]
        return None
    
    def _init_openwakeword(self):
        """Initialize openWakeWord library."""
        try:
            logger.debug("Trying to import openwakeword...")
            import openwakeword
            logger.debug("openwakeword imported successfully")
            self.default_model_dirs = self._discover_openwakeword_model_dirs(openwakeword)
            self.model_search_dirs = [self.local_models_dir] + [
                d for d in self.default_model_dirs if d != self.local_models_dir
            ]
            self._ensure_default_models_available(openwakeword)
            
            logger.debug("Trying to import openwakeword Model...")
            from openwakeword.model import Model
            logger.debug("Model imported successfully")
            
            logger.info("Initializing openWakeWord...")
            
            # Try to use specific models if available, otherwise use defaults
            model_kwargs = {}
            
            # Set VAD threshold if enabled
            if self.vad_threshold > 0:
                model_kwargs['vad_threshold'] = self.vad_threshold
            
            if self.noise_suppression and check_wake_word_noise_suppression():
                model_kwargs['enable_speex_noise_suppression'] = True
                logger.info("Noise suppression enabled")
            else:
                if self.noise_suppression:
                    logger.warning("Noise suppression requested but not available")
            
            # Try to load specific models first
            model_paths = self._get_model_paths()
            if model_paths:
                onnx_paths = [p for p in model_paths if p.endswith('.onnx')]
                tflite_paths = [p for p in model_paths if p.endswith('.tflite')]
                
                # Platform-specific model preference
                if platform.system() == "Linux":
                    # Linux: prefer ONNX by default for compatibility with modern NumPy stacks.
                    prefer_tflite = utils.get_env_bool("HA_WAKE_WORD_PREFER_TFLITE", False)
                    if prefer_tflite and tflite_paths:
                        try:
                            import tflite_runtime
                            model_kwargs['wakeword_models'] = tflite_paths
                            model_kwargs['inference_framework'] = "tflite"
                            logger.info(f"Loading TFLite models on Linux: {', '.join(self.selected_models)}")
                        except ImportError:
                            logger.warning("TFLite runtime not available, trying ONNX...")
                            if onnx_paths:
                                model_kwargs['wakeword_models'] = onnx_paths
                                model_kwargs['inference_framework'] = "onnx"
                                logger.info(f"Loading ONNX models as fallback: {', '.join(self.selected_models)}")
                            else:
                                logger.info("Falling back to default openWakeWord models")
                    elif onnx_paths:
                        model_kwargs['wakeword_models'] = onnx_paths
                        model_kwargs['inference_framework'] = "onnx"
                        logger.info(f"Loading ONNX models on Linux: {', '.join(self.selected_models)}")
                    elif tflite_paths:
                        logger.warning("Using TFLite models on Linux as fallback")
                        model_kwargs['wakeword_models'] = tflite_paths
                        model_kwargs['inference_framework'] = "tflite"
                    else:
                        logger.info("No custom models found, using defaults")
                else:
                    # Windows: prefer ONNX, avoid TFLite due to compatibility issues
                    if onnx_paths:
                        model_kwargs['wakeword_models'] = onnx_paths
                        model_kwargs['inference_framework'] = "onnx"
                        logger.info(f"Loading ONNX models on Windows: {', '.join(self.selected_models)}")
                    elif tflite_paths:
                        logger.warning("Found .tflite models but tflite-runtime not reliable on Windows")
                        logger.info("Falling back to default openWakeWord models")
                    else:
                        logger.info("Using default openWakeWord models")
            else:
                logger.info("Using default openWakeWord models")
            
            logger.debug(f"Creating Model with kwargs: {model_kwargs}")
            
            try:
                self.model = Model(**model_kwargs)
                logger.debug("Model created successfully")
            except Exception as model_error:
                logger.debug(f"Model creation failed: {model_error}")
                # Retry with explicit ONNX backend if ONNX models were provided but framework mismatched.
                if (
                    "wakeword_models" in model_kwargs
                    and any(str(p).endswith(".onnx") for p in model_kwargs.get("wakeword_models", []))
                    and "inference framework is selected" in str(model_error).lower()
                ):
                    logger.warning(f"Retrying wake word model with explicit ONNX framework: {model_error}")
                    retry_kwargs = dict(model_kwargs)
                    retry_kwargs["inference_framework"] = "onnx"
                    logger.debug(f"Retrying with kwargs: {retry_kwargs}")
                    self.model = Model(**retry_kwargs)
                    logger.debug("Retry model created successfully")
                    logger.info(f" Wake word detection initialized")
                    logger.info(f"   Models: {', '.join(self.selected_models)}")
                    logger.info(f"   Threshold: {self.detection_threshold}")
                    logger.info(f"   VAD threshold: {self.vad_threshold}")
                    logger.info(f"   Noise suppression: {self.noise_suppression}")
                    return True
                if "tflite" in str(model_error).lower() and "wakeword_models" in model_kwargs:
                    logger.warning(f"Failed to load custom models: {model_error}")
                    logger.info("Falling back to default openWakeWord models")
                    # Remove custom models and try with defaults
                    model_kwargs_fallback = {k: v for k, v in model_kwargs.items() if k != 'wakeword_models'}
                    logger.debug(f"Trying fallback with kwargs: {model_kwargs_fallback}")
                    self.model = Model(**model_kwargs_fallback)
                    logger.debug("Fallback model created successfully")
                else:
                    logger.debug(f"Re-raising model error: {model_error}")
                    raise model_error
            
            logger.info(f" Wake word detection initialized")
            logger.info(f"   Models: {', '.join(self.selected_models)}")
            logger.info(f"   Threshold: {self.detection_threshold}")
            logger.info(f"   VAD threshold: {self.vad_threshold}")
            logger.info(f"   Noise suppression: {self.noise_suppression}")
            
            return True
            
        except ImportError as import_error:
            logger.debug(f"ImportError while initializing wake word detector: {import_error}")
            logger.error("openWakeWord not installed. Run: pip install openwakeword")
            self.enabled = False
            return False
        except Exception as e:
            logger.debug(f"Other wake word initialization error: {e}")
            logger.error(f"Failed to initialize openWakeWord: {e}")
            self.enabled = False
            return False
    
    def _get_model_paths(self):
        """Get full paths to selected model files with Linux preference."""
        paths = []
        
        for model_name in self.selected_models:
            model_found = False
            
            # On Linux, prefer ONNX first by default for runtime compatibility.
            if platform.system() == "Linux":
                prefer_tflite = utils.get_env_bool("HA_WAKE_WORD_PREFER_TFLITE", False)
                extensions = ['.tflite', '.onnx'] if prefer_tflite else ['.onnx', '.tflite']
            else:
                extensions = ['.onnx', '.tflite']
            
            for ext in extensions:
                model_path = self._find_model_file(model_name, ext)
                if model_path:
                    paths.append(model_path)
                    logger.info(f"Found model: {model_path}")
                    model_found = True
                if model_found:
                    break
            
            if not model_found:
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
            
            # Start detection thread with lower priority
            self.detection_thread = threading.Thread(
                target=self._detection_loop_wrapper, 
                daemon=True,
                name="WakeWordDetection"
            )
            self.detection_thread.start()
            
            logger.info(" Wake word detection started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start wake word detection: {e}")
            return False
    
    def _detection_loop_wrapper(self):
        """Wrapper for detection loop with priority adjustment."""
        import os
        
        try:
            # Lower thread priority on Windows for better GUI responsiveness
            if os.name == 'nt':
                import ctypes
                
                # Get current thread handle
                kernel32 = ctypes.windll.kernel32
                current_thread = kernel32.GetCurrentThread()
                
                # Set to below normal priority
                THREAD_PRIORITY_BELOW_NORMAL = -1
                kernel32.SetThreadPriority(current_thread, THREAD_PRIORITY_BELOW_NORMAL)
                logger.debug("Wake word detection thread priority lowered")
                
        except Exception as e:
            logger.debug(f"Could not lower thread priority: {e}")
        
        # Run actual detection loop
        self._detection_loop()
    
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
        """Find microphone based on configuration or auto-detect."""
        if not self.audio:
            return None
        
        # Sprawdź czy użytkownik wybrał konkretny mikrofon
        mic_index = utils.get_env("HA_MICROPHONE_INDEX", -1, int)
        
        if mic_index >= 0:
            try:
                device_info = self.audio.get_device_info_by_index(mic_index)
                if device_info.get('maxInputChannels', 0) > 0:
                    logger.info(f"Wake word using selected microphone: {device_info['name']}")
                    return mic_index
                else:
                    logger.warning(f"Selected microphone {mic_index} has no input channels for wake word")
            except Exception as e:
                logger.warning(f"Selected microphone {mic_index} not available for wake word: {e}")
        
        # Fallback do automatycznego wyboru (oryginalny kod)
        default_device = None
        
        try:
            default_info = self.audio.get_default_input_device_info()
            default_device = default_info['index']
            logger.info(f"Wake word using default microphone: {default_info['name']}")
        except:
            pass
        
        # Look for working microphone
        for i in range(self.audio.get_device_count()):
            try:
                device_info = self.audio.get_device_info_by_index(i)
                if device_info.get('maxInputChannels', 0) > 0:
                    if default_device is None:
                        default_device = i
                        logger.info(f"Wake word found microphone: {device_info['name']}")
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
                    
                    # Small delay to prevent CPU saturation and improve system responsiveness
                    # This is crucial for keeping GUI responsive
                    import time
                    time.sleep(0.01)  # 10ms delay - imperceptible for wake word detection
                    
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
        selected_models_normalized = {self._normalize_model_name(m) for m in self.selected_models}

        for model_name, score in predictions.items():
            if score >= self.detection_threshold:
                model_name_normalized = self._normalize_model_name(model_name)
                # Trigger when exact selected name or normalized selected base matches.
                if model_name in self.selected_models or model_name_normalized in selected_models_normalized:
                    logger.info(f"Wake word detected: '{model_name}' (confidence: {score:.3f})")
                    
                    # Call detection callback
                    if self.detection_callback:
                        try:
                            self.detection_callback(model_name, score)
                        except Exception as e:
                            logger.error(f"Error in wake word callback: {e}")
                    
                    # Small delay to avoid multiple rapid detections
                    time.sleep(0.5)
                    break
                else:
                    # Log detection of unselected models for debugging
                    logger.debug(f"Ignoring wake word '{model_name}' (confidence: {score:.3f}) - not in selected models: {self.selected_models}")
    
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
        models = set()
        for search_dir in self.model_search_dirs:
            if os.path.isdir(search_dir):
                for filename in os.listdir(search_dir):
                    if filename.endswith(('.onnx', '.tflite')):
                        model_name = os.path.splitext(filename)[0]
                        models.add(model_name)
        return sorted(models)
    
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
        logger.info(" Default models downloaded successfully")
        return True
    except ImportError:
        logger.error("openWakeWord not installed")
        return False
    except Exception as e:
        logger.error(f"Failed to download models: {e}")
        return False


def list_available_models():
    """List all available wake word models."""
    models = set()
    local_models_dir = os.path.join(os.path.dirname(__file__), 'models')
    search_dirs = [local_models_dir]

    try:
        import openwakeword
        package_dir = os.path.dirname(openwakeword.__file__)
        search_dirs.extend([
            os.path.join(package_dir, "resources", "models"),
            os.path.join(package_dir, "resources"),
            os.path.join(os.path.expanduser("~"), ".cache", "openwakeword", "models"),
            os.path.join(os.path.expanduser("~"), ".cache", "openwakeword"),
        ])
    except Exception:
        pass

    for directory in search_dirs:
        if not os.path.isdir(directory):
            continue
        for filename in os.listdir(directory):
            if filename.endswith(('.onnx', '.tflite')):
                model_name = os.path.splitext(filename)[0]
                models.add(model_name)

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
