"""
Enhanced main.py - preserves original code with improvements
"""
import asyncio
import threading
import webview
import sys
import os
import pystray
from PIL import Image, ImageDraw
from pystray import MenuItem as item
import utils
from client import HomeAssistantClient
from audio import AudioManager
from animation_server import AnimationServer
from wake_word_detector import WakeWordDetector, validate_wake_word_config
import platform
from platform_utils import check_linux_dependencies, hide_window_from_taskbar, get_icon_path
from dummy_animation_server import DummyAnimationServer
from conversation_manager import ConversationManager
from prompt_server import PromptServer

logger = utils.setup_logger()

class HAAssistApp:
    """Main application class with enhanced features."""
    
    def __init__(self):
        """Initialize application."""
        self.ha_client = None
        self.audio_manager = None
        self.animation_server = None
        self.window = None
        self.settings_window = None
        self.is_running = False
        self.tray_icon = None
        self.window_visible = True
        self.wake_word_detector = None
        self.conversation_manager = None
        self.prompt_server = None
        self.animations_enabled = utils.get_env_bool("HA_ANIMATIONS_ENABLED", True)
        self.response_text_enabled = utils.get_env_bool("HA_RESPONSE_TEXT_ENABLED", True)

        # Platform detection
        self.is_linux = platform.system() == "Linux"
        self.is_windows = platform.system() == "Windows"
        # Check platform-specific dependencies
        if self.is_linux and not check_linux_dependencies():
            logger.error("Missing required dependencies for Linux")
            sys.exit(1)

        # Pipeline caching
        self.cached_pipelines = []
        self.pipeline_cache_time = 0
        self._setup_wake_word_detector()

    def _setup_wake_word_detector(self):
        """Setup wake word detector with callback."""
        try:
            self.wake_word_detector = WakeWordDetector(
                callback=self.on_wake_word_detected
            )
            
            if self.wake_word_detector.enabled:
                logger.info("Wake word detector initialized and enabled")
            else:
                logger.info("Wake word detector disabled in configuration")
                
        except Exception as e:
            logger.error(f"Failed to setup wake word detector: {e}")
            self.wake_word_detector = None

    def on_wake_word_detected(self, model_name, confidence):
        """Callback when wake word is detected."""
        logger.info(f" Wake word '{model_name}' detected (confidence: {confidence:.3f})")
        
        # Check if we're not already processing a command
        if self.animation_server.current_state != "hidden":
            logger.info("Application is busy, ignoring wake word")
            return
        
        # Trigger voice command processing
        self.on_voice_command_trigger()

    def start_wake_word_detection(self):
        """Start wake word detection if enabled."""
        if self.wake_word_detector and self.wake_word_detector.enabled:
            success = self.wake_word_detector.start_detection()
            if success:
                logger.info(" Wake word detection started")
            else:
                logger.error(" Failed to start wake word detection")
            return success
        return False
    
    def stop_wake_word_detection(self):
        """Stop wake word detection."""
        if self.wake_word_detector:
            self.wake_word_detector.stop_detection()
            logger.info("Wake word detection stopped")

    def create_tray_icon(self):
        if platform.system() == "Linux":
            logger.info("System tray disabled on Linux - use hotkey ctrl+shift+h")
            return
        """Create system tray icon with cross-platform support."""
        icon_path = get_icon_path()
        
        if icon_path and os.path.exists(icon_path):
            try:
                from PIL import Image
                image = Image.open(icon_path)
                logger.info(f"Loaded tray icon: {icon_path}")
            except Exception as e:
                logger.error(f"Error loading icon: {e}")
                image = self._create_fallback_icon()
        else:
            logger.warning(f"Icon file not found, using fallback")
            image = self._create_fallback_icon()
        
        menu = self._build_tray_menu()
        
        self.tray_icon = pystray.Icon(
            "GLaSSIST",
            image,
            "GLaSSIST Desktop",
            menu
        )
        
        logger.info("System tray icon created")

    def _show_wake_word_status(self, icon=None, item=None):
        """Show wake word detection status with animation."""
        if not self.wake_word_detector:
            print(" Wake word detector not initialized")
            if self.animation_server:
                self.animation_server.show_error("Wake word detector not initialized", duration=4.0)
            return
        
        info = self.wake_word_detector.get_model_info()
        
        status_lines = []
        status_lines.append(f"Enabled: {' Yes' if info['enabled'] else ' No'}")
        status_lines.append(f"Running: {' Yes' if info['is_running'] else ' No'}")
        status_lines.append(f"Models: {', '.join(info['selected_models'])}")
        status_lines.append(f"Threshold: {info['detection_threshold']}")
        
        print("\n=== WAKE WORD STATUS ===")
        for line in status_lines:
            print(line)
        print(f"VAD threshold: {info['vad_threshold']}")
        print(f"Noise suppression: {' Yes' if info['noise_suppression'] else ' No'}")
        print(f"Available models: {len(info['available_models'])}")
        print("========================\n")
        
        if info['enabled'] and info['is_running']:
            animation_message = f"Wake word: ON | Models: {', '.join(info['selected_models'])}"
            
            if self.animation_server:
                self.animation_server.show_success(animation_message, duration=5.0)
            
            print("Say your wake word to test detection!")
            
        elif info['enabled'] and not info['is_running']:
            animation_message = "Wake word enabled but not running"
            
            if self.animation_server:
                self.animation_server.show_error(animation_message, duration=5.0)
            
            print(" Wake word detection enabled but not running")
            
        else:
            animation_message = "Wake word detection disabled"
            
            if self.animation_server:
                self.animation_server.show_error(animation_message, duration=4.0)
            
            print("Enable wake word detection in Settings > Models")

    def _restart_wake_word(self, icon=None, item=None):
        """Restart wake word detection."""
        if not self.wake_word_detector:
            print(" Wake word detector not available")
            return
        
        print(" Restarting wake word detection...")
        
        # Stop current detection
        self.stop_wake_word_detection()
        
        # Reload configuration and restart
        success = self.wake_word_detector.reload_models()
        
        if success:
            print(" Wake word detection restarted successfully")

            if self.animation_server:
                self.animation_server.show_success("Wake word restarted", duration=3.0)
        else:
            print(" Failed to restart wake word detection")

            if self.animation_server:
                self.animation_server.show_error("Wake word restart failed", duration=5.0)

        self._refresh_tray_menu()

    def _get_toggle_label(self):
        """Return label for pause/resume menu item."""
        if self.wake_word_detector and self.wake_word_detector.is_running:
            return '⏸ Pause wake word'
        return '▶️ Resume wake word'

    def _build_tray_menu(self):
        """Construct tray menu reflecting current state."""
        return pystray.Menu(
            item('🎤 Activate voice (%s)' % utils.get_env("HA_HOTKEY", "ctrl+shift+h"),
                 self.trigger_voice_command),
            pystray.Menu.SEPARATOR,
            item(self._get_toggle_label(), self._toggle_wake_word_detection),
            item('🎯 Wake word status', self._show_wake_word_status),
            item('🔄 Restart wake word', self._restart_wake_word),
            pystray.Menu.SEPARATOR,
            item('⚙️ Settings', self.open_settings),
            item('🔄 Test connection', self._quick_connection_test),
            pystray.Menu.SEPARATOR,
            item('❌ Close', self.quit_application)
        )

    def _refresh_tray_menu(self):
        """Update tray menu to reflect current wake word state."""
        if not self.tray_icon:
            return
        self.tray_icon.menu = self._build_tray_menu()
        try:
            self.tray_icon.update_menu()
        except Exception:
            pass

    def _toggle_wake_word_detection(self, icon=None, item=None):
        """Pause or resume wake word detection from tray."""
        if not self.wake_word_detector or not self.wake_word_detector.enabled:
            print(" Wake word detection not available")
            if self.animation_server:
                self.animation_server.show_error("Wake word disabled in settings", duration=3.0)
            return

        if self.wake_word_detector.is_running:
            self.stop_wake_word_detection()
            print(" Wake word detection paused")
            if self.animation_server:
                self.animation_server.show_error("Wake word paused", duration=3.0)
        else:
            started = self.start_wake_word_detection()
            if started:
                print(" Wake word detection resumed")
                if self.animation_server:
                    self.animation_server.show_success("Wake word resumed", duration=3.0)
        self._refresh_tray_menu()

    def _create_fallback_icon(self):
        """Create fallback icon."""
        image = Image.new('RGB', (64, 64), color='black')
        draw = ImageDraw.Draw(image)
        draw.ellipse([8, 8, 56, 56], fill='#4fc3f7', outline='white', width=2)
        draw.ellipse([24, 24, 40, 40], fill='white')
        return image
    
    def _quick_connection_test(self, icon=None, item=None):
        """Quick connection test from tray with animation."""
        def test_thread():
            try:
                test_client = HomeAssistantClient()
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    success, message = loop.run_until_complete(test_client.test_connection())
                    
                    if success:
                        logger.info(f"Connection test:  {message}")
                        print(f" Connection test: {message}")
                        
                        if self.animation_server:
                            self.animation_server.show_success("Connection successful", duration=3.0)
                    else:
                        logger.error(f"Connection test:  {message}")
                        print(f" Connection test: {message}")
                        
                        if self.animation_server:
                            self.animation_server.show_error(f"Connection failed", duration=5.0)
                    
                finally:
                    loop.close()
                    
            except Exception as e:
                error_msg = f"Test error: {str(e)}"
                logger.error(error_msg)
                print(f" {error_msg}")
                
                if self.animation_server:
                    self.animation_server.show_error("Test error", duration=5.0)
        
        threading.Thread(target=test_thread, daemon=True).start()
    
    def _show_pipelines_info(self, icon=None, item=None):
        """Show available pipelines information."""
        def pipelines_thread():
            try:
                test_client = HomeAssistantClient()
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    success = loop.run_until_complete(test_client.connect())
                    
                    if success:
                        pipelines = test_client.get_available_pipelines()
                        current_pipeline = utils.get_env("HA_PIPELINE_ID", "(default)")
                        
                        print(f"\n=== AVAILABLE PIPELINES ({len(pipelines)}) ===")
                        print(f"Currently used: {current_pipeline}")
                        print("-" * 50)
                        
                        if not pipelines:
                            print("No available pipelines or connection error")
                        else:
                            for i, pipeline in enumerate(pipelines, 1):
                                if isinstance(pipeline, str):
                                    name = pipeline
                                    pipeline_id = pipeline
                                    language = "unknown"
                                elif isinstance(pipeline, dict):
                                    name = pipeline.get("name", "Unnamed")
                                    pipeline_id = pipeline.get("id", "")
                                    language = pipeline.get("language", "unknown")
                                else:
                                    name = str(pipeline)
                                    pipeline_id = str(pipeline)
                                    language = "unknown"
                                
                                current_marker = " ← CURRENT" if pipeline_id == current_pipeline else ""
                                
                                print(f"{i}. {name}")
                                print(f"   ID: {pipeline_id}{current_marker}")
                                if language != "unknown":
                                    print(f"   Language: {language}")
                                print()
                            
                            print("=" * 50)
                            print("Use 'Settings' to change pipeline.")
                            
                            if len(pipelines) > 1:
                                print("\n TIP:")
                                print("Copy the ID of chosen pipeline and paste it in app settings.")
                                
                    else:
                        print("Cannot connect to Home Assistant")
                        print("Check connection settings.")
                    
                finally:
                    loop.close()
                    
            except Exception as e:
                error_msg = f"Error fetching pipelines: {str(e)}"
                logger.error(error_msg)
                print(f"{error_msg}")
                
                print(f" DEBUG: Error type: {type(e).__name__}")
                if hasattr(e, '__traceback__'):
                    import traceback
                    print(" Stack trace:")
                    traceback.print_exc()
        
        threading.Thread(target=pipelines_thread, daemon=True).start()

    def setup_animation_server(self):
        """Setup animation server or dummy server based on configuration."""
        if self.animations_enabled:
            from animation_server import AnimationServer
            self.animation_server = AnimationServer()
            logger.info("Real animation server created")
        else:
            self.animation_server = DummyAnimationServer()
            logger.info("Dummy animation server created (animations disabled)")
        
        self.animation_server.set_voice_command_callback(self.on_voice_command_trigger)
        self.animation_server.start()
    
    def setup_conversation_manager(self):
        """Setup conversation manager for interactive prompts."""
        if not (self.ha_client and self.audio_manager and self.animation_server):
            logger.error("Cannot setup conversation manager - dependencies not initialized")
            return False
        
        self.conversation_manager = ConversationManager(
            self.ha_client, 
            self.audio_manager, 
            self.animation_server
        )
        
        # Set conversation manager reference in HA client for context cleanup
        self.ha_client.set_conversation_manager(self.conversation_manager)
        
        logger.info("✅ Conversation manager initialized")
        return True
    
    def setup_prompt_server(self):
        """Setup HTTP server for receiving HA prompts."""
        if not self.conversation_manager:
            logger.error("Cannot setup prompt server - conversation manager not initialized")
            return False
        
        port = utils.get_env("HA_PROMPT_SERVER_PORT", 8766, int)
        self.prompt_server = PromptServer(self.conversation_manager, port)
        
        success = self.prompt_server.start()
        if success:
            logger.info(f"✅ Prompt server listening on port {port}")
            return True
        else:
            logger.error("❌ Failed to start prompt server")
            return False
    
    def setup_webview(self):
        """Setup webview window."""
        frontend_path = os.path.join(os.path.dirname(__file__), 'frontend')
        index_path = os.path.join(frontend_path, 'index.html')
        
        if not os.path.exists(index_path):
            logger.error(f"Frontend file not found: {index_path}")
            return False
        
        icon_path = os.path.join(os.path.dirname(__file__), 'img', 'icon.ico')
        window_width = utils.get_env("WINDOW_WIDTH", 400, int)
        window_height = utils.get_env("WINDOW_HEIGHT", 400, int)
        
        self.window = webview.create_window(
            'GLaSSIST',
            index_path,
            width=window_width,
            height=window_height,
            resizable=False,
            fullscreen=False,
            minimized=False,
            on_top=True,
            shadow=False,
            frameless=True,
            transparent=True,
            y=10
        )
        
        logger.info(f"Webview window configured ({window_width}x{window_height}, hidden from taskbar)")
        return True

    def open_settings(self, icon=None, item=None):
        """Open enhanced settings window."""
        logger.info("Opening enhanced settings...")
        
        try:
            from flet_settings import show_flet_settings
            show_flet_settings(self.animation_server)
            
        except ImportError as e:
            logger.error(f"improved_settings_dialog.py not found: {e}")
            
            import tkinter as tk
            from tkinter import messagebox
            
            root = tk.Tk()
            root.withdraw()
            
            messagebox.showerror(
                "Settings Error", 
                "improved_settings_dialog.py file not found!\n\n"
                "Create this file in application folder\n"
                "or check if all files were copied."
            )
            root.destroy()
            
        except Exception as e:
            logger.exception(f"Error opening settings: {e}")
            
            import tkinter as tk
            from tkinter import messagebox
            
            root = tk.Tk()
            root.withdraw()
            
            messagebox.showerror(
                "Settings Error", 
                f"Error occurred while opening settings:\n\n{str(e)}\n\n"
                "Check application logs for details."
            )
            root.destroy()

    async def process_voice_command(self):
        """Enhanced voice command processing with pipeline validation."""
        # Store references to temporary instances for cleanup
        # temp variables removed - using self.ha_client and self.audio_manager
        
        # Volume management variables
        saved_volumes = {}
        media_player_entities = []
        target_volume = None
        
        try:
            # Load media player configuration
            entities_config = utils.get_env("HA_MEDIA_PLAYER_ENTITIES", "")
            if entities_config:
                media_player_entities = [e.strip() for e in entities_config.split(',') if e.strip()]
                target_volume = utils.get_env("HA_MEDIA_PLAYER_TARGET_VOLUME", 0.3, float)
                logger.info(f"Media player volume management enabled for {len(media_player_entities)} entities")
            
            self.animation_server.change_state("listening")
            utils.play_feedback_sound("activation")
            
            # Use existing instances or create temporary ones
            ha_client = self.ha_client if self.ha_client else HomeAssistantClient()
            audio_manager = self.audio_manager if self.audio_manager else AudioManager()
            
            pipeline_id = utils.get_env("HA_PIPELINE_ID")
            if pipeline_id:
                logger.info(f"Checking pipeline availability: {pipeline_id}")
            
            if not self.audio_manager:  # Only init if not already initialized
                audio_manager.init_audio()
            
            if not await ha_client.connect():
                logger.error("Failed to connect to Home Assistant")
                self.animation_server.change_state("error", "Cannot connect to Home Assistant")
                await asyncio.sleep(5)
                self.animation_server.change_state("hidden")
                utils.play_feedback_sound("deactivation")
                return False
            
            logger.info("Connected to Home Assistant")
            
            # Save current volumes and set target volume immediately
            if media_player_entities and not ha_client.volumes_managed:
                try:
                    logger.info("Saving current volumes and setting target volume immediately")
                    saved_volumes = await ha_client.get_multiple_volumes(media_player_entities)
                    if saved_volumes:
                        logger.info(f"Saved volumes: {saved_volumes}")
                        
                        # Set target volume for all entities immediately
                        target_settings = {entity_id: target_volume for entity_id in media_player_entities}
                        results = await ha_client.set_multiple_volumes(target_settings)
                        logger.info(f"Set target volumes: {results}")
                        ha_client.volumes_managed = True  # Mark as managed
                        ha_client.saved_volumes_for_restore = saved_volumes  # Store for restore
                    else:
                        logger.warning("Could not retrieve current volumes")
                except Exception as e:
                    logger.error(f"Error managing volumes: {e}")
            elif media_player_entities and ha_client.volumes_managed:
                logger.info("Volumes already managed by previous call")
            
            if pipeline_id and not ha_client.validate_pipeline_id(pipeline_id):
                logger.warning(f"Pipeline '{pipeline_id}' not available - using default")
                
            if not await ha_client.start_assist_pipeline(timeout_seconds=30):
                logger.error("Failed to start Assist pipeline")
                self.animation_server.change_state("error", "Cannot start voice assistant")
                await asyncio.sleep(5)
                self.animation_server.change_state("hidden")
                utils.play_feedback_sound("deactivation")
                return False
            
            logger.info("Assist pipeline started successfully")
            
            print("\n=== LISTENING ===")
            print("(Waiting for voice, speak to microphone...)")
            
            async def on_audio_chunk(audio_chunk):
                self.animation_server.send_audio_data(audio_chunk)
                success = await ha_client.send_audio_chunk(audio_chunk)
                if not success:
                    logger.warning("Error sending audio chunk")
            
            async def on_audio_end():
                logger.info("=== SWITCHING TO PROCESSING ===")
                self.animation_server.change_state("processing")
                await asyncio.sleep(0.8)
                
                success = await ha_client.end_audio()
                if not success:
                    logger.warning("Error ending audio")
            
            if await audio_manager.record_audio(on_audio_chunk, on_audio_end):
                logger.info("Audio sent successfully")
                
                logger.info("=== RECEIVING RESPONSE ===")
                results = await ha_client.receive_response(timeout_seconds=45)
                
                error_found = False
                for result in results:
                    if result.get('type') == 'event':
                        event = result.get('event', {})
                        if event.get('type') == 'error':
                            error_code = event.get('data', {}).get('code', 'unknown')
                            error_message = event.get('data', {}).get('message', 'Unknown error')
                            
                            print(f"\n=== ASSISTANT ERROR ===")
                            utils.safe_print(f"Error: {error_code} - {error_message}")
                            print("===========================\n")
                            
                            full_error_message = f"{error_code}: {error_message}"
                            
                            if error_code == "stt-stream-failed":
                                full_error_message = "Speech not recognized. Try again."
                            elif error_code == "intent-failed":
                                full_error_message = "Command not understood. Speak clearer."
                            elif error_code == "pipeline-not-found":
                                full_error_message = "Configuration error. Check settings."
                            elif error_code == "stt-no-text-recognized":
                                full_error_message = "No words detected. Try again."
                            
                            self.animation_server.change_state("error", full_error_message)
                            await asyncio.sleep(5)
                            self.animation_server.change_state("hidden")
                            utils.play_feedback_sound("deactivation")
                            
                            error_found = True
                            break
                
                if not error_found:
                    response = ha_client.extract_assistant_response(results)
                    
                    if response and response != "No response from assistant":
                        print("\n=== ASSISTANT RESPONSE ===")
                        utils.safe_print(response)
                        print("===========================\n")
                        
                        self.animation_server.change_state("responding")
                        
                        # Send response text if enabled
                        if self.response_text_enabled:
                            self.animation_server.send_response_text(response)
                        
                        audio_url = ha_client.extract_audio_url(results)
                        if audio_url:
                            print("Playing voice response with FFT analysis...")
                            success = utils.play_audio_from_url(audio_url, ha_client.host, self.animation_server)
                            if not success:
                                logger.warning("Failed to play response audio")
                        
                        await asyncio.sleep(3)
                        self.animation_server.change_state("hidden")
                        utils.play_feedback_sound("deactivation")
                    else:
                        print("\nNo response from assistant or processing error.")
                        self.animation_server.change_state("error", "Assistant did not respond")
                        await asyncio.sleep(5)
                        self.animation_server.change_state("hidden")
                        utils.play_feedback_sound("deactivation")
            else:
                logger.error("Failed to record and send audio")
                self.animation_server.change_state("error", "Audio recording error")
                await asyncio.sleep(5)
                self.animation_server.change_state("hidden")
                utils.play_feedback_sound("deactivation")
                
        except asyncio.TimeoutError:
            logger.error("Timeout during voice command processing")
            self.animation_server.change_state("error", "Timeout - assistant not responding")
            await asyncio.sleep(5)
            self.animation_server.change_state("hidden")
            utils.play_feedback_sound("deactivation")
            
        except Exception as e:
            logger.exception(f"Error during processing: {str(e)}")
            
            error_msg = str(e)
            if len(error_msg) > 80:
                error_msg = error_msg[:77] + "..."
            
            self.animation_server.change_state("error", f"Error: {error_msg}")
            await asyncio.sleep(5)
            self.animation_server.change_state("hidden")
            utils.play_feedback_sound("deactivation")
        finally:
            # Restore original volumes (prefer from HA client if available, fallback to local)
            volumes_to_restore = ha_client.saved_volumes_for_restore if ha_client.saved_volumes_for_restore else saved_volumes
            if volumes_to_restore and media_player_entities and ha_client.volumes_managed:
                try:
                    logger.info("Restoring original volumes")
                    results = await ha_client.set_multiple_volumes(volumes_to_restore)
                    logger.info(f"Restored volumes: {results}")
                    ha_client.volumes_managed = False  # Reset flag
                    ha_client.saved_volumes_for_restore = None  # Clear stored volumes
                except Exception as e:
                    logger.error(f"Error restoring volumes: {e}")
                    ha_client.volumes_managed = False  # Reset flag even on error
                    ha_client.saved_volumes_for_restore = None  # Clear stored volumes
            
            # Proper cleanup of temporary instances
            logger.info("Cleaning up voice command session...")
            
            # Only close temporary instances if we created them (not self instances)
            if audio_manager != self.audio_manager:
                try:
                    audio_manager.close_audio()
                    logger.debug("Temp audio manager closed")
                except Exception as e:
                    logger.error(f"Error closing temp audio manager: {e}")
                
            if ha_client != self.ha_client:
                try:
                    await ha_client.close()
                    logger.debug("Temp HA client closed")
                except Exception as e:
                    logger.error(f"Error closing temp HA client: {e}")
            
            logger.info("Voice command session cleanup completed")

    def on_voice_command_trigger(self):
        """Callback called when user activates voice command."""
        if self.animation_server.current_state != "hidden":
            logger.info("Application is busy, ignoring trigger")
            return
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        def run_async():
            loop.run_until_complete(self.process_voice_command())
        
        thread = threading.Thread(target=run_async, daemon=True)
        thread.start()
    
    def hide_from_taskbar(self):
        """Hide window from taskbar using cross-platform implementation."""
        try:
            success = hide_window_from_taskbar("GLaSSIST")
            if success:
                logger.info("Window successfully hidden from taskbar")
            else:
                logger.warning("Failed to hide window from taskbar")
        except Exception as e:
            logger.exception(f"Error hiding window from taskbar: {e}")

    def trigger_voice_command(self, icon=None, item=None):
        """Trigger from tray menu."""
        logger.info("Voice command activation from tray menu")
        self.on_voice_command_trigger()
    
    def setup_hotkey(self):
        """Setup keyboard shortcut."""
        try:
            import keyboard
            
            hotkey = utils.get_env("HA_HOTKEY", "ctrl+shift+h")
            keyboard.add_hotkey(hotkey, self.on_voice_command_trigger)
            logger.info(f"Keyboard shortcut set: {hotkey}")
            
            # Add escape key to hide interface quickly
            keyboard.add_hotkey("escape", self.hide_interface)
            logger.info("ESC key set to hide interface")
            
            return True
            
        except ImportError:
            logger.warning("keyboard library not installed - run: pip install keyboard")
            return False
        except Exception as e:
            logger.error(f"Error setting up keyboard shortcut: {e}")
            return False
    
    def hide_interface(self):
        """Hide interface immediately via ESC key."""
        if self.animation_server and self.animation_server.current_state != "hidden":
            logger.info("Hiding interface via ESC key")
            self.animation_server.change_state("hidden")
    
    def toggle_window(self, icon=None, item=None):
        """Toggle window visibility."""
        if self.window_visible:
            if hasattr(webview, 'windows') and webview.windows:
                webview.windows[0].minimize()
            self.window_visible = False
            logger.info("Window hidden")
        else:
            if hasattr(webview, 'windows') and webview.windows:
                webview.windows[0].restore()
            self.window_visible = True
            logger.info("Window shown")
    
    def quit_application(self, icon=None, item=None):
        """Close application from tray menu with proper cleanup."""
        logger.info("Closing application from tray menu...")
        
        # First cleanup resources
        self.cleanup()
        
        # Stop tray icon
        if self.tray_icon:
            try:
                self.tray_icon.stop()
                logger.info("Tray icon stopped")
            except Exception as e:
                logger.error(f"Error stopping tray icon: {e}")
        
        # Close webview windows
        if hasattr(webview, 'windows') and webview.windows:
            try:
                for window in webview.windows:
                    window.destroy()
                logger.info("Webview windows closed")
            except Exception as e:
                logger.error(f"Error closing webview windows: {e}")
        
        # Give some time for cleanup to complete
        import time
        time.sleep(0.5)
        
        logger.info("Application shutdown complete")
        
        # Exit cleanly
        os._exit(0)  # Force exit without calling atexit handlers
    
    def run_tray(self):
        """Run tray icon in separate thread."""
        def tray_thread():
            try:
                self.tray_icon.run()
            except Exception as e:
                logger.exception(f"Tray icon error: {e}")
        
        threading.Thread(target=tray_thread, daemon=True).start()
        logger.info("System tray started")
    
    def run(self):
        """Main run method."""
        try:
            logger.info("Starting GLaSSIST Desktop...")
            
            # Initialize HA client and audio manager at startup
            logger.info("Initializing HA client and audio manager...")
            try:
                self.ha_client = HomeAssistantClient()
                self.audio_manager = AudioManager()
                self.audio_manager.init_audio()
                logger.info("✅ HA client and audio manager initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize HA client or audio manager: {e}")
                self.ha_client = None
                self.audio_manager = None
            
            self.setup_animation_server()
            
            # Setup conversation system after HA client and audio manager are initialized
            if self.ha_client and self.audio_manager:
                if self.setup_conversation_manager():
                    # Pass app reference to conversation manager
                    self.conversation_manager._app_instance = self
                    self.setup_prompt_server()
                else:
                    logger.warning("Failed to setup conversation manager")
            else:
                logger.warning("HA client or audio manager not initialized - conversation features disabled")
            
            if not self.setup_webview():
                logger.error("Failed to configure interface")
                return
            
            self.setup_hotkey()
            self.create_tray_icon()
            self.run_tray()
            self.start_wake_word_detection()
            self._refresh_tray_menu()

            logger.info("Starting interface...")
            
            def on_window_loaded():
                import time
                time.sleep(2)
                logger.info("Attempting to hide window from taskbar...")
                
                old_level = logger.level
                logger.setLevel(10)
                
                self.hide_from_taskbar()
                logger.setLevel(old_level)
            
            threading.Thread(target=on_window_loaded, daemon=True).start()
            
            if self.animations_enabled:
                webview.start(debug=utils.get_env("DEBUG", False, bool))
            else:
                logger.info("Running in headless mode (animations disabled)")
                try:
                    import time
                    while True:
                        time.sleep(1)  # Keep main thread alive
                except KeyboardInterrupt:
                    logger.info("Application interrupted by user")
            
        except KeyboardInterrupt:
            logger.info("Application interrupted by user")
        except Exception as e:
            logger.exception(f"Application error: {str(e)}")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources properly."""
        # Prevent duplicate cleanup
        if hasattr(self, '_cleanup_done') and self._cleanup_done:
            logger.debug("Cleanup already performed, skipping")
            return
            
        logger.info("Cleaning up resources...")
        self._cleanup_done = True
        
        # Stop wake word detection first
        self.stop_wake_word_detection()
        
        # Stop prompt server
        if hasattr(self, 'prompt_server') and self.prompt_server:
            try:
                self.prompt_server.stop()
                logger.info("Prompt server stopped")
            except Exception as e:
                logger.error(f"Error stopping prompt server: {e}")
        
        # Cancel any active conversations
        if hasattr(self, 'conversation_manager') and self.conversation_manager:
            try:
                self.conversation_manager.cancel_conversation()
                logger.info("Active conversations cancelled")
            except Exception as e:
                logger.error(f"Error cancelling conversations: {e}")

        # Close HA client connection if exists
        if hasattr(self, 'ha_client') and self.ha_client:
            try:
                # Run close in asyncio loop if one exists
                loop = None
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    # No running loop, create a new one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                if loop and not loop.is_closed():
                    if loop.is_running():
                        # Schedule close for later
                        asyncio.create_task(self.ha_client.close())
                    else:
                        # Run close synchronously
                        loop.run_until_complete(self.ha_client.close())
                        
                self.ha_client = None
                logger.info("HA Client connection closed")
                
            except Exception as e:
                logger.error(f"Error closing HA client: {e}")

        # Stop animation server
        if self.animation_server:
            try:
                self.animation_server.stop()
                logger.info("Animation server stopped")
            except Exception as e:
                logger.error(f"Error stopping animation server: {e}")
        
        # Close audio manager
        if self.audio_manager:
            try:
                self.audio_manager.close_audio()
                logger.info("Audio manager closed")
            except Exception as e:
                logger.error(f"Error closing audio manager: {e}")
                
        # Cancel any remaining asyncio tasks
        try:
            # Check if there's a running event loop
            try:
                loop = asyncio.get_running_loop()
                loop_exists = True
            except RuntimeError:
                # No running loop, try to get the current one
                try:
                    loop = asyncio.get_event_loop()
                    loop_exists = not loop.is_closed()
                except RuntimeError:
                    loop_exists = False
                    loop = None
            
            if loop_exists and loop:
                pending = asyncio.all_tasks(loop)
                if pending:
                    logger.info(f"Cancelling {len(pending)} pending tasks...")
                    for task in pending:
                        if not task.done():
                            task.cancel()
                    
                    # Give tasks a moment to cancel gracefully
                    if not loop.is_running():
                        try:
                            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                        except Exception as e:
                            logger.error(f"Error waiting for task cancellation: {e}")
            else:
                logger.debug("No active event loop found - skipping task cancellation")
                            
        except Exception as e:
            logger.error(f"Error cancelling asyncio tasks: {e}")
            
        logger.info("Cleanup completed")


def validate_configuration():
    """Validate application configuration and return list of issues."""
    issues = []
    
    host = utils.get_env("HA_HOST")
    token = utils.get_env("HA_TOKEN")
    
    if not host:
        issues.append("Missing Home Assistant server address (HA_HOST)")
    
    if not token:
        issues.append("Missing access token (HA_TOKEN)")
    
    sample_rate = utils.get_env("HA_SAMPLE_RATE", 16000, int)
    if sample_rate not in [8000, 16000, 22050, 44100, 48000]:
        issues.append(f"Unusual sample rate: {sample_rate}Hz")
    
    frame_duration = utils.get_env("HA_FRAME_DURATION_MS", 30, int)
    if frame_duration not in [10, 20, 30]:
        issues.append(f"Invalid VAD frame duration: {frame_duration}ms (allowed: 10, 20, 30)")
    
    vad_mode = utils.get_env("HA_VAD_MODE", 3, int)
    if vad_mode < 0 or vad_mode > 3:
        issues.append(f"Invalid VAD mode: {vad_mode} (allowed: 0-3)")

    sound_feedback = utils.get_env('HA_SOUND_FEEDBACK', 'true')
    if sound_feedback.lower() in ('true', '1', 'yes', 'y', 't'):
        sound_dir = os.path.join(os.path.dirname(__file__), 'sound')
        activation_sound = os.path.join(sound_dir, 'activation.wav')
        deactivation_sound = os.path.join(sound_dir, 'deactivation.wav')
        
        if not os.path.exists(activation_sound):
            issues.append(f"Missing activation sound file: {activation_sound}")
        
        if not os.path.exists(deactivation_sound):
            issues.append(f"Missing deactivation sound file: {deactivation_sound}")

    try:
        anim_port = utils.get_env("ANIMATION_PORT", 8765, int)
        if anim_port < 1024 or anim_port > 65535:
            issues.append(f"Invalid animation port: {anim_port} (allowed: 1024-65535)")
    except (ValueError, TypeError):
        issues.append("Animation port must be a number")
    wake_word_issues = validate_wake_word_config()
    issues.extend(wake_word_issues)
    return issues


def main():
    """Main application function with configuration validation."""
    # Set UTF-8 encoding for console output on Windows
    import sys
    if sys.platform == "win32":
        try:
            import locale
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except:
            # Fallback for older Python versions
            import os
            os.environ["PYTHONIOENCODING"] = "utf-8"
    
    print("=== GLaSSIST DESKTOP ===")
    print("Starting application...")
    print("Pre-initializing audio system...")
    try:
        import pyaudio
        temp_audio = pyaudio.PyAudio()
        temp_audio.terminate()
        print("Audio system ready")
    except Exception as e:
        print(f"Audio initialization warning: {e}")
    possible_paths = [
        os.path.join(os.path.dirname(__file__), '.env'),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),
        '.env'
    ]
    
    env_found = False
    for path in possible_paths:
        if os.path.exists(path):
            abs_path = os.path.abspath(path)
            print(f"USING .ENV FILE: {abs_path}")
            env_found = True
            
            with open(abs_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            filtered_lines = []
            for line in lines:
                if line.startswith('HA_TOKEN=') and len(line) > 20:
                    filtered_lines.append(f"HA_TOKEN=***HIDDEN*** (length: {len(line.split('=', 1)[1])} chars)")
                else:
                    filtered_lines.append(line)
            
            print(".ENV FILE CONTENTS:")
            print('\n'.join(filtered_lines))
            print("-" * 50)
            break
    
    if not env_found:
        print("NO .ENV FILE - using default settings")
        print("Run application and go to 'Settings' to configure connection.")
        print("-" * 50)
    
    print("CHECKING CONFIGURATION...")
    config_issues = validate_configuration()
    
    if config_issues:
        print("  CONFIGURATION ISSUES FOUND:")
        for issue in config_issues:
            print(f"   • {issue}")
        print("\nApplication may not work correctly.")
        print("Go to 'Settings' to fix issues.")
    else:
        print(" Configuration looks correct")
    
    print("-" * 50)
    
    print(" KEY SETTINGS:")
    important_settings = {
        'HA_HOST': utils.get_env('HA_HOST', 'MISSING'),
        'HA_PIPELINE_ID': utils.get_env('HA_PIPELINE_ID', '(default)'),
        'HA_HOTKEY': utils.get_env('HA_HOTKEY', 'ctrl+shift+h'),
        'HA_VAD_MODE': utils.get_env('HA_VAD_MODE', '3'),
        'HA_SOUND_FEEDBACK': utils.get_env('HA_SOUND_FEEDBACK', 'true'),
        'HA_WAKE_WORD_ENABLED': utils.get_env('HA_WAKE_WORD_ENABLED', 'false'),
        'DEBUG': utils.get_env('DEBUG', 'false')
    }
    
    for key, value in important_settings.items():
        print(f"   {key} = {value}")

    wake_word_enabled_str = utils.get_env('HA_WAKE_WORD_ENABLED', 'false')
    if isinstance(wake_word_enabled_str, str):
        wake_word_enabled = wake_word_enabled_str.lower() in ('true', '1', 'yes', 'y', 't')
    else:
        wake_word_enabled = bool(wake_word_enabled_str)

    if wake_word_enabled:
        models = utils.get_env('HA_WAKE_WORD_MODELS', 'alexa')
        print(f"   HA_WAKE_WORD_MODELS = {models}")
        print(f"   HA_WAKE_WORD_THRESHOLD = {utils.get_env('HA_WAKE_WORD_THRESHOLD', '0.5')}")
        
    token_length = len(utils.get_env('HA_TOKEN', ''))
    if token_length > 0:
        print(f"   HA_TOKEN = ***HIDDEN*** ({token_length} chars)")
    else:
        print(f"   HA_TOKEN = MISSING")
    
    print("=" * 50)
    
    app = HAAssistApp()
    app.run()


if __name__ == "__main__":
    main()