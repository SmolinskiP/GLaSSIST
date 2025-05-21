"""
Moduł zawierający funkcje pomocnicze dla aplikacji.
"""
import os
import logging
from dotenv import load_dotenv
import requests
import sounddevice as sd
import soundfile as sf
import io
import time


# Ładowanie zmiennych środowiskowych z pliku .env
load_dotenv()

# Konfiguracja loggera
def setup_logger():
    """Konfiguracja i zwrócenie loggera."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger('haassist')

# Funkcja pomocnicza do pobierania zmiennych środowiskowych
def get_env(key, default=None, as_type=str):
    """Pobierz zmienną środowiskową i opcjonalnie przekonwertuj na określony typ."""
    value = os.getenv(key, default)
    if value is None:
        return None
    
    if as_type == bool:
        return value.lower() in ('true', '1', 'yes', 'y', 't')
    
    return as_type(value)

def play_audio_from_url(url, host):
    """Odtwarza dźwięk z podanego URL przy użyciu sounddevice i soundfile."""
    logger = setup_logger()
    
    if not url:
        logger.error("Brak URL do pliku audio")
        return False
    
    try:
        # Jeśli URL jest względny, dodaj host
        if url.startswith('/'):
            full_url = f"http://{host}{url}"
        else:
            full_url = url
        
        logger.info(f"Pobieranie audio z: {full_url}")
        
        # Pobierz plik audio
        response = requests.get(full_url)
        if response.status_code != 200:
            logger.error(f"Błąd pobierania audio: {response.status_code}")
            return False
        
        # Zapisz dane do bufora
        audio_buffer = io.BytesIO(response.content)
        
        # Wczytaj dźwięk do pamięci
        logger.info("Odczytywanie pliku audio...")
        data, samplerate = sf.read(audio_buffer)
        
        # Odtwórz dźwięk
        logger.info(f"Odtwarzanie dźwięku (samplerate: {samplerate})...")
        sd.play(data, samplerate)
        
        # Poczekaj na zakończenie odtwarzania
        sd.wait()
        
        logger.info("Zakończono odtwarzanie dźwięku")
        return True
    except Exception as e:
        logger.exception(f"Błąd odtwarzania audio: {str(e)}")
        return False
    """Odtwarza dźwięk z podanego URL."""
    logger = setup_logger()
    
    if not url:
        logger.error("Brak URL do pliku audio")
        return False
    
    try:
        # Inicjalizacja pygame
        # Pygame mixer powinien być już zainicjalizowany wcześniej
        
        # Jeśli URL jest względny, dodaj host
        if url.startswith('/'):
            full_url = f"http://{host}{url}"
        else:
            full_url = url
        
        logger.info(f"Pobieranie audio z: {full_url}")
        
        # Pobierz plik audio
        response = requests.get(full_url)
        if response.status_code != 200:
            logger.error(f"Błąd pobierania audio: {response.status_code}")
            return False
        
        # Zapisz dane do bufora
        audio_buffer = io.BytesIO(response.content)
        
        # Odtwórz dźwięk
        pygame.mixer.music.load(audio_buffer)
        pygame.mixer.music.play()
        
        logger.info("Odtwarzanie dźwięku...")
        
        # Poczekaj na zakończenie odtwarzania
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        
        logger.info("Zakończono odtwarzanie dźwięku")
        return True
    except Exception as e:
        logger.exception(f"Błąd odtwarzania audio: {str(e)}")
        return False
    """Odtwarza dźwięk z podanego URL."""
    if not url:
        logger = setup_logger()
        logger.error("Brak URL do pliku audio")
        return False
    
    try:
        # Inicjalizacja pygame mixer
        mixer.init()
        
        # Jeśli URL jest względny, dodaj host
        if url.startswith('/'):
            full_url = f"http://{host}{url}"
        else:
            full_url = url
        
        # Pobierz plik audio
        response = requests.get(full_url)
        if response.status_code != 200:
            logger = setup_logger()
            logger.error(f"Błąd pobierania audio: {response.status_code}")
            return False
        
        # Utwórz bufor i załaduj dane audio
        audio_data = io.BytesIO(response.content)
        mixer.music.load(audio_data)
        
        # Odtwórz dźwięk
        mixer.music.play()
        
        # Poczekaj na zakończenie odtwarzania
        while mixer.music.get_busy():
            pygame.time.wait(100)
        
        return True
    except Exception as e:
        logger = setup_logger()
        logger.exception(f"Błąd odtwarzania audio: {str(e)}")
        return False