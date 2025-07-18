"""
Tests for main module (HAAssistApp).
"""
import pytest
import os
import threading
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import main


class TestHAAssistApp:
    """Test cases for HAAssistApp class."""
    
    @patch('main.check_linux_dependencies')
    @patch('main.platform.system')
    def test_init_windows(self, mock_system, mock_check_deps):
        """Test app initialization on Windows."""
        mock_system.return_value = "Windows"
        
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token',
            'HA_ANIMATIONS_ENABLED': 'true'
        }):
            with patch('main.WakeWordDetector') as mock_detector:
                app = main.HAAssistApp()
                
                assert app.is_windows is True
                assert app.is_linux is False
                assert app.animations_enabled is True
                mock_check_deps.assert_not_called()
    
    @patch('main.check_linux_dependencies')
    @patch('main.platform.system')
    def test_init_linux_dependencies_ok(self, mock_system, mock_check_deps):
        """Test app initialization on Linux with dependencies."""
        mock_system.return_value = "Linux"
        mock_check_deps.return_value = True
        
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token',
            'HA_ANIMATIONS_ENABLED': 'false'
        }):
            with patch('main.WakeWordDetector') as mock_detector:
                app = main.HAAssistApp()
                
                assert app.is_windows is False
                assert app.is_linux is True
                assert app.animations_enabled is False
                mock_check_deps.assert_called_once()
    
    @patch('main.check_linux_dependencies')
    @patch('main.platform.system')
    @patch('sys.exit')
    def test_init_linux_dependencies_missing(self, mock_exit, mock_system, mock_check_deps):
        """Test app initialization on Linux with missing dependencies."""
        mock_system.return_value = "Linux"
        mock_check_deps.return_value = False
        
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.WakeWordDetector') as mock_detector:
                main.HAAssistApp()
                
                mock_exit.assert_called_once_with(1)
    
    @patch('main.WakeWordDetector')
    def test_setup_wake_word_detector_success(self, mock_detector_class):
        """Test successful wake word detector setup."""
        mock_detector = Mock()
        mock_detector.enabled = True
        mock_detector_class.return_value = mock_detector
        
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.platform.system', return_value="Windows"):
                app = main.HAAssistApp()
                
                assert app.wake_word_detector == mock_detector
                mock_detector_class.assert_called_once_with(
                    callback=app.on_wake_word_detected
                )
    
    @patch('main.WakeWordDetector')
    def test_setup_wake_word_detector_failure(self, mock_detector_class):
        """Test wake word detector setup failure."""
        mock_detector_class.side_effect = Exception("Detector error")
        
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.platform.system', return_value="Windows"):
                app = main.HAAssistApp()
                
                assert app.wake_word_detector is None
    
    def test_on_wake_word_detected_idle(self):
        """Test wake word detection when app is idle."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'):
                
                app = main.HAAssistApp()
                app.animation_server = Mock()
                app.animation_server.current_state = "hidden"
                
                with patch.object(app, 'on_voice_command_trigger') as mock_trigger:
                    app.on_wake_word_detected("alexa", 0.7)
                    
                    mock_trigger.assert_called_once()
    
    def test_on_wake_word_detected_busy(self):
        """Test wake word detection when app is busy."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'):
                
                app = main.HAAssistApp()
                app.animation_server = Mock()
                app.animation_server.current_state = "listening"
                
                with patch.object(app, 'on_voice_command_trigger') as mock_trigger:
                    app.on_wake_word_detected("alexa", 0.7)
                    
                    mock_trigger.assert_not_called()
    
    @patch('main.platform.system')
    def test_create_tray_icon_linux(self, mock_system):
        """Test tray icon creation on Linux (disabled)."""
        mock_system.return_value = "Linux"
        
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.WakeWordDetector'):
                app = main.HAAssistApp()
                
                app.create_tray_icon()
                
                # Should not create tray icon on Linux
                assert app.tray_icon is None
    
    @patch('main.platform.system')
    @patch('main.get_icon_path')
    @patch('main.pystray.Icon')
    def test_create_tray_icon_windows_success(self, mock_icon, mock_get_icon, mock_system):
        """Test successful tray icon creation on Windows."""
        mock_system.return_value = "Windows"
        mock_get_icon.return_value = "/path/to/icon.ico"
        
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.WakeWordDetector'), \
                 patch('os.path.exists', return_value=True), \
                 patch('PIL.Image.open') as mock_image:
                
                app = main.HAAssistApp()
                app.create_tray_icon()
                
                mock_icon.assert_called_once()
                assert app.tray_icon is not None
    
    @patch('main.platform.system')
    @patch('main.get_icon_path')
    @patch('main.pystray.Icon')
    def test_create_tray_icon_fallback(self, mock_icon, mock_get_icon, mock_system):
        """Test tray icon creation with fallback icon."""
        mock_system.return_value = "Windows"
        mock_get_icon.return_value = "/nonexistent/icon.ico"
        
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.WakeWordDetector'), \
                 patch('os.path.exists', return_value=False), \
                 patch.object(main.HAAssistApp, '_create_fallback_icon') as mock_fallback:
                
                app = main.HAAssistApp()
                app.create_tray_icon()
                
                mock_fallback.assert_called_once()
                mock_icon.assert_called_once()
    
    def test_show_wake_word_status_enabled_running(self):
        """Test wake word status display when enabled and running."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'):
                
                app = main.HAAssistApp()
                app.animation_server = Mock()
                app.wake_word_detector = Mock()
                
                # Mock detector info
                app.wake_word_detector.get_model_info.return_value = {
                    'enabled': True,
                    'is_running': True,
                    'selected_models': ['alexa', 'jarvis'],
                    'detection_threshold': 0.5,
                    'vad_threshold': 0.3,
                    'noise_suppression': False,
                    'available_models': ['alexa', 'jarvis', 'hal']
                }
                
                with patch('builtins.print') as mock_print:
                    app._show_wake_word_status()
                    
                    # Should show success animation
                    app.animation_server.show_success.assert_called_once()
                    # Should print status
                    assert mock_print.call_count > 5
    
    def test_show_wake_word_status_disabled(self):
        """Test wake word status display when disabled."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'):
                
                app = main.HAAssistApp()
                app.animation_server = Mock()
                app.wake_word_detector = Mock()
                
                # Mock detector info
                app.wake_word_detector.get_model_info.return_value = {
                    'enabled': False,
                    'is_running': False,
                    'selected_models': [],
                    'detection_threshold': 0.5,
                    'vad_threshold': 0.3,
                    'noise_suppression': False,
                    'available_models': []
                }
                
                app._show_wake_word_status()
                
                # Should show error animation
                app.animation_server.show_error.assert_called_once()
    
    def test_toggle_wake_word_detection_pause(self):
        """Test pausing wake word detection."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'):
                
                app = main.HAAssistApp()
                app.animation_server = Mock()
                app.wake_word_detector = Mock()
                app.wake_word_detector.enabled = True
                app.wake_word_detector.is_running = True
                
                with patch.object(app, 'stop_wake_word_detection') as mock_stop, \
                     patch.object(app, '_refresh_tray_menu') as mock_refresh:
                    
                    app._toggle_wake_word_detection()
                    
                    mock_stop.assert_called_once()
                    mock_refresh.assert_called_once()
                    app.animation_server.show_error.assert_called_once()
    
    def test_toggle_wake_word_detection_resume(self):
        """Test resuming wake word detection."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'):
                
                app = main.HAAssistApp()
                app.animation_server = Mock()
                app.wake_word_detector = Mock()
                app.wake_word_detector.enabled = True
                app.wake_word_detector.is_running = False
                
                with patch.object(app, 'start_wake_word_detection', return_value=True) as mock_start, \
                     patch.object(app, '_refresh_tray_menu') as mock_refresh:
                    
                    app._toggle_wake_word_detection()
                    
                    mock_start.assert_called_once()
                    mock_refresh.assert_called_once()
                    app.animation_server.show_success.assert_called_once()
    
    def test_toggle_wake_word_detection_disabled(self):
        """Test toggle when wake word detection is disabled."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'):
                
                app = main.HAAssistApp()
                app.animation_server = Mock()
                app.wake_word_detector = Mock()
                app.wake_word_detector.enabled = False
                
                app._toggle_wake_word_detection()
                
                # Should show error about disabled detection
                app.animation_server.show_error.assert_called_once()
    
    def test_restart_wake_word_success(self):
        """Test successful wake word restart."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'):
                
                app = main.HAAssistApp()
                app.animation_server = Mock()
                app.wake_word_detector = Mock()
                app.wake_word_detector.reload_models.return_value = True
                
                with patch.object(app, 'stop_wake_word_detection') as mock_stop, \
                     patch.object(app, '_refresh_tray_menu') as mock_refresh:
                    
                    app._restart_wake_word()
                    
                    mock_stop.assert_called_once()
                    app.wake_word_detector.reload_models.assert_called_once()
                    mock_refresh.assert_called_once()
                    app.animation_server.show_success.assert_called_once()
    
    def test_restart_wake_word_failure(self):
        """Test failed wake word restart."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'):
                
                app = main.HAAssistApp()
                app.animation_server = Mock()
                app.wake_word_detector = Mock()
                app.wake_word_detector.reload_models.return_value = False
                
                with patch.object(app, 'stop_wake_word_detection') as mock_stop, \
                     patch.object(app, '_refresh_tray_menu') as mock_refresh:
                    
                    app._restart_wake_word()
                    
                    mock_stop.assert_called_once()
                    app.wake_word_detector.reload_models.assert_called_once()
                    mock_refresh.assert_called_once()
                    app.animation_server.show_error.assert_called_once()
    
    def test_setup_animation_server_enabled(self):
        """Test animation server setup when enabled."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token',
            'HA_ANIMATIONS_ENABLED': 'true'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'), \
                 patch('main.AnimationServer') as mock_server:
                
                mock_server_instance = Mock()
                mock_server.return_value = mock_server_instance
                
                app = main.HAAssistApp()
                app.setup_animation_server()
                
                mock_server.assert_called_once()
                mock_server_instance.set_voice_command_callback.assert_called_once()
                mock_server_instance.start.assert_called_once()
                assert app.animation_server == mock_server_instance
    
    def test_setup_animation_server_disabled(self):
        """Test animation server setup when disabled."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token',
            'HA_ANIMATIONS_ENABLED': 'false'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'), \
                 patch('main.DummyAnimationServer') as mock_dummy:
                
                mock_dummy_instance = Mock()
                mock_dummy.return_value = mock_dummy_instance
                
                app = main.HAAssistApp()
                app.setup_animation_server()
                
                mock_dummy.assert_called_once()
                mock_dummy_instance.set_voice_command_callback.assert_called_once()
                mock_dummy_instance.start.assert_called_once()
                assert app.animation_server == mock_dummy_instance
    
    @patch('main.webview.create_window')
    def test_setup_webview_success(self, mock_create_window):
        """Test successful webview setup."""
        mock_window = Mock()
        mock_create_window.return_value = mock_window
        
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'), \
                 patch('os.path.exists', return_value=True):
                
                app = main.HAAssistApp()
                result = app.setup_webview()
                
                assert result is True
                assert app.window == mock_window
                mock_create_window.assert_called_once()
    
    @patch('main.webview.create_window')
    def test_setup_webview_missing_frontend(self, mock_create_window):
        """Test webview setup with missing frontend file."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'), \
                 patch('os.path.exists', return_value=False):
                
                app = main.HAAssistApp()
                result = app.setup_webview()
                
                assert result is False
                mock_create_window.assert_not_called()
    
    @patch('main.keyboard.add_hotkey')
    def test_setup_hotkey_success(self, mock_add_hotkey):
        """Test successful hotkey setup."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token',
            'HA_HOTKEY': 'ctrl+alt+v'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'):
                
                app = main.HAAssistApp()
                result = app.setup_hotkey()
                
                assert result is True
                mock_add_hotkey.assert_called_once_with(
                    'ctrl+alt+v',
                    app.on_voice_command_trigger
                )
    
    @patch('main.keyboard.add_hotkey')
    def test_setup_hotkey_import_error(self, mock_add_hotkey):
        """Test hotkey setup with import error."""
        mock_add_hotkey.side_effect = ImportError("keyboard not installed")
        
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'):
                
                app = main.HAAssistApp()
                result = app.setup_hotkey()
                
                assert result is False
    
    @patch('main.keyboard.add_hotkey')
    def test_setup_hotkey_exception(self, mock_add_hotkey):
        """Test hotkey setup with exception."""
        mock_add_hotkey.side_effect = Exception("Hotkey error")
        
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'):
                
                app = main.HAAssistApp()
                result = app.setup_hotkey()
                
                assert result is False
    
    @patch('main.threading.Thread')
    def test_on_voice_command_trigger_idle(self, mock_thread):
        """Test voice command trigger when idle."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'):
                
                app = main.HAAssistApp()
                app.animation_server = Mock()
                app.animation_server.current_state = "hidden"
                
                mock_thread_instance = Mock()
                mock_thread.return_value = mock_thread_instance
                
                app.on_voice_command_trigger()
                
                mock_thread.assert_called_once()
                mock_thread_instance.start.assert_called_once()
    
    def test_on_voice_command_trigger_busy(self):
        """Test voice command trigger when busy."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'):
                
                app = main.HAAssistApp()
                app.animation_server = Mock()
                app.animation_server.current_state = "listening"
                
                with patch('main.threading.Thread') as mock_thread:
                    app.on_voice_command_trigger()
                    
                    mock_thread.assert_not_called()
    
    def test_cleanup_success(self):
        """Test successful cleanup."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'):
                
                app = main.HAAssistApp()
                app.animation_server = Mock()
                app.audio_manager = Mock()
                
                with patch.object(app, 'stop_wake_word_detection') as mock_stop:
                    app.cleanup()
                    
                    mock_stop.assert_called_once()
                    app.animation_server.stop.assert_called_once()
                    app.audio_manager.close_audio.assert_called_once()
    
    def test_cleanup_duplicate_call(self):
        """Test cleanup with duplicate call."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('main.platform.system', return_value="Windows"), \
                 patch('main.WakeWordDetector'):
                
                app = main.HAAssistApp()
                app.animation_server = Mock()
                
                with patch.object(app, 'stop_wake_word_detection') as mock_stop:
                    # First cleanup
                    app.cleanup()
                    
                    # Second cleanup should be skipped
                    app.cleanup()
                    
                    mock_stop.assert_called_once()
                    app.animation_server.stop.assert_called_once()


class TestValidateConfiguration:
    """Test cases for configuration validation."""
    
    def test_validate_configuration_valid(self):
        """Test configuration validation with valid config."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'valid_token',
            'HA_SAMPLE_RATE': '16000',
            'HA_FRAME_DURATION_MS': '30',
            'HA_VAD_MODE': '3',
            'HA_SOUND_FEEDBACK': 'true'
        }):
            with patch('os.path.exists', return_value=True), \
                 patch('main.validate_wake_word_config', return_value=[]):
                
                issues = main.validate_configuration()
                
                assert len(issues) == 0
    
    def test_validate_configuration_missing_required(self):
        """Test configuration validation with missing required fields."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('main.validate_wake_word_config', return_value=[]):
                issues = main.validate_configuration()
                
                assert len(issues) >= 2  # Missing HOST and TOKEN
                assert any("HA_HOST" in issue for issue in issues)
                assert any("HA_TOKEN" in issue for issue in issues)
    
    def test_validate_configuration_invalid_values(self):
        """Test configuration validation with invalid values."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token',
            'HA_SAMPLE_RATE': '12000',  # Invalid sample rate
            'HA_FRAME_DURATION_MS': '25',  # Invalid frame duration
            'HA_VAD_MODE': '5',  # Invalid VAD mode
            'ANIMATION_PORT': '99999'  # Invalid port
        }):
            with patch('main.validate_wake_word_config', return_value=[]):
                issues = main.validate_configuration()
                
                assert len(issues) >= 3
                assert any("sample rate" in issue for issue in issues)
                assert any("frame duration" in issue for issue in issues)
                assert any("VAD mode" in issue for issue in issues)
    
    def test_validate_configuration_missing_sound_files(self):
        """Test configuration validation with missing sound files."""
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token',
            'HA_SOUND_FEEDBACK': 'true'
        }):
            with patch('os.path.exists', return_value=False), \
                 patch('main.validate_wake_word_config', return_value=[]):
                
                issues = main.validate_configuration()
                
                assert len(issues) >= 2  # Missing sound files
                assert any("activation.wav" in issue for issue in issues)
                assert any("deactivation.wav" in issue for issue in issues)


