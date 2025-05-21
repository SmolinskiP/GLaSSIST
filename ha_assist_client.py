import asyncio
import json
import logging
import websockets
import os
from dotenv import load_dotenv

# Ładowanie zmiennych środowiskowych z pliku .env
load_dotenv()

# Konfiguracja loggera
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class HomeAssistantClient:
    def __init__(self):
        # Pobieramy wszystkie ustawienia z pliku .env
        self.host = os.getenv("HA_HOST", "localhost:8123")
        self.token = os.getenv("HA_TOKEN")
        self.pipeline_id = os.getenv("HA_PIPELINE_ID")
        self.sample_rate = int(os.getenv("HA_SAMPLE_RATE", "16000"))
        self.silence_duration_ms = int(os.getenv("HA_SILENCE_DURATION_MS", "1000"))
        
        # Sprawdzenie czy token istnieje
        if not self.token:
            raise ValueError("Brak tokena dostępu w pliku .env (HA_TOKEN)")
        
        self.websocket = None
        self.message_id = 1
        self.stt_binary_handler_id = None
        self.connected = False

    async def connect(self):
        """Nawiązanie połączenia WebSocket z Home Assistant."""
        uri = f"ws://{self.host}/api/websocket"
        logger.info(f"Łączenie z Home Assistant: {uri}")
        
        try:
            self.websocket = await websockets.connect(uri)
            logger.info("Połączenie ustanowione")
            
            # Oczekiwanie na wiadomość auth_required
            auth_message = await self.websocket.recv()
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
            auth_result = await self.websocket.recv()
            auth_result = json.loads(auth_result)
            
            if auth_result["type"] != "auth_ok":
                logger.error(f"Uwierzytelnianie nie powiodło się: {auth_result}")
                await self.websocket.close()
                return False
            
            logger.info("Uwierzytelnianie zakończone sukcesem")
            self.connected = True
            return True
            
        except Exception as e:
            logger.error(f"Błąd połączenia: {str(e)}")
            return False

    async def start_assist_pipeline(self):
        """Uruchomienie pipeline Assist od etapu STT do TTS."""
        logger.info("Uruchamiam pipeline Assist")
        
        pipeline_params = {
            "type": "assist_pipeline/run",
            "start_stage": "stt",
            "end_stage": "intent",
            "input": {
                "sample_rate": self.sample_rate
            }
        }
        
        if self.pipeline_id:
            pipeline_params["pipeline"] = self.pipeline_id
            
        await self.websocket.send(json.dumps({
            "id": self.message_id,
            **pipeline_params
        }))
        self.message_id += 1
        
        # Oczekiwanie na wiadomości z serwera i szukanie binary_handler_id
        while True:
            response = await self.websocket.recv()
            try:
                response_json = json.loads(response)
                logger.info(f"Otrzymano: {response_json}")
                
                # Szukamy wydarzenia run-start, które zawiera stt_binary_handler_id w runner_data
                if (response_json.get("type") == "event" and 
                    response_json.get("event", {}).get("type") == "run-start"):
                    self.stt_binary_handler_id = response_json.get("event", {}).get("data", {}).get("runner_data", {}).get("stt_binary_handler_id")
                    logger.info(f"Otrzymano stt_binary_handler_id: {self.stt_binary_handler_id}")
                    if self.stt_binary_handler_id is not None:
                        break
                
                # Szukamy również wydarzenia stt-start jako zapasowego sposobu
                elif (response_json.get("type") == "event" and 
                    response_json.get("event", {}).get("type") == "stt-start"):
                    # Kontynuuj oczekiwanie na run-start, stt-start to tylko potwierdzenie, że proces STT się rozpoczął
                    continue
                    
            except json.JSONDecodeError:
                logger.warning("Otrzymano wiadomość, która nie jest JSON")
        
        return self.stt_binary_handler_id is not None

    async def send_silence(self):
        """Wysyłanie ciszy do pipeline STT."""
        if not self.stt_binary_handler_id:
            logger.error("Nie znaleziono stt_binary_handler_id")
            return False
        
        # Generowanie ciszy (zera) na określony czas
        # Dla 16kHz, 16-bit (2 bajty na próbkę) = 32000 bajtów na sekundę
        samples_count = int(self.sample_rate * (self.silence_duration_ms / 1000))
        silence_data = bytearray(samples_count * 2)  # 16-bit = 2 bajty na próbkę
        
        # Prefiks z stt_binary_handler_id
        prefix = bytearray([self.stt_binary_handler_id])
        
        # Wysłanie ciszy
        logger.info(f"Wysyłam {samples_count} próbek ciszy ({len(silence_data)} bajtów)")
        await self.websocket.send(prefix + silence_data)
        
        # Wysłanie komunikatu kończącego audio
        logger.info("Wysyłam sygnał końca audio")
        await self.websocket.send(bytearray([self.stt_binary_handler_id]))
        
        return True
    
    async def receive_response(self):
        """Odbiór odpowiedzi z Assist."""
        results = []
        try:
            while True:
                response = await asyncio.wait_for(self.websocket.recv(), timeout=10)
                try:
                    response_json = json.loads(response)
                    logger.info(f"Otrzymano: {response_json}")
                    results.append(response_json)
                    
                    # Kończymy pętlę, jeśli wystąpi jeden z tych warunków:
                    # 1. Otrzymaliśmy intent-end (normalne zakończenie)
                    # 2. Otrzymaliśmy run-end (zakończenie całego pipeline'u)
                    # 3. Otrzymaliśmy error (błąd przetwarzania)
                    if (response_json.get("type") == "event" and 
                        (response_json.get("event", {}).get("type") == "intent-end" or
                        response_json.get("event", {}).get("type") == "run-end" or
                        response_json.get("event", {}).get("type") == "error")):
                        break
                        
                except json.JSONDecodeError:
                    logger.warning(f"Otrzymano wiadomość nie-JSON: {response}")
                    
        except asyncio.TimeoutError:
            logger.warning("Timeout podczas oczekiwania na odpowiedź")
        
        return results

    async def close(self):
        """Zamknięcie połączenia."""
        if self.websocket:
            await self.websocket.close()
            logger.info("Połączenie zamknięte")
            
    def extract_assistant_response(self, results):
        """Wydobycie odpowiedzi asystenta z wyników."""
        # Szukamy odpowiedzi w intent-end
        for result in results:
            if (result.get("type") == "event" and 
                result.get("event", {}).get("type") == "intent-end"):
                intent_output = result.get("event", {}).get("data", {}).get("intent_output", {})
                response = intent_output.get("response", {}).get("speech", {}).get("plain", "")
                return response
        
        # Jeśli nie znaleźliśmy odpowiedzi, sprawdzamy czy wystąpił błąd
        for result in results:
            if (result.get("type") == "event" and 
                result.get("event", {}).get("type") == "error"):
                error_code = result.get("event", {}).get("data", {}).get("code", "")
                error_message = result.get("event", {}).get("data", {}).get("message", "")
                return f"Błąd: {error_code} - {error_message}"
        
        return "Brak odpowiedzi od asystenta"

async def main():
    try:
        client = HomeAssistantClient()
        
        if await client.connect():
            logger.info("Połączono z Home Assistant")
            
            if await client.start_assist_pipeline():
                logger.info("Pipeline Assist uruchomiony pomyślnie")
                
                if await client.send_silence():
                    logger.info("Cisza wysłana pomyślnie")
                    
                    results = await client.receive_response()
                    response = client.extract_assistant_response(results)
                    
                    if response:
                        print("\n=== ODPOWIEDŹ ASYSTENTA ===")
                        print(response)
                        print("===========================\n")
                    else:
                        print("\nBrak odpowiedzi od asystenta lub błąd przetwarzania.")
                else:
                    logger.error("Nie udało się wysłać ciszy")
            else:
                logger.error("Nie udało się uruchomić pipeline Assist")
        else:
            logger.error("Nie udało się połączyć z Home Assistant")
            
    except Exception as e:
        logger.exception(f"Wystąpił błąd: {str(e)}")
    finally:
        if 'client' in locals():
            await client.close()

if __name__ == "__main__":
    asyncio.run(main())