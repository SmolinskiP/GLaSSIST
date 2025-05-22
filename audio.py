"""
Moduł do obsługi audio - nagrywanie i przetwarzanie dźwięku.
"""
import time
import pyaudio
import numpy as np
import utils
from vad import VoiceActivityDetector

logger = utils.setup_logger()

class AudioManager:
    """Klasa do zarządzania audio - nagrywanie i przetwarzanie dźwięku."""
    
    def __init__(self):
        """Inicjalizacja menedżera audio."""
        self.sample_rate = utils.get_env("HA_SAMPLE_RATE", 16000, int)
        self.channels = utils.get_env("HA_CHANNELS", 1, int)
        
        # Użyj tej samej logiki co w VAD do określenia rozmiaru fragmentu
        frame_duration_ms = utils.get_env("HA_FRAME_DURATION_MS", 30, int)
        self.chunk_size = int(self.sample_rate * frame_duration_ms / 1000)
        
        self.format = pyaudio.paInt16
        self.audio = None
        self.stream = None
        self.vad = VoiceActivityDetector()
        
        # Walidacja parametrów audio
        utils.validate_audio_format(self.sample_rate, self.channels)
        
        logger.info(f"AudioManager zainicjalizowany: {self.sample_rate}Hz, {self.channels} kanał(y), chunk {self.chunk_size}")
    
    def init_audio(self):
        """Inicjalizacja PyAudio i strumienia mikrofonu."""
        try:
            self.audio = pyaudio.PyAudio()
            
            # Znalezienie najlepszego urządzenia mikrofonu
            mic_device_index = self._find_best_microphone()
            
            if mic_device_index is None:
                logger.error("Nie znaleziono żadnego mikrofonu")
                raise Exception("Nie znaleziono mikrofonu")
            
            # Otworzenie strumienia audio
            self.stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                input_device_index=mic_device_index
            )
            
            logger.info(f"Zainicjalizowano strumień audio: {self.sample_rate} Hz, {self.channels} kanał(y), chunk {self.chunk_size}")
            return True
            
        except Exception as e:
            logger.exception(f"Błąd inicjalizacji audio: {e}")
            return False
    
    def _find_best_microphone(self):
        """Znajdowanie najlepszego dostępnego mikrofonu."""
        default_device = None
        best_device = None
        
        for i in range(self.audio.get_device_count()):
            try:
                device_info = self.audio.get_device_info_by_index(i)
                logger.debug(f"Urządzenie audio {i}: {device_info['name']} - kanały wej: {device_info.get('maxInputChannels', 0)}")
                
                # Sprawdź czy urządzenie ma kanały wejściowe
                if device_info.get('maxInputChannels', 0) > 0:
                    # Preferuj urządzenie domyślne
                    if i == self.audio.get_default_input_device_info()['index']:
                        default_device = i
                        logger.info(f"Znaleziono domyślny mikrofon: {device_info['name']}")
                    
                    # Zapisz pierwszy dostępny jako backup
                    if best_device is None:
                        best_device = i
                        logger.info(f"Znaleziono mikrofon: {device_info['name']}")
                        
            except Exception as e:
                logger.debug(f"Błąd sprawdzania urządzenia {i}: {e}")
                continue
        
        # Zwróć domyślne urządzenie jeśli dostępne, w przeciwnym razie pierwsze znalezione
        return default_device if default_device is not None else best_device
    
    def close_audio(self):
        """Zamknięcie strumienia audio i PyAudio."""
        try:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None
                logger.info("Strumień audio zamknięty")
            
            if self.audio:
                self.audio.terminate()
                self.audio = None
                logger.info("PyAudio zakończone")
                
        except Exception as e:
            logger.error(f"Błąd zamykania audio: {e}")
    
    async def record_audio(self, on_chunk_callback, on_end_callback=None):
        """
        Nagrywanie audio z detekcją aktywności głosowej.
        
        Args:
            on_chunk_callback: Funkcja wywoływana dla każdego fragmentu audio
            on_end_callback: Opcjonalna funkcja wywoływana na końcu nagrywania
        """
        if not self.stream:
            logger.error("Strumień audio nie został zainicjalizowany")
            return False
        
        logger.info("Rozpoczynam nagrywanie z detekcją VAD")
        
        # Reset VAD
        self.vad.reset()
        
        # Statystyki nagrywania
        start_time = time.time()
        chunks_processed = 0
        
        try:
            waiting_for_speech = True
            speech_active = False
            
            while True:
                # Odczytanie danych audio
                try:
                    data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                    chunks_processed += 1
                    
                except Exception as e:
                    logger.error(f"Błąd odczytu audio: {e}")
                    break
                
                # Przetworzenie audio przez VAD
                process_chunk, is_end = self.vad.process_audio(data)
                
                if waiting_for_speech:
                    if process_chunk:
                        waiting_for_speech = False
                        speech_active = True
                        logger.info("Rozpoczęto przetwarzanie mowy")
                
                if speech_active:
                    # Wywołanie callback'a dla każdego fragmentu audio
                    if process_chunk:
                        try:
                            await on_chunk_callback(data)
                        except Exception as e:
                            logger.error(f"Błąd callback audio chunk: {e}")
                    
                    # Jeśli to koniec mowy, zakończ nagrywanie
                    if is_end:
                        speech_active = False
                        duration = time.time() - start_time
                        logger.info(f"Zakończono nagrywanie po {utils.format_duration(duration)}, przetworzono {chunks_processed} fragmentów")
                        
                        if on_end_callback:
                            try:
                                await on_end_callback()
                            except Exception as e:
                                logger.error(f"Błąd callback audio end: {e}")
                        break
        
        except Exception as e:
            logger.exception(f"Błąd podczas nagrywania: {str(e)}")
            return False
        
        logger.info("Zakończono nagrywanie")
        return True
    
    def get_audio_level(self, audio_data):
        """Oblicza poziom głośności dla danego fragmentu audio."""
        try:
            # Konwersja do numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Oblicz RMS (Root Mean Square)
            rms = np.sqrt(np.mean(audio_array**2))
            
            # Normalizacja do zakresu 0-1
            # Maksymalna wartość dla 16-bit audio to 32767
            level = min(rms / 32767.0, 1.0)
            
            return level
            
        except Exception as e:
            logger.error(f"Błąd obliczania poziomu audio: {e}")
            return 0.0
    
    def is_audio_stream_active(self):
        """Sprawdza czy strumień audio jest aktywny."""
        return self.stream is not None and self.stream.is_active()
    
    def get_device_info(self):
        """Zwraca informacje o aktualnie używanym urządzeniu audio."""
        if not self.audio or not self.stream:
            return None
        
        try:
            device_index = self.stream._input_device_index
            return self.audio.get_device_info_by_index(device_index)
        except Exception as e:
            logger.error(f"Błąd pobierania informacji o urządzeniu: {e}")
            return None