class TestMain:
    """Test cases for main function."""
    
    @patch('main.HAAssistApp')
    @patch('main.validate_configuration')
    @patch('builtins.print')
    def test_main_success(self, mock_print, mock_validate, mock_app):
        """Test successful main function execution."""
        mock_validate.return_value = []
        mock_app_instance = Mock()
        mock_app.return_value = mock_app_instance
        
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('os.path.exists', return_value=True), \
                 patch('builtins.open', mock_open(read_data='HA_HOST=localhost:8123\nHA_TOKEN=test_token')), \
                 patch('pyaudio.PyAudio') as mock_pyaudio:
                
                mock_audio = Mock()
                mock_pyaudio.return_value = mock_audio
                
                main.main()
                
                mock_app.assert_called_once()
                mock_app_instance.run.assert_called_once()
    
    @patch('main.HAAssistApp')
    @patch('main.validate_configuration')
    @patch('builtins.print')
    def test_main_with_config_issues(self, mock_print, mock_validate, mock_app):
        """Test main function with configuration issues."""
        mock_validate.return_value = ["Missing HA_HOST", "Invalid VAD mode"]
        mock_app_instance = Mock()
        mock_app.return_value = mock_app_instance
        
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('os.path.exists', return_value=False), \
                 patch('pyaudio.PyAudio') as mock_pyaudio:
                
                mock_audio = Mock()
                mock_pyaudio.return_value = mock_audio
                
                main.main()
                
                # Should still run but print warnings
                mock_app.assert_called_once()
                mock_app_instance.run.assert_called_once()
                
                # Should print configuration issues
                printed_text = ' '.join(str(call) for call in mock_print.call_args_list)
                assert "CONFIGURATION ISSUES FOUND" in printed_text
    
    @patch('main.HAAssistApp')
    @patch('builtins.print')
    def test_main_audio_init_warning(self, mock_print, mock_app):
        """Test main function with audio initialization warning."""
        mock_app_instance = Mock()
        mock_app.return_value = mock_app_instance
        
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token'
        }):
            with patch('os.path.exists', return_value=False), \
                 patch('pyaudio.PyAudio') as mock_pyaudio:
                
                mock_pyaudio.side_effect = Exception("Audio error")
                
                main.main()
                
                # Should still run but print audio warning
                mock_app.assert_called_once()
                mock_app_instance.run.assert_called_once()
                
                # Should print audio warning
                printed_text = ' '.join(str(call) for call in mock_print.call_args_list)
                assert "Audio initialization warning" in printed_text
    
    @patch('main.HAAssistApp')
    @patch('builtins.print')  
    def test_main_env_file_handling(self, mock_print, mock_app):
        """Test main function environment file handling."""
        mock_app_instance = Mock()
        mock_app.return_value = mock_app_instance
        
        env_content = """HA_HOST=localhost:8123
HA_TOKEN=very_long_secret_token_that_should_be_hidden
HA_SAMPLE_RATE=16000
DEBUG=true"""
        
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=env_content)), \
             patch('pyaudio.PyAudio') as mock_pyaudio:
            
            mock_audio = Mock()
            mock_pyaudio.return_value = mock_audio
            
            main.main()
            
            # Should hide token in output
            printed_text = ' '.join(str(call) for call in mock_print.call_args_list)
            assert "***HIDDEN***" in printed_text
            assert "very_long_secret_token" not in printed_text