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
        
        logger.info(f"AudioManager zainicjalizowany: {self.sample_rate}Hz, {self.channels} kanał(y), chunk {self.chunk_size}")
    
    def init_audio(self):
        """Inicjalizacja PyAudio i strumienia mikrofonu."""
        self.audio = pyaudio.PyAudio()
        
        # Znalezienie indeksu urządzenia mikrofonu
        mic_device_index = None
        for i in range(self.audio.get_device_count()):
            device_info = self.audio.get_device_info_by_index(i)
            logger.debug(f"Urządzenie audio {i}: {device_info['name']}")
            if device_info.get('maxInputChannels') > 0:
                mic_device_index = i
                logger.info(f"Znaleziono mikrofon: {device_info['name']}")
                break
        
        if mic_device_index is None:
            logger.error("Nie znaleziono mikrofonu")
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
    
    def close_audio(self):
        """Zamknięcie strumienia audio i PyAudio."""
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            logger.info("Strumień audio zamknięty")
        
        if self.audio:
            self.audio.terminate()
            logger.info("PyAudio zakończone")
    
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
        
        # Nasłuchiwanie dźwięku
        try:
            waiting_for_speech = True
            speech_active = False
            
            while True:
                # Odczytanie danych audio
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                
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
                        await on_chunk_callback(data)
                    
                    # Jeśli to koniec mowy, zakończ nagrywanie
                    if is_end:
                        speech_active = False
                        if on_end_callback:
                            await on_end_callback()
                        break
        
        except Exception as e:
            logger.exception(f"Błąd podczas nagrywania: {str(e)}")
            return False
        
        logger.info("Zakończono nagrywanie")
        return True