"""
Enhanced HomeAssistantClient with dynamic pipeline list support
"""
import json
import asyncio
import websockets
import utils

logger = utils.setup_logger()

class HomeAssistantClient:
    """Enhanced Home Assistant client class with pipeline support."""
    
    def __init__(self):
        """Initialize Home Assistant client."""
        self.host = utils.get_env("HA_HOST", "localhost:8123")
        self.token = utils.get_env("HA_TOKEN")
        self.pipeline_id = utils.get_env("HA_PIPELINE_ID")
        self.sample_rate = utils.get_env("HA_SAMPLE_RATE", 16000, int)
        
        if not self.token:
            raise ValueError("Missing access token in .env file (HA_TOKEN)")
        
        self.websocket = None
        self.message_id = 1
        self.stt_binary_handler_id = None
        self.connected = False
        self.audio_url = None
        self.available_pipelines = []
        
    async def connect(self):
        """Establish WebSocket connection with Home Assistant."""
        if self.host.startswith(('localhost', '127.0.0.1', '192.168.', '10.', '172.')):
            protocol = "ws"
        else:
            protocol = "wss"
        uri = f"{protocol}://{self.host}/api/websocket"
        logger.info(f"Connecting to Home Assistant: {uri}")
        
        try:
            self.websocket = await asyncio.wait_for(
                websockets.connect(uri), 
                timeout=15.0
            )
            logger.info("Connection established")
            
            auth_message = await asyncio.wait_for(
                self.websocket.recv(), 
                timeout=15.0
            )
            auth_message = json.loads(auth_message)
            
            if auth_message["type"] != "auth_required":
                logger.error(f"Unexpected message: {auth_message}")
                await self.websocket.close()
                return False
            
            await self.websocket.send(json.dumps({
                "type": "auth",
                "access_token": self.token
            }))
            
            auth_result = await asyncio.wait_for(
                self.websocket.recv(), 
                timeout=15.0
            )
            auth_result = json.loads(auth_result)
            
            if auth_result["type"] != "auth_ok":
                logger.error(f"Authentication failed: {auth_result}")
                await self.websocket.close()
                return False
            
            logger.info("Authentication completed successfully")
            self.connected = True
            
            await self.fetch_available_pipelines()
            
            return True
            
        except asyncio.TimeoutError:
            logger.error("Timeout during connection to Home Assistant")
            return False
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            return False

    async def fetch_available_pipelines(self):
        """Fetch list of available Assist pipelines."""
        self.available_pipelines = []
        
        try:
            logger.info("🔍 Fetching Assist pipelines...")
            
            await self.websocket.send(json.dumps({
                "id": self.message_id,
                "type": "assist_pipeline/pipeline/list"
            }))
            current_msg_id = self.message_id
            self.message_id += 1
            
            while True:
                response = await asyncio.wait_for(
                    self.websocket.recv(), 
                    timeout=15.0
                )
                response_json = json.loads(response)
                
                if (response_json.get("id") == current_msg_id and 
                    response_json.get("type") == "result"):
                    
                    if response_json.get("success"):
                        result = response_json.get("result", {})
                        
                        if isinstance(result, dict) and "pipelines" in result:
                            pipelines_list = result["pipelines"]
                            preferred_id = result.get("preferred_pipeline")
                            
                            logger.info(f"✅ Found {len(pipelines_list)} pipelines")
                            logger.info(f"🏆 Preferred pipeline: {preferred_id}")
                            
                            for pipeline_data in pipelines_list:
                                if isinstance(pipeline_data, dict):
                                    pipeline = {
                                        "id": pipeline_data.get("id", ""),
                                        "name": pipeline_data.get("name", "Unnamed"),
                                        "language": pipeline_data.get("language", "unknown"),
                                        "conversation_engine": pipeline_data.get("conversation_engine", ""),
                                        "stt_engine": pipeline_data.get("stt_engine", ""),
                                        "tts_engine": pipeline_data.get("tts_engine", ""),
                                        "tts_voice": pipeline_data.get("tts_voice", ""),
                                        "is_preferred": pipeline_data.get("id") == preferred_id
                                    }
                                    
                                    self.available_pipelines.append(pipeline)
                                    
                                    preferred_marker = " ⭐ (PREFERRED)" if pipeline["is_preferred"] else ""
                                    logger.info(f"  📋 {pipeline['name']}{preferred_marker}")
                                    logger.info(f"      ID: {pipeline['id']}")
                                    logger.info(f"      Language: {pipeline['language']}")
                                    logger.info(f"      Conversation: {pipeline['conversation_engine']}")
                                    logger.info(f"      STT: {pipeline['stt_engine']}")
                                    logger.info(f"      TTS: {pipeline['tts_engine']} ({pipeline['tts_voice']})")
                            
                            self.preferred_pipeline_id = preferred_id
                            
                            logger.info(f"🏁 LOADED {len(self.available_pipelines)} PIPELINES")
                            return True
                            
                        else:
                            logger.error(f"❌ Unexpected result format: {type(result)}")
                            logger.info(f"Full result: {result}")
                            return False
                    else:
                        error = response_json.get("error", {})
                        logger.error(f"❌ API error: {error}")
                        return False
                        
                elif response_json.get("id") != current_msg_id:
                    continue
                    
        except asyncio.TimeoutError:
            logger.error("❌ Timeout during pipeline fetching")
            return False
        except Exception as e:
            logger.error(f"❌ Pipeline fetching error: {e}")
            return False

    def get_preferred_pipeline_id(self):
        """Return preferred pipeline ID."""
        return getattr(self, 'preferred_pipeline_id', None)

    def get_available_pipelines(self):
        """Return list of available pipelines."""
        return self.available_pipelines
    
    def get_pipeline_by_name(self, name):
        """Find pipeline by name."""
        for pipeline in self.available_pipelines:
            if pipeline.get("name") == name:
                return pipeline
        return None
    
    def validate_pipeline_id(self, pipeline_id):
        """Check if given pipeline ID is available."""
        if not pipeline_id:
            return True  # No ID means use default
            
        for pipeline in self.available_pipelines:
            if pipeline.get("id") == pipeline_id:
                return True
        return False

    async def start_assist_pipeline(self, timeout_seconds=300):
        """Start Assist pipeline from STT to TTS stage with timeout."""
        logger.info("Starting Assist pipeline")
        
        if self.pipeline_id and not self.validate_pipeline_id(self.pipeline_id):
            logger.warning(f"Pipeline ID '{self.pipeline_id}' not available")
            self.pipeline_id = None
        
        pipeline_params = {
            "type": "assist_pipeline/run",
            "start_stage": "stt",
            "end_stage": "tts",
            "input": {
                "sample_rate": self.sample_rate
            },
            "timeout": timeout_seconds
        }
        
        if self.pipeline_id:
            pipeline_params["pipeline"] = self.pipeline_id
            logger.info(f"Using pipeline ID: {self.pipeline_id}")
        else:
            logger.info("Using default pipeline")
            
        await self.websocket.send(json.dumps({
            "id": self.message_id,
            **pipeline_params
        }))
        self.message_id += 1
        
        start_time = asyncio.get_event_loop().time()
        
        while True:
            try:
                response = await asyncio.wait_for(
                    self.websocket.recv(), 
                    timeout=15.0
                )
                response_json = json.loads(response)
                logger.info(f"Received: {response_json}")
                
                if asyncio.get_event_loop().time() - start_time > timeout_seconds:
                    logger.error("Timeout during pipeline startup")
                    return False
                
                if (response_json.get("type") == "event" and 
                    response_json.get("event", {}).get("type") == "run-start"):
                    
                    event_data = response_json.get("event", {}).get("data", {})
                    
                    self.stt_binary_handler_id = event_data.get("runner_data", {}).get("stt_binary_handler_id")
                    logger.info(f"Received stt_binary_handler_id: {self.stt_binary_handler_id}")
                    
                    tts_output = event_data.get("tts_output", {})
                    if tts_output and "url" in tts_output:
                        self.audio_url = tts_output["url"]
                        logger.info(f"Saved audio URL from run-start: {self.audio_url}")
                    
                    if self.stt_binary_handler_id is not None:
                        break
                
                elif (response_json.get("type") == "event" and 
                      response_json.get("event", {}).get("type") == "error"):
                    error_data = response_json.get("event", {}).get("data", {})
                    error_code = error_data.get("code", "unknown")
                    error_message = error_data.get("message", "Unknown error")
                    logger.error(f"Pipeline error: {error_code} - {error_message}")
                    return False
                        
            except asyncio.TimeoutError:
                logger.error("Timeout waiting for pipeline response")
                return False
            except json.JSONDecodeError:
                logger.warning("Received non-JSON message")
                continue
        
        return self.stt_binary_handler_id is not None

    async def send_audio_chunk(self, audio_chunk):
        """Send audio chunk to Home Assistant with error handling."""
        if not self.stt_binary_handler_id:
            logger.error("stt_binary_handler_id not found")
            return False
        
        try:
            prefix = bytearray([self.stt_binary_handler_id])
            await self.websocket.send(prefix + audio_chunk)
            return True
            
        except websockets.exceptions.ConnectionClosed:
            logger.error("Connection closed during audio sending")
            return False
        except Exception as e:
            logger.error(f"Audio sending error: {e}")
            return False
    
    async def end_audio(self):
        """Send end of audio signal with error handling."""
        if not self.stt_binary_handler_id:
            logger.error("stt_binary_handler_id not found")
            return False
        
        try:
            logger.info("Sending end of audio signal")
            await self.websocket.send(bytearray([self.stt_binary_handler_id]))
            return True
            
        except websockets.exceptions.ConnectionClosed:
            logger.error("Connection closed during audio ending")
            return False
        except Exception as e:
            logger.error(f"Audio ending error: {e}")
            return False
    
    async def receive_response(self, timeout_seconds=30):
        """Receive response from Assist with timeout configuration."""
        results = []
        start_time = asyncio.get_event_loop().time()
        
        try:
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout_seconds:
                    logger.warning(f"Timeout ({timeout_seconds}s) during response receiving")
                    break
                
                remaining_time = timeout_seconds - elapsed
                response = await asyncio.wait_for(
                    self.websocket.recv(), 
                    timeout=min(remaining_time, 15.0)
                )
                
                try:
                    response_json = json.loads(response)
                    logger.info(f"Received: {response_json}")
                    results.append(response_json)
                    
                    event_type = response_json.get("event", {}).get("type")
                    
                    if (response_json.get("type") == "event" and 
                        event_type in ["intent-end", "run-end", "error", "tts-end"]):
                        logger.info(f"Ending reception on event: {event_type}")
                        break
                        
                except json.JSONDecodeError:
                    logger.warning(f"Received non-JSON message: {response}")
                    
        except asyncio.TimeoutError:
            logger.warning("Timeout during single message reception")
        except Exception as e:
            logger.error(f"Error during response reception: {e}")
        
        return results
    
    def extract_audio_url(self, results):
        """Extract audio URL from results."""
        if self.audio_url:
            logger.info(f"Using audio URL from run-start: {self.audio_url}")
            return self.audio_url
        
        logger.info("Searching for audio URL in results...")
        
        for result in results:
            if (result.get("type") == "event" and 
                result.get("event", {}).get("type") == "run-start"):
                tts_output = result.get("event", {}).get("data", {}).get("tts_output", {})
                if tts_output and "url" in tts_output:
                    url = tts_output["url"]
                    logger.info(f"Found audio URL in results: {url}")
                    return url
        
        logger.warning("Audio URL not found")
        return None

    def extract_assistant_response(self, results):
        """Extract assistant response from results."""
        for result in results:
            if (result.get("type") == "event" and 
                result.get("event", {}).get("type") == "intent-end"):
                intent_output = result.get("event", {}).get("data", {}).get("intent_output", {})
                response = intent_output.get("response", {}).get("speech", {}).get("plain", "")
                
                if isinstance(response, dict) and 'speech' in response:
                    return response['speech']
                
                return response
        
        for result in results:
            if (result.get("type") == "event" and 
                result.get("event", {}).get("type") == "error"):
                error_code = result.get("event", {}).get("data", {}).get("code", "")
                error_message = result.get("event", {}).get("data", {}).get("message", "")
                return f"Error: {error_code} - {error_message}"
        
        return "No response from assistant"
    
    async def test_connection(self):
        """Test connection without creating pipeline."""
        try:
            if not self.connected:
                success = await self.connect()
                if not success:
                    return False, "Cannot establish connection"
            
            if not self.available_pipelines:
                await self.fetch_available_pipelines()
            
            pipeline_count = len(self.available_pipelines)
            return True, f"Connection OK. Available pipelines: {pipeline_count}"
            
        except Exception as e:
            return False, f"Test error: {str(e)}"
    
    async def close(self):
        """Close connection."""
        self.connected = False
        if self.websocket:
            try:
                await self.websocket.close()
                logger.info("Connection closed")
            except Exception as e:
                logger.error(f"Connection closing error: {e}")