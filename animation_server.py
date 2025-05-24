"""
WebSocket server for communication with Three.js animation.
"""
import asyncio
import json
import threading
import websockets
import numpy as np
from typing import Dict, List, Optional
import utils

logger = utils.setup_logger()

class AnimationServer:
    def __init__(self, port: int = 8765):
        self.port = port
        self.clients: set = set()
        self.server = None
        self.loop = None
        self.thread = None
        self.current_state = "hidden"  # CHANGED: 'idle' -> 'hidden'
        self.audio_data_buffer = []
        
    def start(self):
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()
        logger.info(f"Animation server starting on port {self.port}")
    
    def _run_server(self):
        # Create new event loop for this thread
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            # Start server asynchronously
            self.loop.run_until_complete(self._start_websocket_server())
            logger.info(f"Animation server running at ws://localhost:{self.port}")
            
            # Run event loop
            self.loop.run_forever()
        except Exception as e:
            logger.exception(f"Animation server error: {e}")
        finally:
            self.loop.close()
    
    async def _start_websocket_server(self):
        self.server = await websockets.serve(
            self._handle_client, 
            "localhost", 
            self.port,
            ping_interval=None,
            ping_timeout=None
        )
    
    async def _handle_client(self, websocket):
        logger.info(f"New animation client connected: {websocket.remote_address}")
        self.clients.add(websocket)
        
        try:
            await self._send_to_client(websocket, {
                "type": "state_change",
                "state": self.current_state
            })
            
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self._handle_message(websocket, data)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON message: {message}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info("Animation client disconnected")
        except Exception as e:
            logger.exception(f"Error handling animation client: {e}")
        finally:
            self.clients.discard(websocket)
    
    async def _handle_message(self, websocket, data: Dict):
        msg_type = data.get("type")
        
        if msg_type == "ping":
            await self._send_to_client(websocket, {"type": "pong"})
        elif msg_type == "ready":
            logger.info("Animation client ready")
        elif msg_type == "activate_voice_command":
            # ONLY IF STATE IS 'hidden' - otherwise app is busy
            if self.current_state == "hidden":
                logger.info("Received voice command activation request from frontend")
                if hasattr(self, 'voice_command_callback') and self.voice_command_callback:
                    self.voice_command_callback()
            else:
                logger.info(f"Ignoring activation - app is in state: {self.current_state}")
        else:
            logger.warning(f"Unknown message type: {msg_type}")
    
    def set_voice_command_callback(self, callback):
        self.voice_command_callback = callback
    
    async def _send_to_client(self, client, data: Dict):
        try:
            await client.send(json.dumps(data))
        except Exception as e:
            logger.error(f"Error sending to client: {e}")
    
    async def _broadcast(self, data: Dict):
        if not self.clients:
            return
            
        # Remove disconnected clients
        disconnected = set()
        
        for client in self.clients.copy():
            try:
                await self._send_to_client(client, data)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)
            except Exception as e:
                logger.error(f"Broadcast error to client: {e}")
                disconnected.add(client)
        
        # Remove disconnected clients
        self.clients -= disconnected
    
    def _safe_broadcast(self, data: Dict):
        """Thread-safe broadcast - call from main thread"""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._broadcast(data), self.loop)
    
    def change_state(self, new_state: str, error_message: str = None, success_message: str = None, **kwargs):
            if new_state == self.current_state and not error_message and not success_message:
                return
                
            logger.info(f"Animation state change: {self.current_state} -> {new_state}")
            if error_message:
                logger.info(f"Error message: {error_message}")
            if success_message:
                logger.info(f"Success message: {success_message}")
            
            self.current_state = new_state
            
            message = {
                "type": "state_change",
                "state": new_state,
                "timestamp": utils.get_timestamp(),
                **kwargs
            }
            
            # Add error message if available
            if error_message:
                message["errorMessage"] = error_message
                
            # NOWY: Add success message if available
            if success_message:
                message["successMessage"] = success_message
            
            self._safe_broadcast(message)
    
    def show_success(self, message: str = "Success", duration: float = 3.0):
        """Pokaż animację sukcesu na określony czas."""
        self.change_state("success", success_message=message)
        
        # Zaplanuj powrót do hidden po określonym czasie
        import threading
        import time
        
        def hide_after_delay():
            time.sleep(duration)
            if self.current_state == "success":  # Tylko jeśli nadal jesteśmy w stanie success
                self.change_state("hidden")
        
        threading.Thread(target=hide_after_delay, daemon=True).start()
    
    def show_error(self, message: str = "Error", duration: float = 5.0):
        """Pokaż animację błędu na określony czas."""
        self.change_state("error", error_message=message)
        
        # Zaplanuj powrót do hidden po określonym czasie
        import threading
        import time
        
        def hide_after_delay():
            time.sleep(duration)
            if self.current_state == "error":  # Tylko jeśli nadal jesteśmy w stanie error
                self.change_state("hidden")
        
        threading.Thread(target=hide_after_delay, daemon=True).start()
    
    def send_audio_data(self, audio_chunk: bytes, sample_rate: int = 16000):
        try:
            # Convert to numpy array
            audio_array = np.frombuffer(audio_chunk, dtype=np.int16)
            
            # FFT analysis
            fft = np.fft.fft(audio_array)
            fft_mag = np.abs(fft)
            
            # Take only the first half (real frequencies)
            fft_mag = fft_mag[:len(fft_mag)//2]
            
            # Normalize and simplify to 32 bins for performance
            if len(fft_mag) > 32:
                # Group frequencies into 32 bins
                bins = np.array_split(fft_mag, 32)
                fft_simplified = [float(np.mean(bin_data)) for bin_data in bins]
            else:
                fft_simplified = fft_mag.tolist()
            
            # Normalize to 0-1 range
            max_val = max(fft_simplified) if fft_simplified else 1
            if max_val > 0:
                fft_normalized = [val / max_val for val in fft_simplified]
            else:
                fft_normalized = fft_simplified
            
            # Send data
            message = {
                "type": "audio_data",
                "fft": fft_normalized,
                "timestamp": utils.get_timestamp()
            }
            
            self._safe_broadcast(message)
            
        except Exception as e:
            logger.error(f"Error processing audio FFT: {e}")
    
    def send_response_text(self, text: str):
        message = {
            "type": "response_text",
            "text": text,
            "timestamp": utils.get_timestamp()
        }
        
        self._safe_broadcast(message)
    
    def stop(self):
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        
        logger.info("Animation server stopped")