"""
Tests for animation_server module.
"""
import pytest
import json
import asyncio
import numpy as np
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

    @patch('websockets.serve', new_callable=AsyncMock)
    async def test_start_websocket_server(self, mock_serve):
        """Test WebSocket server start."""
        mock_server = Mock()
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
        seen_during_send = []

        async def record_clients(*args):
            seen_during_send.append(mock_websocket in server.clients)

        with patch.object(server, '_send_to_client', side_effect=record_clients) as mock_send:
            await server._handle_client(mock_websocket)

            mock_send.assert_called_once_with(
                mock_websocket,
                {"type": "state_change", "state": "hidden"}
            )
            assert seen_during_send == [True]
            assert mock_websocket not in server.clients

    @pytest.mark.parametrize("state,message,key", [
        ("error", "Boom", "errorMessage"),
        ("success", "Done", "successMessage"),
    ])
    async def test_handle_client_initial_state_with_message(self, state, message, key):
        """Test that a new client receives the current state with its message."""
        server = animation_server.AnimationServer()
        server.current_state = state
        server.current_state_message = message
        mock_websocket = AsyncMock()
        mock_websocket.remote_address = ("127.0.0.1", 12345)
        mock_websocket.__aiter__.return_value = []

        with patch.object(server, '_send_to_client') as mock_send:
            await server._handle_client(mock_websocket)

            mock_send.assert_called_once_with(
                mock_websocket,
                {"type": "state_change", "state": state, key: message}
            )

    async def test_handle_client_invalid_json(self):
        """Test that invalid JSON from a client is ignored."""
        server = animation_server.AnimationServer()
        mock_websocket = AsyncMock()
        mock_websocket.remote_address = ("127.0.0.1", 12345)
        mock_websocket.__aiter__.return_value = ["not json"]

        with patch.object(server, '_send_to_client') as mock_send, \
             patch.object(server, '_handle_message') as mock_handle:
            await server._handle_client(mock_websocket)

            mock_send.assert_called_once()
            mock_handle.assert_not_called()
            assert mock_websocket not in server.clients

    async def test_handle_client_disconnection(self):
        """Test client disconnection handling."""
        server = animation_server.AnimationServer()
        mock_websocket = AsyncMock()
        mock_websocket.remote_address = ("127.0.0.1", 12345)

        # Simulate connection closed exception
        mock_websocket.__aiter__.side_effect = Exception("Connection closed")

        with patch.object(server, '_send_to_client'):
            await server._handle_client(mock_websocket)

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

            mock_send.assert_not_called()

    async def test_handle_message_activate_voice_command(self):
        """Test voice command activation when the app is hidden."""
        server = animation_server.AnimationServer()
        mock_websocket = AsyncMock()
        mock_callback = Mock()
        server.voice_command_callback = mock_callback

        await server._handle_message(mock_websocket, {"type": "activate_voice_command"})

        mock_callback.assert_called_once()

    async def test_handle_message_activate_voice_command_ignored_when_busy(self):
        """Test voice command activation is ignored outside the hidden state."""
        server = animation_server.AnimationServer()
        server.current_state = "listening"
        mock_websocket = AsyncMock()
        mock_callback = Mock()
        server.voice_command_callback = mock_callback

        await server._handle_message(mock_websocket, {"type": "activate_voice_command"})

        mock_callback.assert_not_called()

    async def test_handle_message_activate_voice_command_no_callback(self):
        """Test voice command activation without a registered callback."""
        server = animation_server.AnimationServer()
        mock_websocket = AsyncMock()

        # Should not raise exception
        await server._handle_message(mock_websocket, {"type": "activate_voice_command"})

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
        """Test that send failures propagate so callers can drop the client."""
        server = animation_server.AnimationServer()
        mock_websocket = AsyncMock()
        mock_websocket.send.side_effect = Exception("Send error")

        message = {"type": "test", "data": "value"}

        with pytest.raises(Exception, match="Send error"):
            await server._send_to_client(mock_websocket, message)

    async def test_broadcast_sends_to_all_clients(self):
        """Test broadcast to all clients."""
        server = animation_server.AnimationServer()
        client1 = AsyncMock()
        client2 = AsyncMock()
        server.clients = {client1, client2}
        message = {"type": "broadcast", "data": "value"}

        await server._broadcast(message)

        client1.send.assert_called_once_with(json.dumps(message))
        client2.send.assert_called_once_with(json.dumps(message))
        assert server.clients == {client1, client2}

    async def test_broadcast_no_clients(self):
        """Test broadcast without clients."""
        server = animation_server.AnimationServer()

        with patch.object(server, '_send_to_client') as mock_send:
            await server._broadcast({"type": "broadcast"})

            mock_send.assert_not_called()

    async def test_broadcast_removes_failed_clients(self):
        """Test that clients whose send raises are dropped from the set."""
        server = animation_server.AnimationServer()
        good = AsyncMock()
        bad = AsyncMock()
        server.clients = {good, bad}

        async def send(client, data):
            if client is bad:
                raise Exception("Send error")

        with patch.object(server, '_send_to_client', side_effect=send):
            await server._broadcast({"type": "broadcast"})

        assert server.clients == {good}

    async def test_broadcast_removes_client_with_failing_send(self):
        """Test that a client whose websocket send fails is dropped from the set."""
        server = animation_server.AnimationServer()
        good = AsyncMock()
        bad = AsyncMock()
        bad.send.side_effect = Exception("Send error")
        server.clients = {good, bad}

        await server._broadcast({"type": "broadcast"})

        assert server.clients == {good}

    def test_safe_broadcast_schedules_on_running_loop(self):
        """Test thread-safe broadcast scheduling."""
        server = animation_server.AnimationServer()
        server.loop = Mock()
        server.loop.is_running.return_value = True
        message = {"type": "broadcast"}

        with patch.object(server, '_broadcast', new=Mock()) as mock_broadcast, \
             patch('asyncio.run_coroutine_threadsafe') as mock_run:
            server._safe_broadcast(message)

            mock_broadcast.assert_called_once_with(message)
            mock_run.assert_called_once_with(mock_broadcast.return_value, server.loop)

    def test_safe_broadcast_no_loop(self):
        """Test thread-safe broadcast without event loop."""
        server = animation_server.AnimationServer()
        server.loop = None

        with patch('asyncio.run_coroutine_threadsafe') as mock_run:
            server._safe_broadcast({"type": "broadcast"})

            mock_run.assert_not_called()

    def test_safe_broadcast_loop_not_running(self):
        """Test thread-safe broadcast with a stopped event loop."""
        server = animation_server.AnimationServer()
        server.loop = Mock()
        server.loop.is_running.return_value = False

        with patch('asyncio.run_coroutine_threadsafe') as mock_run:
            server._safe_broadcast({"type": "broadcast"})

            mock_run.assert_not_called()

    def test_change_state(self):
        """Test state change."""
        server = animation_server.AnimationServer()

        with patch.object(server, '_safe_broadcast') as mock_broadcast, \
             patch('animation_server.utils.get_timestamp', return_value=123):
            server.change_state("listening")

            assert server.current_state == "listening"
            assert server.current_state_message == ""
            mock_broadcast.assert_called_once_with({
                "type": "state_change",
                "state": "listening",
                "timestamp": 123
            })

    def test_change_state_with_error_message(self):
        """Test state change with error message."""
        server = animation_server.AnimationServer()

        with patch.object(server, '_safe_broadcast') as mock_broadcast, \
             patch('animation_server.utils.get_timestamp', return_value=123):
            server.change_state("error", error_message="Test error message")

            assert server.current_state == "error"
            assert server.current_state_message == "Test error message"
            mock_broadcast.assert_called_once_with({
                "type": "state_change",
                "state": "error",
                "timestamp": 123,
                "errorMessage": "Test error message"
            })

    def test_change_state_with_success_message(self):
        """Test state change with success message."""
        server = animation_server.AnimationServer()

        with patch.object(server, '_safe_broadcast') as mock_broadcast, \
             patch('animation_server.utils.get_timestamp', return_value=123):
            server.change_state("success", success_message="Done")

            assert server.current_state_message == "Done"
            mock_broadcast.assert_called_once_with({
                "type": "state_change",
                "state": "success",
                "timestamp": 123,
                "successMessage": "Done"
            })

    def test_change_state_extra_kwargs(self):
        """Test that extra kwargs are included in the broadcast message."""
        server = animation_server.AnimationServer()

        with patch.object(server, '_safe_broadcast') as mock_broadcast:
            server.change_state("listening", wake_word="alexa")

            assert mock_broadcast.call_args.args[0]["wake_word"] == "alexa"

    def test_change_state_same_state_is_noop(self):
        """Test that repeating the same state without a message is ignored."""
        server = animation_server.AnimationServer()
        callback = Mock()
        server.set_window_visibility_callback(callback)
        server.current_state = "listening"

        with patch.object(server, '_safe_broadcast') as mock_broadcast:
            server.change_state("listening")

            mock_broadcast.assert_not_called()
            callback.assert_not_called()

    def test_change_state_same_state_with_message_broadcasts(self):
        """Test that repeating the same state with a message is not ignored."""
        server = animation_server.AnimationServer()
        server.current_state = "error"

        with patch.object(server, '_safe_broadcast') as mock_broadcast:
            server.change_state("error", error_message="Another error")

            mock_broadcast.assert_called_once()
            assert server.current_state_message == "Another error"

    @pytest.mark.parametrize("state,visible", [("listening", True), ("hidden", False)])
    def test_change_state_window_visibility_callback(self, state, visible):
        """Test window visibility callback on state change."""
        server = animation_server.AnimationServer()
        server.current_state = "processing"
        callback = Mock()
        server.set_window_visibility_callback(callback)

        with patch.object(server, '_safe_broadcast'):
            server.change_state(state)

        callback.assert_called_once_with(visible)

    def test_change_state_window_visibility_callback_exception(self):
        """Test that a failing visibility callback does not break state change."""
        server = animation_server.AnimationServer()
        server.set_window_visibility_callback(Mock(side_effect=Exception("Callback error")))

        with patch.object(server, '_safe_broadcast'):
            server.change_state("listening")

        assert server.current_state == "listening"

    def test_send_audio_data(self):
        """Test audio data sending."""
        server = animation_server.AnimationServer()
        samples = (np.sin(np.arange(1024) / 5) * 1000).astype(np.int16)

        with patch.object(server, '_safe_broadcast') as mock_broadcast, \
             patch('animation_server.utils.get_timestamp', return_value=123):
            server.send_audio_data(samples.tobytes())

            mock_broadcast.assert_called_once()
            message = mock_broadcast.call_args.args[0]
            assert message["type"] == "audio_data"
            assert message["timestamp"] == 123
            assert len(message["fft"]) == 32
            assert max(message["fft"]) == pytest.approx(1.0)
            assert all(0.0 <= val <= 1.0 for val in message["fft"])

    def test_send_audio_data_short_chunk(self):
        """Test that short chunks are not binned down to 32 values."""
        server = animation_server.AnimationServer()
        samples = np.arange(1, 33, dtype=np.int16)

        with patch.object(server, '_safe_broadcast') as mock_broadcast:
            server.send_audio_data(samples.tobytes())

            assert len(mock_broadcast.call_args.args[0]["fft"]) == 16

    def test_send_audio_data_silence(self):
        """Test that a silent chunk produces a zero spectrum."""
        server = animation_server.AnimationServer()

        with patch.object(server, '_safe_broadcast') as mock_broadcast:
            server.send_audio_data(np.zeros(1024, dtype=np.int16).tobytes())

            assert mock_broadcast.call_args.args[0]["fft"] == [0.0] * 32

    def test_send_audio_data_exception(self):
        """Test audio data sending with exception."""
        server = animation_server.AnimationServer()

        with patch.object(server, '_safe_broadcast') as mock_broadcast:
            # Odd byte count cannot be interpreted as int16
            server.send_audio_data(b"abc")

            mock_broadcast.assert_not_called()

    def test_send_response_text(self):
        """Test response text sending."""
        server = animation_server.AnimationServer()

        with patch.object(server, '_safe_broadcast') as mock_broadcast, \
             patch('animation_server.utils.get_timestamp', return_value=123):
            server.send_response_text("Test response")

            mock_broadcast.assert_called_once_with({
                "type": "response_text",
                "text": "Test response",
                "timestamp": 123
            })

    @pytest.mark.parametrize("method,state,kwarg", [
        ("show_success", "success", "success_message"),
        ("show_error", "error", "error_message"),
        ("show_update", "update", "success_message"),
    ])
    @patch('time.sleep')
    @patch('threading.Thread')
    def test_show_auto_hides(self, mock_thread, mock_sleep, method, state, kwarg):
        """Test timed states change state and schedule a hide."""
        server = animation_server.AnimationServer()

        with patch.object(server, 'change_state') as mock_change_state:
            getattr(server, method)("Test message", duration=2.5)

            mock_change_state.assert_called_once_with(state, **{kwarg: "Test message"})
            mock_thread.assert_called_once()
            assert mock_thread.call_args.kwargs["daemon"] is True
            mock_thread.return_value.start.assert_called_once()

            mock_change_state.reset_mock()
            server.current_state = state
            mock_thread.call_args.kwargs["target"]()

            mock_sleep.assert_called_once_with(2.5)
            mock_change_state.assert_called_once_with("hidden")

    @pytest.mark.parametrize("method", ["show_success", "show_error", "show_update"])
    @patch('time.sleep')
    @patch('threading.Thread')
    def test_show_does_not_hide_if_state_changed(self, mock_thread, mock_sleep, method):
        """Test that the delayed hide is skipped when another state took over."""
        server = animation_server.AnimationServer()

        with patch.object(server, 'change_state') as mock_change_state:
            getattr(server, method)("Test message")
            mock_change_state.reset_mock()
            server.current_state = "listening"
            mock_thread.call_args.kwargs["target"]()

            mock_change_state.assert_not_called()

    @patch('threading.Thread')
    def test_show_connecting(self, mock_thread):
        """Test that the connecting state is persistent."""
        server = animation_server.AnimationServer()

        with patch.object(server, 'change_state') as mock_change_state:
            server.show_connecting("Connecting to HA")

            mock_change_state.assert_called_once_with("connecting", success_message="Connecting to HA")
            mock_thread.assert_not_called()

    def test_set_voice_command_callback(self):
        """Test voice command callback setting."""
        server = animation_server.AnimationServer()
        callback = Mock()

        server.set_voice_command_callback(callback)

        assert server.voice_command_callback == callback

    def test_set_window_visibility_callback(self):
        """Test window visibility callback setting."""
        server = animation_server.AnimationServer()
        callback = Mock()

        server.set_window_visibility_callback(callback)

        assert server.window_visibility_callback == callback

    def test_stop(self):
        """Test server stop."""
        server = animation_server.AnimationServer()
        server.loop = Mock()
        server.loop.is_closed.return_value = False
        server.loop.is_running.return_value = True
        pending_task = Mock()
        pending_task.done.return_value = False
        server.thread = Mock()
        server.thread.is_alive.return_value = True

        with patch('asyncio.all_tasks', return_value={pending_task}):
            server.stop()

        server.loop.call_soon_threadsafe.assert_called_once_with(server.loop.stop)
        pending_task.cancel.assert_called_once()
        server.thread.join.assert_called_once_with(timeout=3)

    def test_stop_loop_not_running(self):
        """Test server stop with a loop that is not running."""
        server = animation_server.AnimationServer()
        server.loop = Mock()
        server.loop.is_closed.return_value = False
        server.loop.is_running.return_value = False

        with patch('asyncio.all_tasks', return_value=set()):
            server.stop()

        server.loop.call_soon_threadsafe.assert_not_called()

    def test_stop_no_loop(self):
        """Test server stop without event loop."""
        server = animation_server.AnimationServer()
        server.loop = None
        server.server = Mock()

        # Should not raise exception
        server.stop()


