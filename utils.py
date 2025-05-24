"""
Moduł zawierający funkcje pomocnicze dla aplikacji.
"""
import os
import logging
import time
import threading
from datetime import datetime
from dotenv import load_dotenv
import requests
import sounddevice as sd
import soundfile as sf
import numpy as np
import io

# Ładowanie zmiennych środowiskowych z pliku .env
load_dotenv()

def setup_logger():
    """Konfiguracja i zwrócenie loggera."""
    import sys
    
    # Handler z wymuszonym flush po każdym logu
    class FlushHandler(logging.StreamHandler):
        def emit(self, record):
            super().emit(record)
            self.flush()  # WYMUŚ FLUSH PO KAŻDYM LOGU
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[FlushHandler(sys.stdout)]
    )
    
    return logging.getLogger('haassist')

# Funkcja pomocnicza do pobierania zmiennych środowiskowych
def get_env(key, default=None, as_type=str):
    """Pobierz zmienną środowiskową i opcjonalnie przekonwertuj na określony typ."""
    # UWAGA: Najpierw sprawdź wartość w PLIKU .env
    value = _read_from_env_file(key)
    
    # Jeśli nie ma w pliku, dopiero wtedy użyj zmiennych systemowych
    if value is None:
        value = os.getenv(key, default)
    
    if value is None:
        return None
    
    if as_type == bool:
        return value.lower() in ('true', '1', 'yes', 'y', 't')
    
    try:
        return as_type(value)
    except (ValueError, TypeError):
        logger.warning(f"Nie można przekonwertować '{value}' na typ {as_type.__name__} dla klucza {key}")
        return default

def _read_from_env_file(key):
    """Odczytaj wartość bezpośrednio z pliku .env."""
    possible_paths = [
        os.path.join(os.path.dirname(__file__), '.env'),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),
        '.env'
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            parts = line.split('=', 1)
                            if len(parts) == 2:
                                env_key, env_value = parts
                                if env_key.strip() == key:
                                    return env_value.strip()
            except Exception as e:
                logger.warning(f"Błąd odczytu pliku .env: {e}")
    
    return None

def get_timestamp():
    """Zwraca aktualny timestamp w milisekundach."""
    return int(time.time() * 1000)

