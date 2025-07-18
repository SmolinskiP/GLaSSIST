"""
Integration tests for GLaSSIST Desktop Voice Assistant.
"""
import pytest
import asyncio
import tempfile
import os
import threading
import time
from unittest.mock import Mock, patch, AsyncMock, MagicMock


class TestVoiceCommandIntegration:
    """Integration tests for voice command processing."""
    
    @pytest.mark.asyncio
    async def test_complete_voice_command_flow(self):
        """Test complete voice command flow from audio to response."""
        # Import main components
        from main import HAAssistApp
        from client import HomeAssistantClient
        from audio import AudioManager
        from animation_server import AnimationServer
        
        # Mock external dependencies
        with patch('pyaudio.PyAudio') as mock_pyaudio, \
             patch('websockets.connect') as mock_ws_connect, \
             patch('webview.create_window') as mock_webview, \
             patch('pystray.Icon') as mock_tray:
            
            # Setup mocks
            mock_audio = Mock()
            mock_pyaudio.return_value = mock_audio
            mock_audio.get_device_count.return_value = 1
            mock_audio.get_device_info_by_index.return_value = {
                'name': 'Test Microphone',
                'maxInputChannels': 1,
                'defaultSampleRate': 16000
            }
            mock_audio.open.return_value = Mock()
            
            mock_ws = AsyncMock()
            mock_ws_connect.return_value = mock_ws
            mock_ws.recv.side_effect = [
                '{"type": "auth_required"}',
                '{"type": "auth_ok"}',
                '{"type": "result", "success": true, "result": {"pipelines": []}}',
                '{"type": "result", "success": true, "result": {}}',
                '{"type": "event", "event": {"type": "stt-end", "data": {"stt_output": {"text": "turn on lights"}}}}',
                '{"type": "event", "event": {"type": "intent-end", "data": {"intent_output": {"response": {"speech": {"plain": {"speech": "Lights turned on"}}}}}}}'
            ]
            
            # Create app instance
            with patch.dict('os.environ', {
                'HA_HOST': 'localhost:8123',
                'HA_TOKEN': 'test_token',
                'HA_ANIMATIONS_ENABLED': 'false',
                'HA_WAKE_WORD_ENABLED': 'false'
            }):
                app = HAAssistApp()
                
                # Mock audio recording
                with patch.object(app, 'animation_server') as mock_anim_server:
                    mock_anim_server.current_state = "hidden"
                    
                    # Test voice command processing
                    await app.process_voice_command()
                    
                    # Verify state changes
                    assert mock_anim_server.change_state.call_count >= 2
                    state_calls = [call[0][0] for call in mock_anim_server.change_state.call_args_list]
                    assert "listening" in state_calls
                    assert "processing" in state_calls
    
    @pytest.mark.asyncio
    async def test_wake_word_to_voice_command(self):
        """Test wake word detection triggering voice command."""
        from main import HAAssistApp
        from wake_word_detector import WakeWordDetector
        
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token',
            'HA_ANIMATIONS_ENABLED': 'false',
            'HA_WAKE_WORD_ENABLED': 'true',
            'HA_WAKE_WORD_MODELS': 'alexa'
        }):
            with patch('openwakeword.model.Model') as mock_model, \
                 patch('pyaudio.PyAudio') as mock_pyaudio, \
                 patch('webview.create_window'), \
                 patch('pystray.Icon'):
                
                # Setup mocks
                mock_model_instance = Mock()
                mock_model.return_value = mock_model_instance
                mock_model_instance.predict.return_value = {'alexa': 0.7}
                
                mock_audio = Mock()
                mock_pyaudio.return_value = mock_audio
                mock_audio.get_device_count.return_value = 1
                mock_audio.get_device_info_by_index.return_value = {
                    'name': 'Test Microphone',
                    'maxInputChannels': 1,
                    'defaultSampleRate': 16000
                }
                mock_audio.open.return_value = Mock()
                
                app = HAAssistApp()
                
                # Mock voice command processing
                with patch.object(app, 'on_voice_command_trigger') as mock_trigger:
                    # Simulate wake word detection
                    app.on_wake_word_detected('alexa', 0.7)
                    
                    # Should trigger voice command
                    mock_trigger.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_animation_server_client_communication(self):
        """Test animation server and client communication."""
        from animation_server import AnimationServer
        import websockets
        import json
        
        # Create server
        server = AnimationServer(port=8766)
        
        # Start server in background
        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        
        # Wait for server to start
        await asyncio.sleep(0.5)
        
        try:
            # Connect client
            uri = "ws://localhost:8766"
            async with websockets.connect(uri) as websocket:
                # Should receive initial state
                message = await websocket.recv()
                data = json.loads(message)
                assert data["type"] == "state_change"
                assert data["state"] == "hidden"
                
                # Send ping
                await websocket.send(json.dumps({"type": "ping"}))
                
                # Should receive pong
                message = await websocket.recv()
                data = json.loads(message)
                assert data["type"] == "pong"
                
                # Test state change broadcast
                server.change_state("listening")
                
                # Should receive state change
                message = await websocket.recv()
                data = json.loads(message)
                assert data["type"] == "state_change"
                assert data["state"] == "listening"
                
        finally:
            server.stop()
    
    def test_audio_manager_vad_integration(self):
        """Test AudioManager integration with VAD."""
        from audio import AudioManager
        from vad import VoiceActivityDetector
        
        with patch('pyaudio.PyAudio') as mock_pyaudio:
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
            
            # Create audio manager
            audio_manager = AudioManager()
            
            # Mock VAD
            with patch.object(audio_manager, 'vad') as mock_vad:
                mock_vad.is_speech.return_value = True
                
                # Initialize audio
                success = audio_manager.init_audio()
                assert success is True
                
                # Verify VAD integration
                assert audio_manager.vad == mock_vad
                
                # Test cleanup
                audio_manager.close_audio()
    
    def test_client_pipeline_integration(self):
        """Test Home Assistant client pipeline integration."""
        from client import HomeAssistantClient
        
        with patch.dict('os.environ', {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'test_token',
            'HA_PIPELINE_ID': 'test_pipeline'
        }):
            client = HomeAssistantClient()
            
            # Mock pipelines
            client.available_pipelines = [
                {"id": "test_pipeline", "name": "Test Pipeline"},
                {"id": "other_pipeline", "name": "Other Pipeline"}
            ]
            
            # Test pipeline validation
            assert client.validate_pipeline_id("test_pipeline") is True
            assert client.validate_pipeline_id("nonexistent") is False
            
            # Test pipeline retrieval
            pipelines = client.get_available_pipelines()
            assert len(pipelines) == 2
            assert pipelines[0]["name"] == "Test Pipeline"


