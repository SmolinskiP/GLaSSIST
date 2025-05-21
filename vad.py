"""
Moduł do detekcji aktywności głosowej (VAD).
"""
import time
import collections
import webrtcvad
import utils

logger = utils.setup_logger()

class VoiceActivityDetector:
    """Klasa do wykrywania aktywności głosowej przy użyciu WebRTC VAD."""
    
    def __init__(self):
        """Inicjalizacja detektora aktywności głosowej."""
        # WebRTC VAD wymaga częstotliwości próbkowania 8000, 16000 lub 32000 Hz
        self.sample_rate = utils.get_env("HA_SAMPLE_RATE", 16000, int)
        if self.sample_rate not in [8000, 16000, 32000]:
            logger.warning(f"Niekompatybilna częstotliwość próbkowania: {self.sample_rate}Hz. WebRTC VAD wymaga 8000, 16000 lub 32000 Hz")
            # Ustaw najbliższą kompatybilną wartość
            if self.sample_rate < 8000:
                self.sample_rate = 8000
            elif self.sample_rate < 16000:
                self.sample_rate = 8000
            elif self.sample_rate < 32000:
                self.sample_rate = 16000
            else:
                self.sample_rate = 32000
            logger.info(f"Dostosowano częstotliwość próbkowania do {self.sample_rate}Hz")
        
        self.vad_mode = utils.get_env("HA_VAD_MODE", 3, int)  # 0-3, im wyżej tym bardziej agresywny
        
        # WebRTC VAD wymaga ramek o długości 10, 20 lub 30 ms
        # Dla 16kHz jedna próbka zajmuje 1/16000 sekundy, więc 10ms to 160 próbek
        # Dla innych częstotliwości odpowiednio
        frame_duration_ms = utils.get_env("HA_FRAME_DURATION_MS", 30, int)
        if frame_duration_ms not in [10, 20, 30]:
            logger.warning(f"Niekompatybilna długość ramki: {frame_duration_ms}ms. WebRTC VAD wymaga 10, 20 lub 30ms.")
            frame_duration_ms = 30  # Domyślnie 30ms
        
        # Oblicz rozmiar fragmentu na podstawie długości ramki i częstotliwości próbkowania
        self.chunk_size = int(self.sample_rate * frame_duration_ms / 1000)
        
        self.padding_ms = utils.get_env("HA_PADDING_MS", 300, int)  # ms ciszy na końcu
        self.silence_threshold_sec = utils.get_env("HA_SILENCE_THRESHOLD_SEC", 0.8, float)
        
        # Inicjalizacja WebRTC VAD
        self.vad = webrtcvad.Vad(self.vad_mode)
        
        # Bufor do przechowywania historii fragmentów głosu
        self.voiced_frames = collections.deque(maxlen=500)
        
        # Stan detektora
        self.is_speech_active = False
        self.last_voice_time = 0
        
        logger.info(f"VAD zainicjalizowany: tryb={self.vad_mode}, próg ciszy={self.silence_threshold_sec}s, rozmiar fragmentu={self.chunk_size}")
    
    def is_speech(self, audio_chunk):
        """Sprawdza czy dany fragment audio zawiera mowę."""
        # Sprawdź czy długość danych zgadza się z oczekiwaną
        expected_bytes = self.chunk_size * 2  # 16-bit = 2 bajty na próbkę
        if len(audio_chunk) != expected_bytes:
            logger.warning(f"Nieoczekiwana długość danych audio: {len(audio_chunk)} bajtów, oczekiwano {expected_bytes}")
            return False
        
        try:
            return self.vad.is_speech(audio_chunk, self.sample_rate)
        except Exception as e:
            logger.error(f"Błąd VAD: {str(e)}")
            # W przypadku błędu zakładamy, że to nie jest mowa
            return False
    
    def process_audio(self, audio_chunk):
        """
        Przetwarza fragment audio i określa czy to jest aktywna mowa.
        
        Zwraca:
            tuple: (czy_przetwarzać, czy_kończyć)
                - czy_przetwarzać: True jeśli ten fragment powinien być wysłany
                - czy_kończyć: True jeśli to jest ostatni fragment (koniec mowy)
        """
        # W przypadku problemów z VAD, zawsze przetwarzaj dane audio
        # i używaj prostego wykrywania na podstawie czasu
        try:
            # Bufory do akumulacji wyników VAD
            is_speech_chunk = self.is_speech(audio_chunk)
            
            # Aktualizacja stanu detektora
            if is_speech_chunk:
                self.last_voice_time = time.time()
                
                if not self.is_speech_active:
                    logger.info("Wykryto początek mowy")
                    self.is_speech_active = True
                
                # Dodaj aktualny fragment do bufora
                self.voiced_frames.append(audio_chunk)
                return True, False
            else:
                # To jest cisza - sprawdź czy to koniec mowy
                if self.is_speech_active:
                    silence_duration = time.time() - self.last_voice_time
                    
                    # Dodaj fragmenty ciszy na końcu
                    if silence_duration < self.silence_threshold_sec:
                        self.voiced_frames.append(audio_chunk)
                        return True, False
                    else:
                        logger.info(f"Wykryto koniec mowy po {silence_duration:.2f}s ciszy")
                        self.is_speech_active = False
                        self.voiced_frames.clear()
                        return True, True
                
                # To jest cisza przed wykryciem mowy - nie przetwarzaj
                return False, False
        except Exception as e:
            logger.exception(f"Błąd podczas przetwarzania audio: {str(e)}")
            # W przypadku błędu, zawsze przetwarzaj dane audio
            return True, False
    
    def reset(self):
        """Resetuje stan detektora."""
        self.is_speech_active = False
        self.last_voice_time = 0
        self.voiced_frames.clear()