"""
Tests for client module (Home Assistant WebSocket client).
"""
import pytest
import json
import asyncio
from unittest.mock import Mock, patch, AsyncMock
import client


RUN_START = {
    "type": "event",
    "event": {
        "type": "run-start",
        "data": {
            "runner_data": {"stt_binary_handler_id": 1},
            "tts_output": {"url": "/api/tts_proxy/test.wav"}
        }
    }
}


@pytest.fixture(autouse=True)
def ha_env(monkeypatch):
    """Pin client configuration to known values, independent of the developer's environment."""
    monkeypatch.setenv('HA_HOST', 'test-host:8123')
    monkeypatch.setenv('HA_TOKEN', 'test-token')
    for key in ('HA_PIPELINE_ID', 'HA_AI_AGENT_ID', 'HA_SAMPLE_RATE', 'HA_CONVERSATION_TIMEOUT'):
        monkeypatch.delenv(key, raising=False)


class TestHomeAssistantClient:
    """Test cases for HomeAssistantClient class."""

    @patch.dict('os.environ', {
        'HA_HOST': 'test-host:8123',
        'HA_TOKEN': 'test-token',
        'HA_PIPELINE_ID': 'test-pipeline',
        'HA_SAMPLE_RATE': '16000'
    })
    def test_init_success(self):
        """Test successful client initialization."""
        ha_client = client.HomeAssistantClient()

        assert ha_client.host == 'test-host:8123'
        assert ha_client.token == 'test-token'
        assert ha_client.pipeline_id == 'test-pipeline'
        assert ha_client.sample_rate == 16000
        assert ha_client.connected is False
        assert ha_client.message_id == 1

    def test_init_missing_token(self, monkeypatch):
        """Test initialization with missing token."""
        monkeypatch.delenv('HA_TOKEN')

        with pytest.raises(ValueError, match="Missing access token"):
            client.HomeAssistantClient()

    async def test_connect_success(self):
        """Test successful WebSocket connection."""
        mock_ws = AsyncMock()
        mock_ws.recv.side_effect = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"})
        ]

        ha_client = client.HomeAssistantClient()

        with patch('websockets.connect', AsyncMock(return_value=mock_ws)), \
             patch.object(ha_client, 'fetch_available_pipelines', AsyncMock()) as mock_fetch:
            result = await ha_client.connect()

            assert result is True
            assert ha_client.connected is True
            assert ha_client.websocket == mock_ws
            mock_fetch.assert_awaited_once()

            mock_ws.send.assert_called_once()
            sent_message = json.loads(mock_ws.send.call_args[0][0])
            assert sent_message["type"] == "auth"
            assert sent_message["access_token"] == ha_client.token

    async def test_connect_timeout(self):
        """Test connection timeout."""
        ha_client = client.HomeAssistantClient()

        with patch('websockets.connect', AsyncMock(side_effect=asyncio.TimeoutError())):
            result = await ha_client.connect()

        assert result is False
        assert ha_client.connected is False

    async def test_connect_auth_failed(self):
        """Test connection with authentication failure."""
        mock_ws = AsyncMock()
        mock_ws.recv.side_effect = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_invalid", "message": "Invalid token"})
        ]

        ha_client = client.HomeAssistantClient()

        with patch('websockets.connect', AsyncMock(return_value=mock_ws)):
            result = await ha_client.connect()

        assert result is False
        assert ha_client.connected is False
        mock_ws.close.assert_awaited_once()

    async def test_connect_unexpected_message(self):
        """Test connection with unexpected initial message."""
        mock_ws = AsyncMock()
        mock_ws.recv.return_value = json.dumps({"type": "unexpected"})

        ha_client = client.HomeAssistantClient()

        with patch('websockets.connect', AsyncMock(return_value=mock_ws)):
            result = await ha_client.connect()

        assert result is False
        assert ha_client.connected is False
        mock_ws.send.assert_not_called()

    async def test_fetch_available_pipelines_success(self):
        """Test successful pipeline fetching."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = AsyncMock()
        ha_client.message_id = 1

        pipeline_response = {
            "id": 1,
            "type": "result",
            "success": True,
            "result": {
                "pipelines": [
                    {"id": "pipeline1", "name": "Pipeline 1", "language": "en"},
                    {"id": "pipeline2", "name": "Pipeline 2", "language": "pl"}
                ],
                "preferred_pipeline": "pipeline2"
            }
        }

        ha_client.websocket.recv.return_value = json.dumps(pipeline_response)

        result = await ha_client.fetch_available_pipelines()

        assert result is True
        assert len(ha_client.available_pipelines) == 2
        assert ha_client.available_pipelines[0]["name"] == "Pipeline 1"
        assert ha_client.available_pipelines[1]["name"] == "Pipeline 2"
        assert ha_client.available_pipelines[1]["is_preferred"] is True
        assert ha_client.get_preferred_pipeline_id() == "pipeline2"
        assert ha_client.message_id == 2

    async def test_fetch_available_pipelines_error(self):
        """Test pipeline fetching with error response."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = AsyncMock()
        ha_client.message_id = 1

        error_response = {
            "id": 1,
            "type": "result",
            "success": False,
            "error": {"code": "unknown_error", "message": "Failed to fetch pipelines"}
        }

        ha_client.websocket.recv.return_value = json.dumps(error_response)

        result = await ha_client.fetch_available_pipelines()

        assert result is False
        assert len(ha_client.available_pipelines) == 0
        assert ha_client.message_id == 2

    async def test_fetch_available_pipelines_timeout(self):
        """Test pipeline fetching with timeout."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = AsyncMock()
        ha_client.websocket.recv.side_effect = asyncio.TimeoutError()

        result = await ha_client.fetch_available_pipelines()

        assert result is False
        assert len(ha_client.available_pipelines) == 0

    def test_get_available_pipelines(self):
        """Test getting available pipelines."""
        ha_client = client.HomeAssistantClient()
        ha_client.available_pipelines = [
            {"id": "pipeline1", "name": "Pipeline 1"},
            {"id": "pipeline2", "name": "Pipeline 2"}
        ]

        pipelines = ha_client.get_available_pipelines()

        assert len(pipelines) == 2
        assert pipelines[0]["name"] == "Pipeline 1"

    def test_validate_pipeline_id_valid(self):
        """Test pipeline ID validation with valid ID."""
        ha_client = client.HomeAssistantClient()
        ha_client.available_pipelines = [
            {"id": "pipeline1", "name": "Pipeline 1"},
            {"id": "pipeline2", "name": "Pipeline 2"}
        ]

        result = ha_client.validate_pipeline_id("pipeline1")
        assert result is True

    def test_validate_pipeline_id_invalid(self):
        """Test pipeline ID validation with invalid ID."""
        ha_client = client.HomeAssistantClient()
        ha_client.available_pipelines = [
            {"id": "pipeline1", "name": "Pipeline 1"},
            {"id": "pipeline2", "name": "Pipeline 2"}
        ]

        result = ha_client.validate_pipeline_id("nonexistent")
        assert result is False

    def test_validate_pipeline_id_empty_list(self):
        """Test pipeline ID validation with empty pipeline list."""
        ha_client = client.HomeAssistantClient()
        ha_client.available_pipelines = []

        result = ha_client.validate_pipeline_id("pipeline1")
        assert result is False

    async def test_start_assist_pipeline_success(self):
        """Test successful Assist pipeline start."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = AsyncMock()
        ha_client.message_id = 1

        ha_client.websocket.recv.side_effect = [
            json.dumps({"id": 1, "type": "result", "success": True, "result": None}),
            json.dumps(RUN_START)
        ]

        result = await ha_client.start_assist_pipeline()

        assert result is True
        assert ha_client.message_id == 2
        assert ha_client.stt_binary_handler_id == 1
        assert ha_client.audio_url == "/api/tts_proxy/test.wav"

        ha_client.websocket.send.assert_called_once()
        sent_message = json.loads(ha_client.websocket.send.call_args[0][0])
        assert sent_message["type"] == "assist_pipeline/run"
        assert "pipeline" not in sent_message

    async def test_start_assist_pipeline_with_pipeline_id(self):
        """Test Assist pipeline start with specific pipeline ID."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = AsyncMock()
        ha_client.message_id = 1
        ha_client.pipeline_id = "test-pipeline"
        ha_client.available_pipelines = [{"id": "test-pipeline", "name": "Test"}]

        ha_client.websocket.recv.return_value = json.dumps(RUN_START)

        result = await ha_client.start_assist_pipeline()

        assert result is True

        sent_message = json.loads(ha_client.websocket.send.call_args[0][0])
        assert sent_message["pipeline"] == "test-pipeline"
        assert sent_message["start_stage"] == "stt"
        assert sent_message["end_stage"] == "tts"
        assert sent_message["input"]["sample_rate"] == ha_client.sample_rate

    async def test_start_assist_pipeline_unknown_pipeline_id(self):
        """Test that an unavailable pipeline ID falls back to the default pipeline."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = AsyncMock()
        ha_client.pipeline_id = "missing-pipeline"
        ha_client.available_pipelines = [{"id": "other", "name": "Other"}]

        ha_client.websocket.recv.return_value = json.dumps(RUN_START)

        result = await ha_client.start_assist_pipeline()

        assert result is True
        assert ha_client.pipeline_id is None
        sent_message = json.loads(ha_client.websocket.send.call_args[0][0])
        assert "pipeline" not in sent_message

    async def test_start_assist_pipeline_error_event(self):
        """Test Assist pipeline start with error event."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = AsyncMock()
        ha_client.message_id = 1

        error_event = {
            "type": "event",
            "event": {
                "type": "error",
                "data": {"code": "pipeline_not_found", "message": "Pipeline not found"}
            }
        }

        ha_client.websocket.recv.return_value = json.dumps(error_event)

        result = await ha_client.start_assist_pipeline()

        assert result is False
        assert ha_client.stt_binary_handler_id is None

    async def test_start_assist_pipeline_error_result(self):
        """Test Assist pipeline start with failed result message."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = AsyncMock()
        ha_client.message_id = 1

        error_response = {
            "id": 1,
            "type": "result",
            "success": False,
            "error": {"code": "pipeline_not_found", "message": "Pipeline not found"}
        }

        ha_client.websocket.recv.side_effect = [
            json.dumps(error_response),
            asyncio.TimeoutError()
        ]

        result = await ha_client.start_assist_pipeline()

        assert result is False
        assert ha_client.websocket.recv.call_count == 1

    async def test_start_assist_pipeline_timeout(self):
        """Test Assist pipeline start with timeout."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = AsyncMock()
        ha_client.websocket.recv.side_effect = asyncio.TimeoutError()

        result = await ha_client.start_assist_pipeline(timeout_seconds=1)

        assert result is False

    async def test_send_audio_chunk_success(self):
        """Test successful audio chunk sending."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = AsyncMock()
        ha_client.stt_binary_handler_id = 123

        audio_data = b"test_audio_data"

        result = await ha_client.send_audio_chunk(audio_data)

        assert result is True
        ha_client.websocket.send.assert_called_once_with(bytearray([123]) + audio_data)

    async def test_send_audio_chunk_no_handler(self):
        """Test audio chunk sending without handler ID."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = AsyncMock()
        ha_client.stt_binary_handler_id = None

        audio_data = b"test_audio_data"

        result = await ha_client.send_audio_chunk(audio_data)

        assert result is False
        ha_client.websocket.send.assert_not_called()

    async def test_send_audio_chunk_exception(self):
        """Test audio chunk sending with exception."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = AsyncMock()
        ha_client.stt_binary_handler_id = 123
        ha_client.websocket.send.side_effect = Exception("Connection error")

        audio_data = b"test_audio_data"

        result = await ha_client.send_audio_chunk(audio_data)

        assert result is False

    async def test_end_audio_success(self):
        """Test successful audio ending."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = AsyncMock()
        ha_client.stt_binary_handler_id = 123

        result = await ha_client.end_audio()

        assert result is True
        ha_client.websocket.send.assert_called_once_with(bytearray([123]))

    async def test_end_audio_no_handler(self):
        """Test audio ending without handler ID."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = AsyncMock()
        ha_client.stt_binary_handler_id = None

        result = await ha_client.end_audio()

        assert result is False
        ha_client.websocket.send.assert_not_called()

    async def test_receive_response_success(self):
        """Test that reception stops at intent-end."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = AsyncMock()

        responses = [
            {"type": "event", "event": {"type": "stt-end", "data": {"stt_output": {"text": "test"}}}},
            {"type": "event", "event": {"type": "intent-end", "data": {"intent_output": {"response": {"speech": {"plain": {"speech": "response"}}}}}}},
            {"type": "event", "event": {"type": "tts-end", "data": {"tts_output": {"url": "/api/tts/test.wav"}}}}
        ]

        ha_client.websocket.recv.side_effect = [json.dumps(resp) for resp in responses]

        results = await ha_client.receive_response()

        assert len(results) == 2
        assert results[0]["event"]["type"] == "stt-end"
        assert results[1]["event"]["type"] == "intent-end"
        assert ha_client.websocket.recv.call_count == 2

    async def test_receive_response_captures_conversation_id(self):
        """Test that the conversation_id from intent-end is stored for the next turn."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = AsyncMock()

        intent_end = {
            "type": "event",
            "event": {
                "type": "intent-end",
                "data": {"intent_output": {"conversation_id": "conv-123", "response": {}}}
            }
        }

        ha_client.websocket.recv.return_value = json.dumps(intent_end)

        await ha_client.receive_response()

        assert ha_client._last_conversation_id == "conv-123"

    async def test_receive_response_timeout(self):
        """Test response receiving with timeout."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = AsyncMock()
        ha_client.websocket.recv.side_effect = asyncio.TimeoutError()

        results = await ha_client.receive_response(timeout_seconds=1)

        assert len(results) == 0

    async def test_receive_response_with_error(self):
        """Test response receiving with error event."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = AsyncMock()

        error_response = {
            "type": "event",
            "event": {"type": "error", "data": {"code": "stt-stream-failed", "message": "STT failed"}}
        }

        ha_client.websocket.recv.return_value = json.dumps(error_response)

        results = await ha_client.receive_response()

        assert len(results) == 1
        assert results[0]["event"]["type"] == "error"

    def test_extract_assistant_response_success(self):
        """Test successful assistant response extraction."""
        ha_client = client.HomeAssistantClient()

        results = [
            {"type": "event", "event": {"type": "intent-end", "data": {"intent_output": {"response": {"speech": {"plain": {"speech": "Hello world"}}}}}}},
            {"type": "event", "event": {"type": "tts-end", "data": {"tts_output": {"url": "/api/tts/test.wav"}}}}
        ]

        response = ha_client.extract_assistant_response(results)

        assert response == "Hello world"

    def test_extract_assistant_response_error_event(self):
        """Test assistant response extraction from an error event."""
        ha_client = client.HomeAssistantClient()

        results = [
            {"type": "event", "event": {"type": "error", "data": {"code": "stt-stream-failed", "message": "STT failed"}}}
        ]

        response = ha_client.extract_assistant_response(results)

        assert response == "Error: stt-stream-failed - STT failed"

    def test_extract_assistant_response_no_speech(self):
        """Test assistant response extraction without speech."""
        ha_client = client.HomeAssistantClient()

        results = [
            {"type": "event", "event": {"type": "stt-end", "data": {"stt_output": {"text": "test"}}}},
            {"type": "event", "event": {"type": "tts-end", "data": {"tts_output": {"url": "/api/tts/test.wav"}}}}
        ]

        response = ha_client.extract_assistant_response(results)

        assert response == "No response from assistant"

    def test_extract_assistant_response_empty_results(self):
        """Test assistant response extraction with empty results."""
        ha_client = client.HomeAssistantClient()

        response = ha_client.extract_assistant_response([])

        assert response == "No response from assistant"

    def test_extract_audio_url_success(self):
        """Test successful audio URL extraction from run-start."""
        ha_client = client.HomeAssistantClient()

        results = [
            RUN_START,
            {"type": "event", "event": {"type": "intent-end", "data": {"intent_output": {"response": {"speech": {"plain": {"speech": "Hello"}}}}}}}
        ]

        url = ha_client.extract_audio_url(results)

        assert url == "/api/tts_proxy/test.wav"

    def test_extract_audio_url_cached_fallback(self):
        """Test audio URL extraction falling back to the URL cached at pipeline start."""
        ha_client = client.HomeAssistantClient()
        ha_client.audio_url = "/api/tts_proxy/cached.wav"

        results = [
            {"type": "event", "event": {"type": "intent-end", "data": {"intent_output": {"response": {"speech": {"plain": {"speech": "Hello"}}}}}}}
        ]

        url = ha_client.extract_audio_url(results)

        assert url == "/api/tts_proxy/cached.wav"

    def test_extract_audio_url_no_url(self):
        """Test audio URL extraction without URL."""
        ha_client = client.HomeAssistantClient()

        results = [
            {"type": "event", "event": {"type": "intent-end", "data": {"intent_output": {"response": {"speech": {"plain": {"speech": "Hello"}}}}}}},
            {"type": "event", "event": {"type": "stt-end", "data": {"stt_output": {"text": "test"}}}}
        ]

        url = ha_client.extract_audio_url(results)

        assert url is None

    async def test_test_connection_success(self):
        """Test successful connection test."""
        ha_client = client.HomeAssistantClient()

        with patch.object(ha_client, 'connect', AsyncMock(return_value=True)), \
             patch.object(ha_client, 'fetch_available_pipelines', AsyncMock()):

            success, message = await ha_client.test_connection()

            assert success is True
            assert "Connection OK" in message

    async def test_test_connection_failure(self):
        """Test connection test failure."""
        ha_client = client.HomeAssistantClient()

        with patch.object(ha_client, 'connect', AsyncMock(return_value=False)):

            success, message = await ha_client.test_connection()

            assert success is False
            assert "Cannot establish connection" in message

    async def test_test_connection_exception(self):
        """Test connection test with exception."""
        ha_client = client.HomeAssistantClient()

        with patch.object(ha_client, 'connect', AsyncMock(side_effect=Exception("Test error"))):

            success, message = await ha_client.test_connection()

            assert success is False
            assert "Test error" in message

    async def test_close_success(self):
        """Test successful client cleanup."""
        ha_client = client.HomeAssistantClient()
        mock_ws = AsyncMock()
        ha_client.websocket = mock_ws
        ha_client.connected = True

        await ha_client.close()

        assert ha_client.connected is False
        mock_ws.close.assert_awaited_once()

    async def test_close_no_websocket(self):
        """Test cleanup without websocket."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = None
        ha_client.connected = True

        await ha_client.close()

        assert ha_client.connected is False

    async def test_close_with_exception(self):
        """Test cleanup with exception."""
        ha_client = client.HomeAssistantClient()
        ha_client.websocket = AsyncMock()
        ha_client.websocket.close.side_effect = Exception("Close error")
        ha_client.connected = True

        await ha_client.close()

        assert ha_client.connected is False
