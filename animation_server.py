"""
Serwer WebSocket do komunikacji z animacją Three.js.
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
    """Serwer WebSocket do komunikacji z animacją."""
    
    def __init__(self, port: int = 8765):
        """Inicjalizacja serwera animacji."""
        self.port = port
        self.clients: set = set()
        self.server = None
        self.loop = None
        self.thread = None
        self.current_state = "hidden"  # ZMIANA: zamiast 'idle' -> 'hidden'
        self.audio_data_buffer = []
        
    def start(self):
        """Uruchomienie serwera w osobnym wątku."""
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()
        logger.info(f"Animation server startuje na porcie {self.port}")
    
    def _run_server(self):
        """Uruchomienie asyncio event loop w wątku."""
        # Utworzenie nowego event loop dla tego wątku
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            # Uruchomienie serwera asynchronicznie
            self.loop.run_until_complete(self._start_websocket_server())
            logger.info(f"Animation server działa na ws://localhost:{self.port}")
            
            # Uruchomienie event loop
            self.loop.run_forever()
        except Exception as e:
            logger.exception(f"Błąd serwera animacji: {e}")
        finally:
            self.loop.close()
    
    async def _start_websocket_server(self):
        """Uruchomienie WebSocket serwera."""
        self.server = await websockets.serve(
            self._handle_client, 
            "localhost", 
            self.port,
            ping_interval=None,
            ping_timeout=None
        )
    
    async def _handle_client(self, websocket):
        """Obsługa połączenia klienta WebSocket."""
        logger.info(f"Nowy klient animacji połączony: {websocket.remote_address}")
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
                    logger.warning(f"Nieprawidłowa wiadomość JSON: {message}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info("Klient animacji rozłączony")
        except Exception as e:
            logger.exception(f"Błąd obsługi klienta animacji: {e}")
        finally:
            self.clients.discard(websocket)
    
    async def _handle_message(self, websocket, data: Dict):
        """Obsługa wiadomości od klienta."""
        msg_type = data.get("type")
        
        if msg_type == "ping":
            await self._send_to_client(websocket, {"type": "pong"})
        elif msg_type == "ready":
            logger.info("Klient animacji gotowy")
        elif msg_type == "activate_voice_command":
            # TYLKO JEŚLI STAN TO 'hidden' - inaczej aplikacja jest zajęta
            if self.current_state == "hidden":
                logger.info("Otrzymano żądanie aktywacji komendy głosowej z frontendu")
                if hasattr(self, 'voice_command_callback') and self.voice_command_callback:
                    self.voice_command_callback()
            else:
                logger.info(f"Ignoruję aktywację - aplikacja w stanie: {self.current_state}")
        else:
            logger.warning(f"Nieznany typ wiadomości: {msg_type}")
    
    def set_voice_command_callback(self, callback):
        """Ustawienie callback'a dla aktywacji komendy głosowej."""
        self.voice_command_callback = callback
    
    async def _send_to_client(self, client, data: Dict):
        """Wysłanie danych do konkretnego klienta."""
        try:
            await client.send(json.dumps(data))
        except Exception as e:
            logger.error(f"Błąd wysyłania do klienta: {e}")
    
    async def _broadcast(self, data: Dict):
        """Wysłanie danych do wszystkich klientów."""
        if not self.clients:
            return
            
        # Usuń klientów, którzy się rozłączyli
        disconnected = set()
        
        for client in self.clients.copy():
            try:
                await self._send_to_client(client, data)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)
            except Exception as e:
                logger.error(f"Błąd broadcast do klienta: {e}")
                disconnected.add(client)
        
        # Usuń rozłączonych klientów
        self.clients -= disconnected
    
    def _safe_broadcast(self, data: Dict):
        """Thread-safe broadcast - wywołanie z głównego wątku."""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._broadcast(data), self.loop)
    
    def change_state(self, new_state: str, **kwargs):
        """Zmiana stanu animacji."""
        if new_state == self.current_state:
            return
            
        logger.info(f"Zmiana stanu animacji: {self.current_state} -> {new_state}")
        self.current_state = new_state
        
        message = {
            "type": "state_change",
            "state": new_state,
            "timestamp": utils.get_timestamp(),
            **kwargs
        }
        
        self._safe_broadcast(message)
    
    def send_audio_data(self, audio_chunk: bytes, sample_rate: int = 16000):
        """Wysłanie danych audio do analizy FFT."""
        try:
            # Konwersja do numpy array
            audio_array = np.frombuffer(audio_chunk, dtype=np.int16)
            
            # FFT analysis
            fft = np.fft.fft(audio_array)
            fft_mag = np.abs(fft)
            
            # Weź tylko pierwszą połowę (rzeczywiste częstotliwości)
            fft_mag = fft_mag[:len(fft_mag)//2]
            
            # Normalizacja i uproszczenie do 32 binów dla wydajności
            if len(fft_mag) > 32:
                # Pogrupuj częstotliwości w 32 biny
                bins = np.array_split(fft_mag, 32)
                fft_simplified = [float(np.mean(bin_data)) for bin_data in bins]
            else:
                fft_simplified = fft_mag.tolist()
            
            # Normalizacja do zakresu 0-1
            max_val = max(fft_simplified) if fft_simplified else 1
            if max_val > 0:
                fft_normalized = [val / max_val for val in fft_simplified]
            else:
                fft_normalized = fft_simplified
            
            # Wyślij dane
            message = {
                "type": "audio_data",
                "fft": fft_normalized,
                "timestamp": utils.get_timestamp()
            }
            
            self._safe_broadcast(message)
            
        except Exception as e:
            logger.error(f"Błąd przetwarzania audio FFT: {e}")
    
    def send_response_text(self, text: str):
        """Wysłanie tekstu odpowiedzi do wyświetlenia."""
        message = {
            "type": "response_text",
            "text": text,
            "timestamp": utils.get_timestamp()
        }
        
        self._safe_broadcast(message)
    
    def stop(self):
        """Zatrzymanie serwera."""
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        
        logger.info("Animation server zatrzymany")