class TestConfigurationIntegration:
    """Integration tests for configuration handling."""
    
    def test_environment_variable_loading(self):
        """Test environment variable loading across modules."""
        import utils
        
        test_env = {
            'HA_HOST': 'test.local:8123',
            'HA_TOKEN': 'test_token_123',
            'HA_SAMPLE_RATE': '44100',
            'HA_CHANNELS': '2',
            'HA_VAD_MODE': '2',
            'HA_WAKE_WORD_ENABLED': 'true',
            'HA_ANIMATIONS_ENABLED': 'false',
            'DEBUG': 'true'
        }
        
        with patch.dict('os.environ', test_env):
            # Test string values
            assert utils.get_env('HA_HOST') == 'test.local:8123'
            assert utils.get_env('HA_TOKEN') == 'test_token_123'
            
            # Test integer conversion
            assert utils.get_env('HA_SAMPLE_RATE', 16000, int) == 44100
            assert utils.get_env('HA_CHANNELS', 1, int) == 2
            assert utils.get_env('HA_VAD_MODE', 3, int) == 2
            
            # Test boolean conversion
            assert utils.get_env_bool('HA_WAKE_WORD_ENABLED', False) is True
            assert utils.get_env_bool('HA_ANIMATIONS_ENABLED', True) is False
            assert utils.get_env_bool('DEBUG', False) is True
    
    def test_configuration_validation_integration(self):
        """Test configuration validation across modules."""
        from main import validate_configuration
        from wake_word_detector import validate_wake_word_config
        
        # Test valid configuration
        valid_env = {
            'HA_HOST': 'localhost:8123',
            'HA_TOKEN': 'valid_token',
            'HA_SAMPLE_RATE': '16000',
            'HA_VAD_MODE': '3',
            'HA_FRAME_DURATION_MS': '30',
            'HA_WAKE_WORD_ENABLED': 'false',
            'HA_SOUND_FEEDBACK': 'true'
        }
        
        with patch.dict('os.environ', valid_env):
            with patch('os.path.exists', return_value=True):
                issues = validate_configuration()
                wake_word_issues = validate_wake_word_config()
                
                # Should have minimal issues with valid config
                assert len(issues) <= 2  # May have some warnings
                assert len(wake_word_issues) == 0
        
        # Test invalid configuration
        invalid_env = {
            'HA_HOST': '',  # Missing host
            'HA_TOKEN': '',  # Missing token
            'HA_SAMPLE_RATE': '12000',  # Invalid sample rate
            'HA_VAD_MODE': '5',  # Invalid VAD mode
            'HA_FRAME_DURATION_MS': '25',  # Invalid frame duration
            'HA_WAKE_WORD_ENABLED': 'true',
            'HA_WAKE_WORD_THRESHOLD': '1.5'  # Invalid threshold
        }
        
        with patch.dict('os.environ', invalid_env):
            with patch('os.path.exists', return_value=False):
                issues = validate_configuration()
                wake_word_issues = validate_wake_word_config()
                
                # Should have multiple issues
                assert len(issues) > 3
                assert len(wake_word_issues) > 0
    
    def test_cross_module_configuration_consistency(self):
        """Test configuration consistency across modules."""
        from audio import AudioManager
        from wake_word_detector import WakeWordDetector
        from client import HomeAssistantClient
        
        test_env = {
            'HA_HOST': 'test.local:8123',
            'HA_TOKEN': 'test_token',
            'HA_SAMPLE_RATE': '44100',
            'HA_WAKE_WORD_ENABLED': 'true',
            'HA_WAKE_WORD_MODELS': 'alexa,jarvis'
        }
        
        with patch.dict('os.environ', test_env):
            with patch('openwakeword.model.Model'), \
                 patch('pyaudio.PyAudio'):
                
                # Create instances
                audio_manager = AudioManager()
                wake_word_detector = WakeWordDetector()
                ha_client = HomeAssistantClient()
                
                # Verify consistent configuration
                assert audio_manager.sample_rate == 44100
                assert wake_word_detector.sample_rate == 16000  # Fixed for OpenWakeWord
                assert ha_client.sample_rate == 44100
                assert ha_client.host == 'test.local:8123'
                assert ha_client.token == 'test_token'
                assert wake_word_detector.enabled is True
                assert wake_word_detector.selected_models == ['alexa', 'jarvis']


