"""
Conversation Manager - handles interactive prompts with context
"""
import asyncio
import json
import threading
import time
import utils

logger = utils.setup_logger()

class ConversationManager:
    """Manages interactive conversations initiated by Home Assistant."""
    
    def __init__(self, ha_client, audio_manager, animation_server):
        self.ha_client = ha_client
        self.audio_manager = audio_manager
        self.animation_server = animation_server
        self.current_conversation = None
        self.conversation_timeout = utils.get_env("HA_CONVERSATION_TIMEOUT", 15, int)
    
    def handle_interactive_prompt(self, prompt_data):
        """Handle interactive prompt from HA (runs in thread)."""
        try:
            # Run the async conversation in a new event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                loop.run_until_complete(self._process_interactive_prompt(prompt_data))
            finally:
                loop.close()
                
        except Exception as e:
            logger.error(f"Error in interactive prompt: {e}")
            # Show error animation
            if self.animation_server:
                self.animation_server.show_error(f"Conversation error: {str(e)}", duration=3.0)
    
    async def _process_interactive_prompt(self, prompt_data):
        """Process interactive prompt by triggering wake word flow with context."""
        message = prompt_data.get('message', 'Hello')
        context = prompt_data.get('context', 'interactive_prompt')
        wait_for_response = prompt_data.get('wait_for_response', True)
        
        # Volume management variables
        saved_volumes = {}
        media_player_entities = []
        target_volume = None
        
        # Load media player configuration
        entities_config = utils.get_env("HA_MEDIA_PLAYER_ENTITIES", "")
        if entities_config:
            media_player_entities = [e.strip() for e in entities_config.split(',') if e.strip()]
            target_volume = utils.get_env("HA_MEDIA_PLAYER_TARGET_VOLUME", 0.3, float)
        
        logger.info(f"📢 HA prompt: '{message}' with context '{context}', wait_for_response: {wait_for_response}")
        print(f"\n>>> HA says: {message}")
        
        # Check if we're already busy
        if self.animation_server.current_state not in ["hidden", "idle"]:
            logger.warning("GLaSSIST busy, ignoring HA prompt")
            return
        
        try:
            # Create fresh HA client to avoid event loop conflicts
            from client import HomeAssistantClient
            temp_ha_client = HomeAssistantClient()
            
            logger.info("Connecting to HA for interactive prompt...")
            if not await temp_ha_client.connect():
                logger.error("Failed to connect to HA")
                return
            
            # Save current volumes and set target volume before TTS
            # Always do this for interactive prompts since we have fresh connection
            if media_player_entities:
                try:
                    logger.info("Saving current volumes and setting target volume for interactive prompt")
                    saved_volumes = await temp_ha_client.get_multiple_volumes(media_player_entities)
                    if saved_volumes:
                        logger.info(f"Saved volumes: {saved_volumes}")
                        self.ha_client.saved_volumes_for_restore = saved_volumes  # Store in original client
                        
                        # Set target volume for all entities
                        target_settings = {entity_id: target_volume for entity_id in media_player_entities}
                        results = await temp_ha_client.set_multiple_volumes(target_settings)
                        logger.info(f"Set target volumes: {results}")
                        self.ha_client.volumes_managed = True  # Mark as managed
                    else:
                        logger.warning("Could not retrieve current volumes")
                except Exception as e:
                    logger.error(f"Error managing volumes: {e}")
            
            # 1. Play TTS through GLaSSIST using dedicated TTS pipeline
            logger.info(f"🔊 Creating separate TTS pipeline for: {message}")
            
            # Use the same temp client for TTS
            tts_client = temp_ha_client
            
            try:
                # Start TTS-only pipeline
                pipeline_params = {
                    "type": "assist_pipeline/run",
                    "start_stage": "tts", 
                    "end_stage": "tts",
                    "input": {
                        "text": message
                    }
                }
                
                if hasattr(tts_client, 'pipeline_id') and tts_client.pipeline_id:
                    pipeline_params["pipeline"] = tts_client.pipeline_id
                
                await tts_client.websocket.send(json.dumps({
                    "id": tts_client.message_id,
                    **pipeline_params
                }))
                tts_client.message_id += 1
                
                # Wait for TTS URL
                tts_url = None
                start_wait = time.time()
                
                while time.time() - start_wait < 10.0:  # 10s timeout for TTS
                    try:
                        response = await asyncio.wait_for(
                            tts_client.websocket.recv(), 
                            timeout=2.0
                        )
                        response_json = json.loads(response)
                        
                        # Look for TTS URL in run-start event
                        if (response_json.get("type") == "event" and 
                            response_json.get("event", {}).get("type") == "run-start"):
                            tts_output = response_json.get("event", {}).get("data", {}).get("tts_output", {})
                            if tts_output and "url" in tts_output:
                                tts_url = tts_output["url"]
                                logger.info(f"🎵 Got TTS URL: {tts_url}")
                                break
                                
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        logger.error(f"Error getting TTS URL: {e}")
                        break
                
                # Play TTS through GLaSSIST audio system
                if tts_url:
                    logger.info("🎵 Playing TTS through GLaSSIST...")
                    tts_success = utils.play_audio_from_url(
                        tts_url, 
                        tts_client.host, 
                        self.animation_server
                    )
                    if tts_success:
                        logger.info("✅ TTS played successfully through GLaSSIST")
                    else:
                        logger.warning("❌ TTS playback failed")
                else:
                    logger.warning("❌ Could not get TTS URL from HA")
                    
            finally:
                # Close temp client
                await temp_ha_client.close()
            
            # 2. Store context and original question for voice command
            self.ha_client._conversation_context = context
            self.ha_client._original_question = message
            logger.info(f"🔖 Context stored: '{context}'")
            logger.info(f"🔖 Original question stored: '{message}'")
            
            # 3. Start listening for user response - only if wait_for_response is True
            if wait_for_response:
                if hasattr(self, '_app_instance') and self._app_instance:
                    logger.info("🎯 Now listening for user response...")
                    self._app_instance.on_voice_command_trigger()
                else:
                    logger.error("App instance not available")
            else:
                logger.info("🔇 TTS-only mode: not waiting for user response")
                # Just show animation briefly then hide
                if hasattr(self, '_app_instance') and self._app_instance.animation_server:
                    self._app_instance.animation_server.change_state("responding")
                    await asyncio.sleep(2)  # Brief display
                    self._app_instance.animation_server.change_state("hidden")
                
        except Exception as e:
            logger.error(f"Error triggering voice command: {e}")
            
            # If error occurred, we need to restore volumes since main process won't run
            if (media_player_entities and hasattr(self.ha_client, 'saved_volumes_for_restore') and 
                self.ha_client.saved_volumes_for_restore and self.ha_client.volumes_managed):
                try:
                    logger.info("Restoring volumes after conversation error")
                    results = await self.ha_client.set_multiple_volumes(self.ha_client.saved_volumes_for_restore)
                    logger.info(f"Restored volumes: {results}")
                    self.ha_client.volumes_managed = False
                    self.ha_client.saved_volumes_for_restore = None
                except Exception as restore_error:
                    logger.error(f"Error restoring volumes after conversation error: {restore_error}")
                    self.ha_client.volumes_managed = False
                    self.ha_client.saved_volumes_for_restore = None
            
            # Clean up temp client
            try:
                await temp_ha_client.close()
            except:
                pass
        finally:
            # For TTS-only mode (wait_for_response=false), restore volumes here using temp client
            # For normal mode, main process_voice_command will handle volume restore
            if (not wait_for_response and media_player_entities and 
                hasattr(self.ha_client, 'saved_volumes_for_restore') and 
                self.ha_client.saved_volumes_for_restore and self.ha_client.volumes_managed):
                try:
                    logger.info("Restoring volumes after TTS-only prompt")
                    # Create another temp client for restore to avoid event loop conflicts
                    from client import HomeAssistantClient
                    restore_client = HomeAssistantClient()
                    await restore_client.connect()
                    
                    results = await restore_client.set_multiple_volumes(self.ha_client.saved_volumes_for_restore)
                    logger.info(f"Restored volumes: {results}")
                    self.ha_client.volumes_managed = False
                    self.ha_client.saved_volumes_for_restore = None
                    
                    await restore_client.close()
                except Exception as restore_error:
                    logger.error(f"Error restoring volumes after TTS-only prompt: {restore_error}")
                    self.ha_client.volumes_managed = False
                    self.ha_client.saved_volumes_for_restore = None
            else:
                logger.info("Interactive prompt setup completed, main process will handle volume restore (if needed)")
            
            # Clean up temp client if still alive  
            try:
                if 'temp_ha_client' in locals():
                    await temp_ha_client.close()
            except:
                pass
    
    async def _listen_for_response_with_timeout(self, timeout):
        """Listen for audio response with timeout."""
        try:
            # Use audio manager to capture response
            # This will need to be adapted based on your AudioManager implementation
            start_time = time.time()
            
            logger.info("Starting audio capture for conversation response")
            
            # Start recording with adjusted settings for conversation
            audio_data = await self.audio_manager.record_audio_async(
                timeout=timeout,
                silence_threshold=1.5,  # Much longer silence needed (1.5s)
                min_audio_length=0.8    # At least 0.8s of speech
            )
            logger.info(f"Audio recording completed, received: {len(audio_data) if audio_data else 0} bytes")
            
            if audio_data and len(audio_data) > 0:
                duration = time.time() - start_time
                logger.info(f"Captured {len(audio_data)} bytes of audio in {duration:.1f}s")
                return audio_data
            else:
                logger.warning("No audio captured or audio too short")
                return None
                
        except Exception as e:
            logger.error(f"Error capturing audio response: {e}")
            return None
    
    async def _process_response_with_context(self, audio_data, context):
        """Process audio response with context through HA pipeline."""
        try:
            logger.info(f"Sending audio to HA with context: {context}")
            
            # Send audio to HA pipeline with context prepended
            # The HA pipeline will receive context + user_response and interpret it
            result = await self.ha_client.process_voice_command_with_context(
                audio_data, 
                context
            )
            
            if result and result.get('success'):
                logger.info(f"HA processed command successfully: {result}")
                return True
            else:
                logger.warning(f"HA could not process command: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing response with HA: {e}")
            return False
    
    def is_in_conversation(self):
        """Check if currently in an interactive conversation."""
        return self.current_conversation is not None
    
    def get_conversation_info(self):
        """Get current conversation information."""
        if not self.current_conversation:
            return None
        
        elapsed = time.time() - self.current_conversation['start_time']
        remaining = max(0, self.current_conversation['timeout'] - elapsed)
        
        return {
            'context': self.current_conversation['context'],
            'message': self.current_conversation['message'], 
            'elapsed_time': elapsed,
            'remaining_time': remaining
        }
    
    def cancel_conversation(self):
        """Cancel current conversation."""
        if self.current_conversation:
            logger.info("Cancelling current conversation")
            self.current_conversation = None
            # Clear conversation context in HA client
            if hasattr(self.ha_client, '_conversation_context'):
                logger.info("🔖 Clearing conversation context on cancellation")
                self.ha_client._conversation_context = None
            self.animation_server.change_state("hidden")
            return True
        return False