"""
Tests for animation_server module.
"""
import pytest
import json
import asyncio
from unittest.mock import Mock, patch, AsyncMock
import animation_server


class TestAnimationServer:
    """Test cases for AnimationServer class."""
    
    def test_init_default_port(self):
        """Test AnimationServer initialization with default port."""
        server = animation_server.AnimationServer()
        
        assert server.port == 8765
        assert server.current_state == "hidden"
        assert server.clients == set()
        assert server.audio_data_buffer == []
        assert server.server is None
        assert server.loop is None
        assert server.thread is None
    
    def test_init_custom_port(self):
        """Test AnimationServer initialization with custom port."""
        server = animation_server.AnimationServer(port=9999)
        
        assert server.port == 9999
        assert server.current_state == "hidden"
    
    @patch('threading.Thread')
    def test_start(self, mock_thread):
        """Test server start."""
        server = animation_server.AnimationServer()
        mock_thread_instance = Mock()
        mock_thread.return_value = mock_thread_instance
        
        server.start()
        
        mock_thread.assert_called_once()
        mock_thread_instance.start.assert_called_once()
        assert server.thread == mock_thread_instance
    
    @patch('asyncio.new_event_loop')
    @patch('asyncio.set_event_loop')
    def test_run_server_setup(self, mock_set_loop, mock_new_loop):
        """Test server run setup."""
        mock_loop = Mock()
        mock_new_loop.return_value = mock_loop
        
        server = animation_server.AnimationServer()
        
        with patch.object(server, '_start_websocket_server') as mock_start:
            mock_start.return_value = AsyncMock()
            
            # Mock the run_forever to avoid infinite loop
            mock_loop.run_forever.side_effect = KeyboardInterrupt()
            
            try:
                server._run_server()
            except KeyboardInterrupt:
                pass
            
            mock_set_loop.assert_called_once_with(mock_loop)
            assert server.loop == mock_loop
            mock_loop.run_until_complete.assert_called_once()
    
    @patch('websockets.serve')
    async def test_start_websocket_server(self, mock_serve):
        """Test WebSocket server start."""
        mock_server = AsyncMock()
        mock_serve.return_value = mock_server
        
        server = animation_server.AnimationServer(port=8765)
        
        await server._start_websocket_server()
        
        mock_serve.assert_called_once_with(
            server._handle_client,
            "localhost",
            8765,
            ping_interval=None,
            ping_timeout=None
        )
        assert server.server == mock_server
    
    async def test_handle_client_connection(self):
        """Test client connection handling."""
        server = animation_server.AnimationServer()
        mock_websocket = AsyncMock()
        mock_websocket.remote_address = ("127.0.0.1", 12345)
        mock_websocket.__aiter__.return_value = []  # No messages
        
        with patch.object(server, '_send_to_client') as mock_send:
            try:
                await server._handle_client(mock_websocket)
            except StopAsyncIteration:
                pass
            
            # Should add client to set
            assert mock_websocket in server.clients
            
            # Should send initial state
            mock_send.assert_called_once_with(
                mock_websocket,
                {"type": "state_change", "state": "hidden"}
            )
    
    async def test_handle_client_disconnection(self):
        """Test client disconnection handling."""
        server = animation_server.AnimationServer()
        mock_websocket = AsyncMock()
        mock_websocket.remote_address = ("127.0.0.1", 12345)
        
        # Simulate connection closed exception
        mock_websocket.__aiter__.side_effect = Exception("Connection closed")
        
        with patch.object(server, '_send_to_client'):
            try:
                await server._handle_client(mock_websocket)
            except Exception:
                pass
            
            # Client should be removed from set
            assert mock_websocket not in server.clients
    
    async def test_handle_message_ping(self):
        """Test ping message handling."""
        server = animation_server.AnimationServer()
        mock_websocket = AsyncMock()
        
        with patch.object(server, '_send_to_client') as mock_send:
            await server._handle_message(mock_websocket, {"type": "ping"})
            
            mock_send.assert_called_once_with(
                mock_websocket,
                {"type": "pong"}
            )
    
    async def test_handle_message_ready(self):
        """Test ready message handling."""
        server = animation_server.AnimationServer()
        mock_websocket = AsyncMock()
        
        with patch.object(server, '_send_to_client') as mock_send:
            await server._handle_message(mock_websocket, {"type": "ready"})
            
            # Should send current state
            mock_send.assert_called_once_with(
                mock_websocket,
                {"type": "state_change", "state": "hidden"}
            )
    
    async def test_handle_message_voice_command(self):
        """Test voice command message handling."""
        server = animation_server.AnimationServer()
        mock_websocket = AsyncMock()
        mock_callback = Mock()
        server.voice_command_callback = mock_callback
        
        await server._handle_message(mock_websocket, {"type": "voice_command"})
        
        mock_callback.assert_called_once()
    
    async def test_handle_message_unknown_type(self):
        """Test unknown message type handling."""
        server = animation_server.AnimationServer()
        mock_websocket = AsyncMock()
        
        # Should not raise exception
        await server._handle_message(mock_websocket, {"type": "unknown"})
    
    async def test_send_to_client_success(self):
        """Test successful message sending to client."""
        server = animation_server.AnimationServer()
        mock_websocket = AsyncMock()
        
        message = {"type": "test", "data": "value"}
        
        await server._send_to_client(mock_websocket, message)
        
        mock_websocket.send.assert_called_once_with(json.dumps(message))
    
    async def test_send_to_client_exception(self):
        """Test message sending with exception."""
        server = animation_server.AnimationServer()
        mock_websocket = AsyncMock()
        mock_websocket.send.side_effect = Exception("Send error")
        
        message = {"type": "test", "data": "value"}
        
        # Should not raise exception
        await server._send_to_client(mock_websocket, message)
    
    def test_broadcast_to_clients_success(self):
        """Test successful broadcast to all clients."""
        server = animation_server.AnimationServer()
        server.loop = Mock()
        
        # Add mock clients
        mock_client1 = Mock()
        mock_client2 = Mock()
        server.clients = {mock_client1, mock_client2}
        
        message = {"type": "broadcast", "data": "value"}
        
        with patch.object(server, '_send_to_client') as mock_send:
            server._broadcast_to_clients(message)
            
            # Should schedule tasks for all clients
            assert server.loop.create_task.call_count == 2
    
    def test_broadcast_to_clients_no_loop(self):
        """Test broadcast without event loop."""
        server = animation_server.AnimationServer()
        server.loop = None
        
        message = {"type": "broadcast", "data": "value"}
        
        # Should not raise exception
        server._broadcast_to_clients(message)
    
    def test_change_state(self):
        """Test state change."""
        server = animation_server.AnimationServer()
        server.loop = Mock()
        
        with patch.object(server, '_broadcast_to_clients') as mock_broadcast:
            server.change_state("listening")
            
            assert server.current_state == "listening"
            mock_broadcast.assert_called_once_with({
                "type": "state_change",
                "state": "listening",
                "message": None
            })
    
    def test_change_state_with_message(self):
        """Test state change with message."""
        server = animation_server.AnimationServer()
        server.loop = Mock()
        
        with patch.object(server, '_broadcast_to_clients') as mock_broadcast:
            server.change_state("error", "Test error message")
            
            assert server.current_state == "error"
            mock_broadcast.assert_called_once_with({
                "type": "state_change",
                "state": "error",
                "message": "Test error message"
            })
    
    def test_send_audio_data(self):
        """Test audio data sending."""
        server = animation_server.AnimationServer()
        server.loop = Mock()
        
        audio_data = b"test_audio_data"
        
        with patch.object(server, '_broadcast_to_clients') as mock_broadcast, \
             patch('animation_server.utils.convert_audio_chunk_to_float32') as mock_convert:
            
            mock_convert.return_value = [0.1, 0.2, 0.3]
            
            server.send_audio_data(audio_data)
            
            mock_convert.assert_called_once_with(audio_data)
            mock_broadcast.assert_called_once_with({
                "type": "audio_data",
                "data": [0.1, 0.2, 0.3]
            })
    
    def test_send_audio_data_exception(self):
        """Test audio data sending with exception."""
        server = animation_server.AnimationServer()
        server.loop = Mock()
        
        audio_data = b"test_audio_data"
        
        with patch.object(server, '_broadcast_to_clients') as mock_broadcast, \
             patch('animation_server.utils.convert_audio_chunk_to_float32') as mock_convert:
            
            mock_convert.side_effect = Exception("Conversion error")
            
            # Should not raise exception
            server.send_audio_data(audio_data)
            
            mock_broadcast.assert_not_called()
    
    def test_send_response_text(self):
        """Test response text sending."""
        server = animation_server.AnimationServer()
        server.loop = Mock()
        
        response_text = "Test response"
        
        with patch.object(server, '_broadcast_to_clients') as mock_broadcast:
            server.send_response_text(response_text)
            
            mock_broadcast.assert_called_once_with({
                "type": "response_text",
                "text": response_text
            })
    
    def test_show_success(self):
        """Test success message display."""
        server = animation_server.AnimationServer()
        server.loop = Mock()
        
        with patch.object(server, 'change_state') as mock_change_state:
            server.show_success("Success message", duration=3.0)
            
            mock_change_state.assert_called_once_with("success", "Success message")
    
    def test_show_error(self):
        """Test error message display."""
        server = animation_server.AnimationServer()
        server.loop = Mock()
        
        with patch.object(server, 'change_state') as mock_change_state:
            server.show_error("Error message", duration=5.0)
            
            mock_change_state.assert_called_once_with("error", "Error message")
    
    def test_set_voice_command_callback(self):
        """Test voice command callback setting."""
        server = animation_server.AnimationServer()
        callback = Mock()
        
        server.set_voice_command_callback(callback)
        
        assert server.voice_command_callback == callback
    
    def test_stop(self):
        """Test server stop."""
        server = animation_server.AnimationServer()
        server.loop = Mock()
        server.server = Mock()
        
        server.stop()
        
        server.loop.call_soon_threadsafe.assert_called_once()
        # The actual stop logic would be in the scheduled function
    
    def test_stop_no_loop(self):
        """Test server stop without event loop."""
        server = animation_server.AnimationServer()
        server.loop = None
        server.server = Mock()
        
        # Should not raise exception
        server.stop()
    
    async def test_stop_server_success(self):
        """Test successful server stop."""
        server = animation_server.AnimationServer()
        server.server = AsyncMock()
        
        await server._stop_server()
        
        server.server.close.assert_called_once()
        server.server.wait_closed.assert_called_once()
        assert server.server is None
    
    async def test_stop_server_no_server(self):
        """Test server stop when no server exists."""
        server = animation_server.AnimationServer()
        server.server = None
        
        # Should not raise exception
        await server._stop_server()
    
    async def test_stop_server_exception(self):
        """Test server stop with exception."""
        server = animation_server.AnimationServer()
        server.server = AsyncMock()
        server.server.close.side_effect = Exception("Close error")
        
        # Should not raise exception
        await server._stop_server()
        
        assert server.server is None