class TestAnimationServerIntegration:
    """Integration tests for AnimationServer."""

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
            '{"type": "activate_voice_command"}'
        ]

        mock_websocket.__aiter__.return_value = messages

        callback = Mock()
        server.set_voice_command_callback(callback)

        await server._handle_client(mock_websocket)

        sent = [json.loads(call.args[0]) for call in mock_websocket.send.call_args_list]
        assert sent == [
            {"type": "state_change", "state": "hidden"},
            {"type": "pong"}
        ]
        callback.assert_called_once()
        assert mock_websocket not in server.clients

    async def test_state_changes_broadcast(self):
        """Test that state changes are broadcast to all clients."""
        server = animation_server.AnimationServer()
        server.loop = asyncio.get_running_loop()

        # Add mock clients
        mock_client1 = AsyncMock()
        mock_client2 = AsyncMock()
        server.clients = {mock_client1, mock_client2}

        # Change state
        with patch('animation_server.utils.get_timestamp', return_value=123):
            server.change_state("error", error_message="Something failed")

        # Let the scheduled broadcast run
        await asyncio.sleep(0.01)

        # Both clients should receive the state change
        expected_message = json.dumps({
            "type": "state_change",
            "state": "error",
            "timestamp": 123,
            "errorMessage": "Something failed"
        })

        mock_client1.send.assert_called_once_with(expected_message)
        mock_client2.send.assert_called_once_with(expected_message)