class TestErrorHandlingIntegration:
    """Integration tests for error handling across modules."""
    
    @pytest.mark.asyncio
    async def test_connection_error_handling(self):
        """Test connection error handling throughout the system."""
        from main import HAAssistApp
        
        with patch.dict('os.environ', {
            'HA_HOST': 'nonexistent:8123',
            'HA_TOKEN': 'invalid_token',
            'HA_ANIMATIONS_ENABLED': 'false',
            'HA_WAKE_WORD_ENABLED': 'false'
        }):
            with patch('websockets.connect') as mock_connect, \
                 patch('webview.create_window'), \
                 patch('pystray.Icon'):
                
                # Mock connection failure
                mock_connect.side_effect = Exception("Connection failed")
                
                app = HAAssistApp()
                
                with patch.object(app, 'animation_server') as mock_anim_server:
                    mock_anim_server.current_state = "hidden"
                    
                    # Should handle connection error gracefully
                    await app.process_voice_command()
                    
                    # Should show error state
                    error_calls = [call for call in mock_anim_server.change_state.call_args_list 
                                 if call[0][0] == "error"]
                    assert len(error_calls) > 0
    
    def test_audio_error_handling(self):
        """Test audio error handling."""
        from audio import AudioManager
        
        with patch('pyaudio.PyAudio') as mock_pyaudio:
            # Mock audio initialization failure
            mock_pyaudio.side_effect = Exception("Audio device error")
            
            audio_manager = AudioManager()
            
            # Should handle error gracefully
            result = audio_manager.init_audio()
            assert result is False
            
            # Should handle cleanup errors
            audio_manager.stream = Mock()
            audio_manager.audio = Mock()
            audio_manager.stream.stop_stream.side_effect = Exception("Stream error")
            
            # Should not raise exception
            audio_manager.close_audio()
    
    def test_wake_word_error_handling(self):
        """Test wake word detection error handling."""
        from wake_word_detector import WakeWordDetector
        
        with patch.dict('os.environ', {
            'HA_WAKE_WORD_ENABLED': 'true',
            'HA_WAKE_WORD_MODELS': 'alexa'
        }):
            with patch('openwakeword.model.Model') as mock_model:
                # Mock model initialization failure
                mock_model.side_effect = Exception("Model load error")
                
                detector = WakeWordDetector()
                
                # Should handle error gracefully
                assert detector.enabled is False
                assert detector.model is None
                
                # Should handle detection start failure
                result = detector.start_detection()
                assert result is False
    
    @pytest.mark.asyncio
    async def test_animation_server_error_handling(self):
        """Test animation server error handling."""
        from animation_server import AnimationServer
        
        server = AnimationServer()
        
        # Test client handling with errors
        mock_websocket = AsyncMock()
        mock_websocket.remote_address = ("127.0.0.1", 12345)
        mock_websocket.send.side_effect = Exception("Send error")
        
        # Should handle send errors gracefully
        await server._send_to_client(mock_websocket, {"type": "test"})
        
        # Test message handling with invalid JSON
        mock_websocket.reset_mock()
        mock_websocket.__aiter__.return_value = ['invalid json']
        
        with patch.object(server, '_send_to_client'):
            # Should handle invalid JSON gracefully
            await server._handle_client(mock_websocket)