def get_datetime_string():
    """Zwraca sformatowany string z datą i czasem."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def play_audio_from_url(url, host, animation_server=None):
    """
    Odtwarza dźwięk z podanego URL przy użyciu sounddevice i soundfile.
    Opcjonalnie wysyła dane FFT do animation server podczas odtwarzania.
    """
    logger = setup_logger()
    
    if not url:
        logger.error("Brak URL do pliku audio")
        return False
    
    try:
        # Jeśli URL jest względny, dodaj host z odpowiednim protokołem
        if url.startswith('/'):
            # Określ protokół na podstawie typu hosta (tak samo jak w client.py)
            if host.startswith(('localhost', '127.0.0.1', '192.168.', '10.', '172.')):
                protocol = "http"
            else:
                protocol = "https"
            full_url = f"{protocol}://{host}{url}"
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
        
        # Jeśli mamy animation server, użyj zaawansowanego odtwarzania z analizą FFT
        if animation_server:
            logger.info(f"Odtwarzanie z analizą FFT (samplerate: {samplerate})...")
            return _play_with_fft_analysis(data, samplerate, animation_server)
        else:
            # Standardowe odtwarzanie bez analizy
            logger.info(f"Standardowe odtwarzanie (samplerate: {samplerate})...")
            sd.play(data, samplerate)
            sd.wait()
            logger.info("Zakończono odtwarzanie dźwięku")
            return True
            
    except Exception as e:
        logger.exception(f"Błąd odtwarzania audio: {str(e)}")
        return False

def _play_with_fft_analysis(audio_data, samplerate, animation_server):
    """
    Odtwarza audio i jednocześnie wysyła dane FFT do animation server.
    """
    logger = setup_logger()
    
    try:
        # Parametry dla analizy FFT
        chunk_size = 1024  # Rozmiar fragmentu dla FFT (mniejszy = szybsza reakcja)
        
        # Convert stereo to mono if needed
        if len(audio_data.shape) > 1:
            audio_data = np.mean(audio_data, axis=1)
        
        # Konwersja do int16 dla kompatybilności
        if audio_data.dtype != np.int16:
            # Normalizacja do zakresu int16
            audio_data = (audio_data * 32767).astype(np.int16)
        
        # Zmienne do śledzenia postępu odtwarzania
        total_samples = len(audio_data)
        samples_played = 0
        
        # Callback do analizy audio podczas odtwarzania
        def audio_callback(outdata, frames, time, status):
            nonlocal samples_played
            
            if status:
                logger.warning(f"Audio callback status: {status}")
            
            # Sprawdź czy jeszcze mamy dane do odtworzenia
            if samples_played >= total_samples:
                # Koniec danych - wypełnij ciszą
                outdata.fill(0)
                return
            
            # Oblicz ile próbek możemy odtworzyć
            samples_to_play = min(frames, total_samples - samples_played)
            
            # Skopiuj dane audio do bufora wyjściowego
            if len(audio_data.shape) == 1:
                # Mono - duplikuj do stereo jeśli potrzeba
                if outdata.shape[1] == 2:
                    outdata[:samples_to_play, 0] = audio_data[samples_played:samples_played + samples_to_play]
                    outdata[:samples_to_play, 1] = audio_data[samples_played:samples_played + samples_to_play]
                else:
                    outdata[:samples_to_play, 0] = audio_data[samples_played:samples_played + samples_to_play]
            
            # Wypełnij resztę ciszą jeśli potrzeba
            if samples_to_play < frames:
                outdata[samples_to_play:].fill(0)
            
            # ANALIZA FFT - użyj mniejszego chunka dla lepszej responsywności
            fft_chunk_size = min(chunk_size, samples_to_play)
            if fft_chunk_size > 0:
                chunk_data = audio_data[samples_played:samples_played + fft_chunk_size]
                
                # Wykonaj analizę FFT w osobnym wątku żeby nie blokować audio
                threading.Thread(
                    target=_send_fft_to_animation, 
                    args=(chunk_data, animation_server), 
                    daemon=True
                ).start()
            
            samples_played += samples_to_play
        
        # Uruchom stream z callback
        logger.info("Rozpoczynam odtwarzanie z analizą FFT...")
        
        with sd.OutputStream(
            samplerate=samplerate,
            channels=2,  # Stereo output
            callback=audio_callback,
            dtype=np.int16
        ):
            # Oblicz czas trwania i czekaj
            duration = len(audio_data) / samplerate
            logger.info(f"Czas trwania audio: {duration:.2f}s")
            
            # Czekaj na zakończenie odtwarzania
            time.sleep(duration + 0.5)  # Dodatkowe 0.5s na margines
        
        logger.info("Zakończono odtwarzanie z analizą FFT")
        return True
        
    except Exception as e:
        logger.exception(f"Błąd odtwarzania z analizą FFT: {str(e)}")
        return False

def _send_fft_to_animation(audio_chunk, animation_server):
    """
    Wykonuje analizę FFT i wysyła dane do animation server.
    Wywoływane w osobnym wątku.
    """
    try:
        if len(audio_chunk) == 0:
            return
            
        # Konwersja do bytes dla kompatybilności z istniejącą funkcją send_audio_data
        if audio_chunk.dtype != np.int16:
            audio_chunk = audio_chunk.astype(np.int16)
        audio_chunk = (audio_chunk * 0.6).astype(np.int16)
        audio_bytes = audio_chunk.tobytes()
        
        # Wyślij do animation server (użyje istniejącej logiki FFT)
        animation_server.send_audio_data(audio_bytes, 16000)  # Zakładamy 16kHz dla FFT
        
    except Exception as e:
        # Nie loguj każdego błędu FFT żeby nie spammować
        pass

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

def play_feedback_sound(sound_name):
    """
    Odtwarza dźwięk feedback (activation.wav, deactivation.wav) z folderu 'sound'.
    
    Args:
        sound_name: Nazwa dźwięku ('activation' lub 'deactivation')
    """
    # Sprawdź czy dźwięki są włączone
    sound_enabled = get_env('HA_SOUND_FEEDBACK', 'true')
    if sound_enabled.lower() not in ('true', '1', 'yes', 'y', 't'):
        return False
    
    logger = setup_logger()
    
    try:
        # Ścieżka do pliku dźwiękowego
        sound_dir = os.path.join(os.path.dirname(__file__), 'sound')
        sound_file = os.path.join(sound_dir, f"{sound_name}.wav")
        
        if not os.path.exists(sound_file):
            logger.warning(f"Brak pliku dźwiękowego: {sound_file}")
            return False
        
        # Wczytaj i odtwórz dźwięk w osobnym wątku żeby nie blokować
        def play_thread():
            try:
                data, samplerate = sf.read(sound_file)
                sd.play(data, samplerate)
                # Nie używamy sd.wait() żeby nie blokować
                
            except Exception as e:
                logger.error(f"Błąd odtwarzania dźwięku {sound_name}: {e}")
        
        # Uruchom w osobnym wątku
        thread = threading.Thread(target=play_thread, daemon=True)
        thread.start()
        
        logger.debug(f"Odtwarzam dźwięk: {sound_name}")
        return True
        
    except Exception as e:
        logger.error(f"Błąd odtwarzania dźwięku feedback {sound_name}: {e}")
        return False

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
    