class TestAnimationServerIntegration:
    """Integration tests for AnimationServer."""
    
    @pytest.mark.asyncio
    async def test_full_client_lifecycle(self):
        """Test complete client connection lifecycle."""
        server = animation_server.AnimationServer()
        
        # Mock WebSocket client
        mock_websocket = AsyncMock()
        mock_websocket.remote_address = ("127.0.0.1", 12345)
        
        # Simulate message exchange
        messages = [
            '{"type": "ping"}',
            '{"type": "ready"}',
            '{"type": "voice_command"}'
        ]
        
        mock_websocket.__aiter__.return_value = messages
        
        callback = Mock()
        server.set_voice_command_callback(callback)
        
        with patch.object(server, '_send_to_client') as mock_send:
            await server._handle_client(mock_websocket)
            
            # Should handle all messages
            assert mock_send.call_count >= 3  # Initial state + ping response + ready response
            callback.assert_called_once()  # Voice command callback
    
    @pytest.mark.asyncio
    async def test_state_changes_broadcast(self):
        """Test that state changes are broadcast to all clients."""
        server = animation_server.AnimationServer()
        server.loop = asyncio.get_event_loop()
        
        # Add mock clients
        mock_client1 = AsyncMock()
        mock_client2 = AsyncMock()
        server.clients = {mock_client1, mock_client2}
        
        # Change state
        server.change_state("listening", "Listening for voice")
        
        # Wait for async tasks to complete
        await asyncio.sleep(0.1)
        
        # Both clients should receive the state change
        expected_message = json.dumps({
            "type": "state_change",
            "state": "listening",
            "message": "Listening for voice"
        })
        
        mock_client1.send.assert_called_with(expected_message)
        mock_client2.send.assert_called_with(expected_message)