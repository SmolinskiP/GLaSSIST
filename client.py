"""
Ulepszona wersja HomeAssistantClient z obsługą dynamicznej listy pipeline'ów
"""
import json
import asyncio
import websockets
import utils

logger = utils.setup_logger()

class HomeAssistantClient:
    """Ulepszona klasa klienta Home Assistant z obsługą pipeline'ów."""
    
    def __init__(self):
        """Inicjalizacja klienta Home Assistant."""
        self.host = utils.get_env("HA_HOST", "localhost:8123")
        self.token = utils.get_env("HA_TOKEN")
        self.pipeline_id = utils.get_env("HA_PIPELINE_ID")
        self.sample_rate = utils.get_env("HA_SAMPLE_RATE", 16000, int)
        
        # Sprawdzenie czy token istnieje
        if not self.token:
            raise ValueError("Brak tokena dostępu w pliku .env (HA_TOKEN)")
        
        self.websocket = None
        self.message_id = 1
        self.stt_binary_handler_id = None
        self.connected = False
        self.audio_url = None
        self.available_pipelines = []
        
    async def connect(self):
        """Nawiązanie połączenia WebSocket z Home Assistant."""
        if self.host.startswith(('localhost', '127.0.0.1', '192.168.', '10.', '172.')):
            protocol = "ws"
        else:
            protocol = "wss"
        uri = f"{protocol}://{self.host}/api/websocket"
        logger.info(f"Łączenie z Home Assistant: {uri}")
        
        try:
            self.websocket = await asyncio.wait_for(
                websockets.connect(uri), 
                timeout=10.0
            )
            logger.info("Połączenie ustanowione")
            
            # Oczekiwanie na wiadomość auth_required
            auth_message = await asyncio.wait_for(
                self.websocket.recv(), 
                timeout=5.0
            )
            auth_message = json.loads(auth_message)
            
            if auth_message["type"] != "auth_required":
                logger.error(f"Nieoczekiwana wiadomość: {auth_message}")
                await self.websocket.close()
                return False
            
            # Wysłanie tokena uwierzytelniającego
            await self.websocket.send(json.dumps({
                "type": "auth",
                "access_token": self.token
            }))
            
            # Oczekiwanie na wiadomość auth_ok
            auth_result = await asyncio.wait_for(
                self.websocket.recv(), 
                timeout=5.0
            )
            auth_result = json.loads(auth_result)
            
            if auth_result["type"] != "auth_ok":
                logger.error(f"Uwierzytelnianie nie powiodło się: {auth_result}")
                await self.websocket.close()
                return False
            
            logger.info("Uwierzytelnianie zakończone sukcesem")
            self.connected = True
            
            # NOWOŚĆ: Po połączeniu, pobierz listę dostępnych pipeline'ów
            await self.fetch_available_pipelines()
            
            return True
            
        except asyncio.TimeoutError:
            logger.error("Timeout podczas łączenia z Home Assistant")
            return False
        except Exception as e:
            logger.error(f"Błąd połączenia: {str(e)}")
            return False

    async def fetch_available_pipelines(self):
        """Pobiera listę dostępnych pipeline'ów Assist - NAPRAWIONA WERSJA."""
        self.available_pipelines = []
        
        try:
            logger.info("🔍 Pobieranie pipeline'ów Assist...")
            
            # Wyślij żądanie listy pipeline'ów
            await self.websocket.send(json.dumps({
                "id": self.message_id,
                "type": "assist_pipeline/pipeline/list"
            }))
            current_msg_id = self.message_id
            self.message_id += 1
            
            # Czekaj na odpowiedź
            while True:
                response = await asyncio.wait_for(
                    self.websocket.recv(), 
                    timeout=5.0
                )
                response_json = json.loads(response)
                
                # Sprawdź czy to odpowiedź na nasze żądanie
                if (response_json.get("id") == current_msg_id and 
                    response_json.get("type") == "result"):
                    
                    if response_json.get("success"):
                        result = response_json.get("result", {})
                        
                        # NAPRAWIONE: Wyciągnij pipeline'y ze słownika
                        if isinstance(result, dict) and "pipelines" in result:
                            pipelines_list = result["pipelines"]
                            preferred_id = result.get("preferred_pipeline")
                            
                            logger.info(f"✅ Znaleziono {len(pipelines_list)} pipeline'ów")
                            logger.info(f"🏆 Preferowany pipeline: {preferred_id}")
                            
                            # Przetwórz każdy pipeline
                            for pipeline_data in pipelines_list:
                                if isinstance(pipeline_data, dict):
                                    pipeline = {
                                        "id": pipeline_data.get("id", ""),
                                        "name": pipeline_data.get("name", "Bez nazwy"),
                                        "language": pipeline_data.get("language", "nieznany"),
                                        "conversation_engine": pipeline_data.get("conversation_engine", ""),
                                        "stt_engine": pipeline_data.get("stt_engine", ""),
                                        "tts_engine": pipeline_data.get("tts_engine", ""),
                                        "tts_voice": pipeline_data.get("tts_voice", ""),
                                        "is_preferred": pipeline_data.get("id") == preferred_id
                                    }
                                    
                                    self.available_pipelines.append(pipeline)
                                    
                                    # Dodatkowe info dla preferred
                                    preferred_marker = " ⭐ (PREFEROWANY)" if pipeline["is_preferred"] else ""
                                    logger.info(f"  📋 {pipeline['name']}{preferred_marker}")
                                    logger.info(f"      ID: {pipeline['id']}")
                                    logger.info(f"      Język: {pipeline['language']}")
                                    logger.info(f"      Conversation: {pipeline['conversation_engine']}")
                                    logger.info(f"      STT: {pipeline['stt_engine']}")
                                    logger.info(f"      TTS: {pipeline['tts_engine']} ({pipeline['tts_voice']})")
                            
                            # Zapisz preferred pipeline ID dla łatwego dostępu
                            self.preferred_pipeline_id = preferred_id
                            
                            logger.info(f"🏁 ZAŁADOWANO {len(self.available_pipelines)} PIPELINE'ÓW")
                            return True
                            
                        else:
                            logger.error(f"❌ Nieoczekiwany format wyniku: {type(result)}")
                            logger.info(f"Pełny wynik: {result}")
                            return False
                    else:
                        error = response_json.get("error", {})
                        logger.error(f"❌ Błąd API: {error}")
                        return False
                        
                # Jeśli to nie nasza odpowiedź, kontynuuj oczekiwanie
                elif response_json.get("id") != current_msg_id:
                    continue
                    
        except asyncio.TimeoutError:
            logger.error("❌ Timeout podczas pobierania pipeline'ów")
            return False
        except Exception as e:
            logger.error(f"❌ Błąd pobierania pipeline'ów: {e}")
            return False

    def get_preferred_pipeline_id(self):
        """Zwraca ID preferowanego pipeline'u."""
        return getattr(self, 'preferred_pipeline_id', None)

    def get_available_pipelines(self):
        """Zwraca listę dostępnych pipeline'ów."""
        return self.available_pipelines
    
    def get_pipeline_by_name(self, name):
        """Znajduje pipeline po nazwie."""
        for pipeline in self.available_pipelines:
            if pipeline.get("name") == name:
                return pipeline
        return None
    
    def validate_pipeline_id(self, pipeline_id):
        """Sprawdza czy podane ID pipeline'u jest dostępne."""
        if not pipeline_id:
            return True  # Brak ID oznacza użycie domyślnego
            
        for pipeline in self.available_pipelines:
            if pipeline.get("id") == pipeline_id:
                return True
        return False

    async def start_assist_pipeline(self, timeout_seconds=300):
        """Uruchomienie pipeline Assist od etapu STT do TTS z timeout."""
        logger.info("Uruchamiam pipeline Assist")
        
        # Sprawdź czy podany pipeline_id jest dostępny
        if self.pipeline_id and not self.validate_pipeline_id(self.pipeline_id):
            logger.warning(f"Pipeline ID '{self.pipeline_id}' nie jest dostępny")
            # Wyczyść nieprawidłowy ID - użyj domyślnego
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
            logger.info(f"Używam pipeline ID: {self.pipeline_id}")
        else:
            logger.info("Używam domyślnego pipeline'u")
            
        await self.websocket.send(json.dumps({
            "id": self.message_id,
            **pipeline_params
        }))
        self.message_id += 1
        
        # Oczekiwanie na wiadomości z serwera i szukanie binary_handler_id
        start_time = asyncio.get_event_loop().time()
        
        while True:
            try:
                response = await asyncio.wait_for(
                    self.websocket.recv(), 
                    timeout=10.0
                )
                response_json = json.loads(response)
                logger.info(f"Otrzymano: {response_json}")
                
                # Sprawdź timeout
                if asyncio.get_event_loop().time() - start_time > timeout_seconds:
                    logger.error("Timeout podczas uruchamiania pipeline")
                    return False
                
                # Szukamy wydarzenia run-start
                if (response_json.get("type") == "event" and 
                    response_json.get("event", {}).get("type") == "run-start"):
                    
                    event_data = response_json.get("event", {}).get("data", {})
                    
                    # Pobierz stt_binary_handler_id
                    self.stt_binary_handler_id = event_data.get("runner_data", {}).get("stt_binary_handler_id")
                    logger.info(f"Otrzymano stt_binary_handler_id: {self.stt_binary_handler_id}")
                    
                    # Pobierz URL audio z TTS_OUTPUT
                    tts_output = event_data.get("tts_output", {})
                    if tts_output and "url" in tts_output:
                        self.audio_url = tts_output["url"]
                        logger.info(f"Zapisano URL audio z run-start: {self.audio_url}")
                    
                    if self.stt_binary_handler_id is not None:
                        break
                
                # Sprawdź czy nie ma błędu
                elif (response_json.get("type") == "event" and 
                      response_json.get("event", {}).get("type") == "error"):
                    error_data = response_json.get("event", {}).get("data", {})
                    error_code = error_data.get("code", "unknown")
                    error_message = error_data.get("message", "Nieznany błąd")
                    logger.error(f"Błąd pipeline: {error_code} - {error_message}")
                    return False
                        
            except asyncio.TimeoutError:
                logger.error("Timeout podczas oczekiwania na odpowiedź pipeline")
                return False
            except json.JSONDecodeError:
                logger.warning("Otrzymano wiadomość, która nie jest JSON")
                continue
        
        return self.stt_binary_handler_id is not None

    async def send_audio_chunk(self, audio_chunk):
        """Wysyłanie fragmentu audio do Home Assistant z obsługą błędów."""
        if not self.stt_binary_handler_id:
            logger.error("Nie znaleziono stt_binary_handler_id")
            return False
        
        try:
            # Prefiks z stt_binary_handler_id
            prefix = bytearray([self.stt_binary_handler_id])
            
            # Wysłanie danych audio
            await self.websocket.send(prefix + audio_chunk)
            return True
            
        except websockets.exceptions.ConnectionClosed:
            logger.error("Połączenie zostało zamknięte podczas wysyłania audio")
            return False
        except Exception as e:
            logger.error(f"Błąd wysyłania audio: {e}")
            return False
    
    async def end_audio(self):
        """Wysłanie sygnału końca audio z obsługą błędów."""
        if not self.stt_binary_handler_id:
            logger.error("Nie znaleziono stt_binary_handler_id")
            return False
        
        try:
            # Wysłanie komunikatu kończącego audio
            logger.info("Wysyłam sygnał końca audio")
            await self.websocket.send(bytearray([self.stt_binary_handler_id]))
            return True
            
        except websockets.exceptions.ConnectionClosed:
            logger.error("Połączenie zostało zamknięte podczas kończenia audio")
            return False
        except Exception as e:
            logger.error(f"Błąd kończenia audio: {e}")
            return False
    
    async def receive_response(self, timeout_seconds=30):
        """Odbiór odpowiedzi z Assist z konfiguracją timeout."""
        results = []
        start_time = asyncio.get_event_loop().time()
        
        try:
            while True:
                # Sprawdź timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout_seconds:
                    logger.warning(f"Timeout ({timeout_seconds}s) podczas odbierania odpowiedzi")
                    break
                
                remaining_time = timeout_seconds - elapsed
                response = await asyncio.wait_for(
                    self.websocket.recv(), 
                    timeout=min(remaining_time, 5.0)
                )
                
                try:
                    response_json = json.loads(response)
                    logger.info(f"Otrzymano: {response_json}")
                    results.append(response_json)
                    
                    # Kończymy pętlę na różnych eventach
                    event_type = response_json.get("event", {}).get("type")
                    
                    if (response_json.get("type") == "event" and 
                        event_type in ["intent-end", "run-end", "error", "tts-end"]):
                        logger.info(f"Kończę odbiór na wydarzeniu: {event_type}")
                        break
                        
                except json.JSONDecodeError:
                    logger.warning(f"Otrzymano wiadomość nie-JSON: {response}")
                    
        except asyncio.TimeoutError:
            logger.warning("Timeout podczas odbierania pojedynczej wiadomości")
        except Exception as e:
            logger.error(f"Błąd podczas odbierania odpowiedzi: {e}")
        
        return results
    
    def extract_audio_url(self, results):
        """Wydobycie URL audio z wyników."""
        # Najpierw sprawdź czy mamy URL z run-start (zapisany wcześniej)
        if self.audio_url:
            logger.info(f"Używam URL audio z run-start: {self.audio_url}")
            return self.audio_url
        
        # Backup - sprawdź w wynikach (dla kompatybilności)
        logger.info("Szukam URL audio w wynikach...")
        
        for result in results:
            if (result.get("type") == "event" and 
                result.get("event", {}).get("type") == "run-start"):
                tts_output = result.get("event", {}).get("data", {}).get("tts_output", {})
                if tts_output and "url" in tts_output:
                    url = tts_output["url"]
                    logger.info(f"Znaleziono URL audio w wynikach: {url}")
                    return url
        
        logger.warning("Nie znaleziono URL audio")
        return None

    def extract_assistant_response(self, results):
        """Wydobycie odpowiedzi asystenta z wyników."""
        # Szukamy odpowiedzi w intent-end
        for result in results:
            if (result.get("type") == "event" and 
                result.get("event", {}).get("type") == "intent-end"):
                intent_output = result.get("event", {}).get("data", {}).get("intent_output", {})
                response = intent_output.get("response", {}).get("speech", {}).get("plain", "")
                
                # Jeśli odpowiedź jest obiektem z polem 'speech', to wyodrębnij samo speech
                if isinstance(response, dict) and 'speech' in response:
                    return response['speech']
                
                return response
        
        # Jeśli nie znaleźliśmy odpowiedzi, sprawdzamy czy wystąpił błąd
        for result in results:
            if (result.get("type") == "event" and 
                result.get("event", {}).get("type") == "error"):
                error_code = result.get("event", {}).get("data", {}).get("code", "")
                error_message = result.get("event", {}).get("data", {}).get("message", "")
                return f"Błąd: {error_code} - {error_message}"
        
        return "Brak odpowiedzi od asystenta"
    
    async def test_connection(self):
        """Test połączenia bez tworzenia pipeline'u."""
        try:
            if not self.connected:
                success = await self.connect()
                if not success:
                    return False, "Nie można nawiązać połączenia"
            
            # Jeśli połączenie udane, sprawdź pipeline'y
            if not self.available_pipelines:
                await self.fetch_available_pipelines()
            
            pipeline_count = len(self.available_pipelines)
            return True, f"Połączenie OK. Dostępne pipeline'y: {pipeline_count}"
            
        except Exception as e:
            return False, f"Błąd testowania: {str(e)}"
    
    async def close(self):
        """Zamknięcie połączenia."""
        self.connected = False
        if self.websocket:
            try:
                await self.websocket.close()
                logger.info("Połączenie zamknięte")
            except Exception as e:
                logger.error(f"Błąd zamykania połączenia: {e}")