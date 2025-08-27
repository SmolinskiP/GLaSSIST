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
        self.conversation_manager = None
        
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

    def set_conversation_manager(self, conversation_manager):
        """Set conversation manager reference for context cleanup."""
        self.conversation_manager = conversation_manager

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
        
        # Add context to conversation metadata if available
        if hasattr(self, '_conversation_context') and self._conversation_context:
            # Try adding context as conversation metadata
            original_question = getattr(self, '_original_question', 'Unknown question')
            context_info = f"CONTEXT: {self._conversation_context} QUESTION: {original_question}"
            
            pipeline_params["conversation_id"] = context_info[:100]  # Limit length
            logger.info(f"🔖 Adding context as conversation_id: '{context_info[:100]}'")
        
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
                    
                    # Handle conversation context by calling conversation.process directly  
                    if (hasattr(self, '_conversation_context') and self._conversation_context and
                        response_json.get('type') == 'event' and
                        response_json.get('event', {}).get('type') == 'stt-end'):
                        
                        logger.info(f"🔖 DEBUG: Entering conversation context path")
                        
                        stt_text = response_json.get('event', {}).get('data', {}).get('stt_output', {}).get('text', '')
                        if stt_text:
                            logger.info(f"🔖 DETECTED CONTEXT - calling conversation.process")
                            
                            # Extract original question and context
                            original_question = getattr(self, '_original_question', 'Unknown question')
                            context_instructions = self._conversation_context
                            
                            # Build context prompt for direct conversation.process
                            combined_text = f"{context_instructions} User was asked: '{original_question}' and responded: '{stt_text}'. Execute appropriate action and confirm what was done."
                            
                            # Call conversation.process service and get the response
                            try:
                                service_message = {
                                    "id": self.message_id,
                                    "type": "call_service",
                                    "domain": "conversation",
                                    "service": "process",
                                    "service_data": {
                                        "text": combined_text,
                                        "agent_id": "conversation.claude_short_2"
                                    },
                                    "return_response": True
                                }
                                
                                await self.websocket.send(json.dumps(service_message))
                                current_msg_id = self.message_id
                                self.message_id += 1
                                
                                logger.info(f"🔖 CALLED conversation.process with return_response: '{combined_text}'")
                                
                                # Wait for the service response
                                response_text = None
                                timeout_start = asyncio.get_event_loop().time()
                                
                                while asyncio.get_event_loop().time() - timeout_start < 10.0:
                                    try:
                                        service_response = await asyncio.wait_for(
                                            self.websocket.recv(), 
                                            timeout=2.0
                                        )
                                        service_response_json = json.loads(service_response)
                                        
                                        if (service_response_json.get("id") == current_msg_id and 
                                            service_response_json.get("type") == "result"):
                                            
                                            if service_response_json.get("success"):
                                                result = service_response_json.get("result", {})
                                                logger.info(f"🔖 DEBUG conversation.process result: {result}")
                                                
                                                # Try different response paths
                                                response_text = ""
                                                if "speech" in result:
                                                    response_text = result.get("speech", "")
                                                elif "response" in result:
                                                    resp = result.get("response", {})
                                                    if isinstance(resp, dict):
                                                        # Navigate through the nested structure
                                                        inner_resp = resp.get("response", {})
                                                        if isinstance(inner_resp, dict):
                                                            speech_data = inner_resp.get("speech", {})
                                                            if isinstance(speech_data, dict):
                                                                plain_data = speech_data.get("plain", {})
                                                                if isinstance(plain_data, dict):
                                                                    response_text = plain_data.get("speech", "")
                                                        
                                                        if not response_text:
                                                            response_text = str(resp)
                                                    else:
                                                        response_text = str(resp)
                                                else:
                                                    response_text = str(result)
                                                
                                                logger.info(f"🔖 GOT conversation.process response: '{response_text}'")
                                                if response_text:
                                                    break
                                            else:
                                                logger.error(f"conversation.process failed: {service_response_json}")
                                                break
                                                
                                    except asyncio.TimeoutError:
                                        continue
                                    except Exception as e:
                                        logger.error(f"Error waiting for conversation.process response: {e}")
                                        break
                                
                                if response_text:
                                    # Generate TTS for the correct response
                                    tts_pipeline = {
                                        "type": "assist_pipeline/run",
                                        "start_stage": "tts",
                                        "end_stage": "tts", 
                                        "input": {
                                            "text": response_text
                                        }
                                    }
                                    
                                    if hasattr(self, 'pipeline_id') and self.pipeline_id:
                                        tts_pipeline["pipeline"] = self.pipeline_id
                                    
                                    await self.websocket.send(json.dumps({
                                        "id": self.message_id,
                                        **tts_pipeline
                                    }))
                                    self.message_id += 1
                                    
                                    logger.info(f"🔖 GENERATED TTS for correct response: '{response_text}'")
                                    
                                    # Wait for TTS pipeline results and get audio URL
                                    tts_url = None
                                    tts_timeout = asyncio.get_event_loop().time() + 10.0
                                    
                                    while asyncio.get_event_loop().time() < tts_timeout:
                                        try:
                                            tts_response = await asyncio.wait_for(
                                                self.websocket.recv(), 
                                                timeout=2.0
                                            )
                                            tts_response_json = json.loads(tts_response)
                                            
                                            if (tts_response_json.get("type") == "event" and 
                                                tts_response_json.get("event", {}).get("type") == "tts-end"):
                                                tts_output = tts_response_json.get("event", {}).get("data", {}).get("tts_output", {})
                                                tts_url = tts_output.get("url")
                                                if tts_url:
                                                    logger.info(f"🔖 GOT TTS URL: {tts_url}")
                                                    break
                                                    
                                        except asyncio.TimeoutError:
                                            continue
                                        except Exception as e:
                                            logger.error(f"Error getting TTS URL: {e}")
                                            break
                                    
                                    # Play TTS through GLaSSIST
                                    if tts_url:
                                        # Create fake results that GLaSSIST expects
                                        fake_results = [
                                            {
                                                "type": "event",
                                                "event": {
                                                    "type": "run-start",
                                                    "data": {
                                                        "tts_output": {
                                                            "url": tts_url
                                                        }
                                                    }
                                                }
                                            },
                                            {
                                                "type": "event",
                                                "event": {
                                                    "type": "intent-end",
                                                    "data": {
                                                        "intent_output": {
                                                            "response": {
                                                                "speech": {
                                                                    "plain": {
                                                                        "speech": response_text
                                                                    }
                                                                }
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        ]
                                        
                                        # Return fake results instead of continuing with original pipeline
                                        logger.info(f"🔖 RETURNING FAKE RESULTS WITH TTS: {tts_url}")
                                        logger.info(f"🔖 RESPONSE TEXT: {response_text}")
                                        
                                        # Clear context and cancel conversation BEFORE returning
                                        self._conversation_context = None
                                        
                                        # Cancel the conversation in conversation manager
                                        if self.conversation_manager:
                                            logger.info("🔖 Cancelling conversation after response processing")
                                            self.conversation_manager.cancel_conversation()
                                        else:
                                            logger.warning("🔖 No conversation manager available to cancel conversation")
                                        
                                        return fake_results
                                
                            except Exception as e:
                                logger.error(f"Error calling conversation.process with response: {e}")
                                
                                # Clear context even on error
                                self._conversation_context = None
                                if self.conversation_manager:
                                    logger.info("🔖 Cancelling conversation after error")
                                    self.conversation_manager.cancel_conversation()
                            
                            # Skip the original pipeline - we handled it with conversation.process
                            continue
                    
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
        
        # Clear conversation context after normal pipeline completion
        if hasattr(self, '_conversation_context') and self._conversation_context:
            logger.info("🔖 Clearing conversation context after pipeline completion")
            self._conversation_context = None
        
        return results
    
    def extract_audio_url(self, results):
        """Extract audio URL from results."""
        logger.info("Searching for audio URL in results...")
        
        # First check results (including fake results with new TTS URLs)
        for result in results:
            if (result.get("type") == "event" and 
                result.get("event", {}).get("type") == "run-start"):
                tts_output = result.get("event", {}).get("data", {}).get("tts_output", {})
                if tts_output and "url" in tts_output:
                    url = tts_output["url"]
                    logger.info(f"Found audio URL in results: {url}")
                    return url
        
        # Fallback to cached URL if no URL found in results
        if self.audio_url:
            logger.info(f"Using audio URL from run-start: {self.audio_url}")
            return self.audio_url
        
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
    
    async def send_tts_message(self, message):
        """Send TTS message to Home Assistant using service call."""
        try:
            logger.info(f"Sending TTS message: {message}")
            
            # Use call_service to invoke TTS instead of direct TTS engine
            tts_message = {
                "id": self.message_id,
                "type": "call_service",
                "domain": "tts",
                "service": "speak",
                "service_data": {
                    "entity_id": "tts.piper",  # Default TTS engine
                    "message": message
                }
            }
            
            await self.websocket.send(json.dumps(tts_message))
            self.message_id += 1
            
            # Wait for service response
            response = await asyncio.wait_for(
                self.websocket.recv(), 
                timeout=10.0
            )
            
            result = json.loads(response)
            if result.get("success", True):  # Service calls usually succeed without explicit success field
                logger.info("TTS service called successfully")
                return True
            else:
                logger.warning(f"TTS service failed: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending TTS message: {e}")
            return False
    
    async def process_voice_command_with_context(self, audio_data, context):
        """Process voice command with context through HA pipeline."""
        try:
            logger.info(f"Processing voice command with context: {context}")
            
            # Start pipeline with context as prefix
            pipeline_params = {
                "type": "assist_pipeline/run", 
                "start_stage": "stt",
                "end_stage": "intent",
                "input": {
                    "sample_rate": self.sample_rate
                },
                "context": context  # Add context for HA to understand
            }
            
            if self.pipeline_id:
                pipeline_params["pipeline"] = self.pipeline_id
            
            # Send pipeline start message
            await self.websocket.send(json.dumps({
                "id": self.message_id,
                **pipeline_params
            }))
            
            pipeline_id = self.message_id
            self.message_id += 1
            
            # Send audio data
            await self.websocket.send(audio_data)
            
            # End audio stream
            await self.websocket.send(json.dumps({
                "id": self.message_id,
                "type": "assist_pipeline/run",
                "stage": "stt",
                "event": "end"
            }))
            self.message_id += 1
            
            # Wait for pipeline results
            while True:
                response = await asyncio.wait_for(
                    self.websocket.recv(), 
                    timeout=30.0
                )
                
                result = json.loads(response)
                
                # Check if this is our pipeline response
                if result.get("id") == pipeline_id:
                    if result.get("type") == "result":
                        if result.get("success", False):
                            logger.info(f"Pipeline processed successfully: {result}")
                            return {"success": True, "result": result}
                        else:
                            error = result.get("error", {})
                            logger.warning(f"Pipeline failed: {error}")
                            return {"success": False, "error": error}
                    
                    # Handle intermediate events
                    elif result.get("type") == "event":
                        event_type = result.get("event", {}).get("type")
                        if event_type == "intent-end":
                            intent_output = result.get("event", {}).get("data", {})
                            logger.info(f"Intent recognized: {intent_output}")
                            
                            # Check if HA executed an action
                            if intent_output.get("intent", {}).get("name"):
                                return {"success": True, "intent": intent_output}
                        
                        elif event_type in ["error", "run-end"]:
                            break
                
        except Exception as e:
            logger.error(f"Error processing voice command with context: {e}")
            return {"success": False, "error": str(e)}
    
    async def call_service(self, service_call):
        """Call a Home Assistant service."""
        try:
            # Parse service call (e.g., "script.make_coffee" or "light.turn_on")
            if '.' not in service_call:
                logger.error(f"Invalid service call format: {service_call}")
                return False
            
            domain, service = service_call.split('.', 1)
            
            logger.info(f"Calling HA service: {domain}.{service}")
            
            service_message = {
                "id": self.message_id,
                "type": "call_service",
                "domain": domain,
                "service": service,
                "service_data": {}
            }
            
            await self.websocket.send(json.dumps(service_message))
            self.message_id += 1
            
            # Wait for service response
            response = await asyncio.wait_for(
                self.websocket.recv(), 
                timeout=10.0
            )
            
            result = json.loads(response)
            if result.get("success", False):
                logger.info(f"Service {service_call} executed successfully")
                return True
            else:
                logger.warning(f"Service {service_call} failed: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error calling service {service_call}: {e}")
            return False
    
    async def call_service_with_data(self, domain, service, service_data):
        """Call HA service with custom data."""
        try:
            logger.info(f"Calling HA service: {domain}.{service} with data: {service_data}")
            
            service_message = {
                "id": self.message_id,
                "type": "call_service",
                "domain": domain,
                "service": service,
                "service_data": service_data
            }
            
            await self.websocket.send(json.dumps(service_message))
            self.message_id += 1
            
            # Wait for service response
            response = await asyncio.wait_for(
                self.websocket.recv(), 
                timeout=10.0
            )
            
            result = json.loads(response)
            if result.get("success", True):  # Most services succeed
                logger.info(f"Service {domain}.{service} executed successfully")
                return True
            else:
                logger.warning(f"Service {domain}.{service} failed: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error calling service {domain}.{service}: {e}")
            return False