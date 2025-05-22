"""
Moduł zawierający funkcje pomocnicze dla aplikacji.
"""
import os
import logging
import time
from datetime import datetime
from dotenv import load_dotenv
import requests
import sounddevice as sd
import soundfile as sf
import io

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

def get_timestamp():
    """Zwraca aktualny timestamp w milisekundach."""
    return int(time.time() * 1000)

def get_datetime_string():
    """Zwraca sformatowany string z datą i czasem."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
        response = requests.get(full_url, timeout=10)
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

def validate_audio_format(sample_rate, channels=1):
    """Walidacja parametrów audio."""
    valid_rates = [8000, 16000, 22050, 44100, 48000]
    if sample_rate not in valid_rates:
        logger = setup_logger()
        logger.warning(f"Nietypowa częstotliwość próbkowania: {sample_rate}Hz")
    
    if channels not in [1, 2]:
        logger = setup_logger()
        logger.warning(f"Nietypowa liczba kanałów: {channels}")
    
    return True

def format_duration(seconds):
    """Formatuje czas trwania w sekundach na czytelny string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}h {minutes}m {secs:.1f}s"