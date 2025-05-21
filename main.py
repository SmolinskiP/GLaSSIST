"""
Główny plik aplikacji do interakcji z Home Assistant ASSIST przez WebSocket API.
"""
import asyncio
import utils
from client import HomeAssistantClient
from audio import AudioManager

logger = utils.setup_logger()

async def main():
    """Główna funkcja aplikacji."""
    try:
        # Inicjalizacja klientów
        ha_client = HomeAssistantClient()
        audio_manager = AudioManager()
        
        # Inicjalizacja mikrofonu
        audio_manager.init_audio()
        
        # Połączenie z Home Assistant
        if await ha_client.connect():
            logger.info("Połączono z Home Assistant")
            
            # Uruchomienie pipeline Assist
            if await ha_client.start_assist_pipeline():
                logger.info("Pipeline Assist uruchomiony pomyślnie")
                
                print("\n=== MÓWISZ ===")
                print("(Oczekiwanie na głos, mów do mikrofonu...)")
                
                # Rejestracja funkcji callback dla fragmentów audio
                async def on_audio_chunk(audio_chunk):
                    await ha_client.send_audio_chunk(audio_chunk)
                
                async def on_audio_end():
                    await ha_client.end_audio()
                
                # Rozpoczęcie nagrywania
                if await audio_manager.record_audio(on_audio_chunk, on_audio_end):
                    logger.info("Audio wysłane pomyślnie")
                    
                    # Odbieranie odpowiedzi
                    results = await ha_client.receive_response()
                    response = ha_client.extract_assistant_response(results)
                    
                    if response:
                        print("\n=== ODPOWIEDŹ ASYSTENTA ===")
                        print(response)
                        print("===========================\n")
                        
                        # Odtwórz dźwięk odpowiedzi
                        audio_url = ha_client.extract_audio_url(results)
                        if ha_client.audio_url:
                            print("Odtwarzam odpowiedź głosową...")
                            utils.play_audio_from_url(ha_client.audio_url, ha_client.host)
                        else:
                            print("Brak URL audio do odtworzenia")
                    else:
                        print("\nBrak odpowiedzi od asystenta lub błąd przetwarzania.")
                else:
                    logger.error("Nie udało się nagrać i wysłać audio")
            else:
                logger.error("Nie udało się uruchomić pipeline Assist")
        else:
            logger.error("Nie udało się połączyć z Home Assistant")
            
    except Exception as e:
        logger.exception(f"Wystąpił błąd: {str(e)}")
    finally:
        if 'audio_manager' in locals():
            audio_manager.close_audio()
        
        if 'ha_client' in locals():
            await ha_client.close()

if __name__ == "__main__":
    asyncio.run(main())