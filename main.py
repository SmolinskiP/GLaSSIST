"""
Główny plik aplikacji do interakcji z Home Assistant ASSIST przez WebSocket API.
"""
import asyncio
import threading
import webview
import sys
import os
import pystray
from PIL import Image, ImageDraw
from pystray import MenuItem as item
import utils
from client import HomeAssistantClient
from audio import AudioManager
from animation_server import AnimationServer

logger = utils.setup_logger()

class HAAssistApp:
    """Główna klasa aplikacji."""
    
    def __init__(self):
        """Inicjalizacja aplikacji."""
        self.ha_client = None
        self.audio_manager = None
        self.animation_server = None
        self.window = None
        self.is_running = False
        self.tray_icon = None
        self.window_visible = True
        
    def create_tray_icon(self):
        """Utworzenie ikony w system tray."""
        # Tworzenie prostej ikony
        image = Image.new('RGB', (64, 64), color='black')
        draw = ImageDraw.Draw(image)
        draw.ellipse([8, 8, 56, 56], fill='#4fc3f7', outline='white', width=2)
        draw.ellipse([24, 24, 40, 40], fill='white')
        
        # Menu kontekstowe
        menu = pystray.Menu(
            item('Pokaż/Ukryj okno', self.toggle_window),
            item('Aktywuj głos (Ctrl+Shift+H)', self.trigger_voice_command),
            pystray.Menu.SEPARATOR,
            item('Zamknij', self.quit_application)
        )
        
        self.tray_icon = pystray.Icon(
            "HA Assist",
            image,
            "HA Assist Desktop",
            menu
        )
        
        logger.info("Ikona system tray utworzona")
        
    def setup_animation_server(self):
        """Konfiguracja serwera animacji."""
        self.animation_server = AnimationServer()
        
        # Ustawienie callback'a dla aktywacji z frontendu
        self.animation_server.set_voice_command_callback(self.on_voice_command_trigger)
        
        self.animation_server.start()
        logger.info("Animation server uruchomiony")
    
    def setup_webview(self):
        """Konfiguracja okna webview."""
        # Ścieżka do plików frontend
        frontend_path = os.path.join(os.path.dirname(__file__), 'frontend')
        index_path = os.path.join(frontend_path, 'index.html')
        
        if not os.path.exists(index_path):
            logger.error(f"Nie znaleziono pliku frontend: {index_path}")
            return False
        
        # Utworzenie okna webview - ukryte z paska zadań
        self.window = webview.create_window(
            'HA Assist',
            index_path,
            width=400,
            height=400,
            resizable=False,
            fullscreen=False,
            minimized=False,
            on_top=True,
            shadow=False,
            frameless=True,
            transparent=True,
            y=10
        )
        
        logger.info("Webview window skonfigurowane (ukryte z paska zadań)")
        return True

    async def process_voice_command(self):
        """Przetwarzanie komendy głosowej."""
        try:
            # Zmień stan na nasłuchiwanie
            self.animation_server.change_state("listening")
            
            # Inicjalizacja klientów
            self.ha_client = HomeAssistantClient()
            self.audio_manager = AudioManager()
            
            # Inicjalizacja mikrofonu
            self.audio_manager.init_audio()
            
            # Połączenie z Home Assistant
            if not await self.ha_client.connect():
                logger.error("Nie udało się połączyć z Home Assistant")
                self.animation_server.change_state("error", "Nie można połączyć się z Home Assistant")
                await asyncio.sleep(8)  # WYDŁUŻONO z 6 do 8 sekund
                self.animation_server.change_state("hidden")
                return False
            
            logger.info("Połączono z Home Assistant")
            
            # Uruchomienie pipeline Assist
            if not await self.ha_client.start_assist_pipeline():
                logger.error("Nie udało się uruchomić pipeline Assist")
                self.animation_server.change_state("error", "Nie można uruchomić asystenta głosowego")
                await asyncio.sleep(8)  # WYDŁUŻONO z 6 do 8 sekund
                self.animation_server.change_state("hidden")
                return False
            
            logger.info("Pipeline Assist uruchomiony pomyślnie")
            
            print("\n=== MÓWISZ ===")
            print("(Oczekiwanie na głos, mów do mikrofonu...)")
            
            # Rejestracja funkcji callback dla fragmentów audio
            async def on_audio_chunk(audio_chunk):
                # Wyślij dane audio do animacji
                self.animation_server.send_audio_data(audio_chunk)
                # Wyślij do Home Assistant
                await self.ha_client.send_audio_chunk(audio_chunk)
            
            async def on_audio_end():
                # Zmień stan na przetwarzanie Z MAŁYM OPÓŹNIENIEM
                logger.info("=== PRZECHODZĘ DO PRZETWARZANIA ===")
                self.animation_server.change_state("processing")
                
                # KRÓTKIE OPÓŹNIENIE - żeby animacja processing była widoczna
                await asyncio.sleep(0.8)
                
                await self.ha_client.end_audio()
            
            # Rozpoczęcie nagrywania
            if await self.audio_manager.record_audio(on_audio_chunk, on_audio_end):
                logger.info("Audio wysłane pomyślnie")
                
                # Odbieranie odpowiedzi - TUTAJ BĘDĄ LOGI W CZASIE RZECZYWISTYM
                logger.info("=== ODBIERAM ODPOWIEDŹ ===")
                results = await self.ha_client.receive_response()
                
                # SPRAWDŹ CZY NIE MA BŁĘDU W RESULTS
                error_found = False
                for result in results:
                    if result.get('type') == 'event':
                        event = result.get('event', {})
                        if event.get('type') == 'error':
                            # BŁĄD ZNALEZIONY!
                            error_code = event.get('data', {}).get('code', 'unknown')
                            error_message = event.get('data', {}).get('message', 'Nieznany błąd')
                            
                            print(f"\n=== BŁĄD ASYSTENTA ===")
                            print(f"Błąd: {error_code} - {error_message}")
                            print("===========================\n")
                            
                            # POKAŻ ERROR ANIMATION Z TEKSTEM BŁĘDU
                            full_error_message = f"{error_code}: {error_message}"
                            self.animation_server.change_state("error", full_error_message)
                            await asyncio.sleep(8)  # WYDŁUŻONO z 6 do 8 sekund - więcej czasu na przeczytanie
                            self.animation_server.change_state("hidden")
                            
                            error_found = True
                            break
                
                if not error_found:
                    # NIE MA BŁĘDU - NORMALNA ODPOWIEDŹ
                    response = self.ha_client.extract_assistant_response(results)
                    
                    if response:
                        print("\n=== ODPOWIEDŹ ASYSTENTA ===")
                        print(response)
                        print("===========================\n")
                        
                        # Zmień stan na odpowiadanie i wyślij tekst
                        self.animation_server.change_state("responding")
                        self.animation_server.send_response_text(response)
                        
                        # Odtwórz dźwięk odpowiedzi Z ANALIZĄ FFT! 🔥
                        audio_url = self.ha_client.extract_audio_url(results)
                        if audio_url:
                            print("Odtwarzam odpowiedź głosową z analizą FFT...")
                            utils.play_audio_from_url(audio_url, self.ha_client.host, self.animation_server)
                        
                        # Powrót do stanu hidden po 3 sekundach
                        await asyncio.sleep(3)
                        self.animation_server.change_state("hidden")
                    else:
                        print("\nBrak odpowiedzi od asystenta lub błąd przetwarzania.")
                        self.animation_server.change_state("error", "Asystent nie odpowiedział")
                        await asyncio.sleep(8)  # WYDŁUŻONO z 6 do 8 sekund
                        self.animation_server.change_state("hidden")
            else:
                logger.error("Nie udało się nagrać i wysłać audio")
                self.animation_server.change_state("error", "Błąd nagrywania audio")
                await asyncio.sleep(8)  # WYDŁUŻONO z 6 do 8 sekund
                self.animation_server.change_state("hidden")
                
        except Exception as e:
            logger.exception(f"Wystąpił błąd podczas przetwarzania: {str(e)}")
            
            # WYCIĄGNIJ INFORMACJĘ O BŁĘDZIE I PRZEKAŻ DO ANIMACJI
            error_msg = str(e)
            if len(error_msg) > 80:  # Ogranicz długość wiadomości błędu
                error_msg = error_msg[:77] + "..."
            
            self.animation_server.change_state("error", f"Błąd: {error_msg}")
            
            # Po błędzie też wracamy do hidden - WYDŁUŻONO CZAS
            await asyncio.sleep(10)  # WYDŁUŻONO z 6 do 10 sekund dla błędów wyjątków
            self.animation_server.change_state("hidden")
        finally:
            # Cleanup
            if self.audio_manager:
                self.audio_manager.close_audio()
            if self.ha_client:
                await self.ha_client.close()

    def on_voice_command_trigger(self):
        """Callback wywoływany gdy użytkownik aktywuje komendę głosową."""
        # ZMIANA: sprawdzaj 'hidden' zamiast 'idle'
        if self.animation_server.current_state != "hidden":
            logger.info("Aplikacja jest zajęta, ignoruję trigger")
            return
        
        # Uruchom przetwarzanie w osobnym wątku
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        def run_async():
            loop.run_until_complete(self.process_voice_command())
        
        thread = threading.Thread(target=run_async, daemon=True)
        thread.start()
    
    def hide_from_taskbar(self):
        """Ukrycie okna z paska zadań Windows (backup method)."""
        try:
            import ctypes
            from ctypes import wintypes
            
            user32 = ctypes.windll.user32
            screen_width = user32.GetSystemMetrics(0)   # SM_CXSCREEN
            screen_height = user32.GetSystemMetrics(1)  # SM_CYSCREEN
            window_width = 500
            window_height = 500
            pos_x = (screen_width - window_width) // 2
            pos_y = screen_height - window_height + 50

            logger.info(f"Rozmiar ekranu: {screen_width}x{screen_height}")
            logger.info(f"Pozycja okna: x={pos_x}, y={pos_y}")

            found_windows = []
            
            # Znajdź okno aplikacji
            def enum_windows_proc(hwnd, lParam):
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    window_text = ctypes.create_unicode_buffer(512)
                    ctypes.windll.user32.GetWindowTextW(hwnd, window_text, 512)
                    class_name = ctypes.create_unicode_buffer(512)
                    ctypes.windll.user32.GetClassNameW(hwnd, class_name, 512)
                    
                    window_title = window_text.value
                    class_name_str = class_name.value
                    
                    # TYLKO okno HA Assist - bardzo precyzyjnie!
                    if window_title == "HA Assist" and "WindowsForms10" in class_name_str:
                        
                        found_windows.append((hwnd, window_title, class_name_str))
                        
                        # Ustaw WS_EX_TOOLWINDOW żeby ukryć z paska zadań
                        GWL_EXSTYLE = -20
                        WS_EX_TOOLWINDOW = 0x00000080
                        WS_EX_APPWINDOW = 0x00040000
                        
                        current_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                        # Usuń WS_EX_APPWINDOW i dodaj WS_EX_TOOLWINDOW
                        new_style = (current_style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
                        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
                        
                        # Zmuś do odświeżenia
                        SWP_FRAMECHANGED = 0x0020
                        SWP_NOMOVE = 0x0002
                        SWP_NOSIZE = 0x0001
                        SWP_NOZORDER = 0x0004
                        ctypes.windll.user32.SetWindowPos(
                            hwnd, 0,
                            pos_x, pos_y,
                            window_width, window_height,
                            SWP_FRAMECHANGED | SWP_NOZORDER
                        )
                        
                        logger.info(f"Okno ukryte z paska zadań: '{window_title}' (klasa: {class_name_str})")
                
                return True
            
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            ctypes.windll.user32.EnumWindows(EnumWindowsProc(enum_windows_proc), 0)
            
            logger.info(f"Znaleziono {len(found_windows)} okien do ukrycia")
            
        except Exception as e:
            logger.exception(f"Błąd ukrywania z paska zadań: {e}")
    
    def trigger_voice_command(self, icon=None, item=None):
        """Trigger z menu tray."""
        logger.info("Aktywacja komendy głosowej z menu tray")
        self.on_voice_command_trigger()
    
    def setup_hotkey(self):
        """Konfiguracja skrótu klawiszowego."""
        try:
            import keyboard
            
            # Skrót Ctrl+Shift+H
            hotkey = utils.get_env("HA_HOTKEY", "ctrl+shift+h")
            keyboard.add_hotkey(hotkey, self.on_voice_command_trigger)
            logger.info(f"Skrót klawiszowy ustawiony: {hotkey}")
            return True
            
        except ImportError:
            logger.warning("Biblioteka keyboard nie jest zainstalowana - uruchom: pip install keyboard")
            return False
        except Exception as e:
            logger.error(f"Błąd konfiguracji skrótu klawiszowego: {e}")
            return False
    
    def toggle_window(self, icon=None, item=None):
        """Przełączenie widoczności okna."""
        if self.window_visible:
            # Ukryj okno
            if hasattr(webview, 'windows') and webview.windows:
                webview.windows[0].minimize()
            self.window_visible = False
            logger.info("Okno ukryte")
        else:
            # Pokaż okno
            if hasattr(webview, 'windows') and webview.windows:
                webview.windows[0].restore()
            self.window_visible = True
            logger.info("Okno pokazane")
    
    def quit_application(self, icon=None, item=None):
        """Zamknięcie aplikacji z menu tray."""
        logger.info("Zamykanie aplikacji z menu tray...")
        self.cleanup()
        
        # Zatrzymaj tray icon
        if self.tray_icon:
            self.tray_icon.stop()
        
        # Zamknij webview
        if hasattr(webview, 'windows') and webview.windows:
            for window in webview.windows:
                window.destroy()
        
        sys.exit(0)
    
    def run_tray(self):
        """Uruchomienie ikony tray w osobnym wątku."""
        def tray_thread():
            try:
                self.tray_icon.run()
            except Exception as e:
                logger.exception(f"Błąd tray icon: {e}")
        
        threading.Thread(target=tray_thread, daemon=True).start()
        logger.info("System tray uruchomiony")
    
    def run(self):
        """Uruchomienie aplikacji."""
        try:
            logger.info("Uruchamianie HA Assist Desktop...")
            
            # Konfiguracja serwera animacji
            self.setup_animation_server()
            
            # Konfiguracja webview
            if not self.setup_webview():
                logger.error("Nie udało się skonfigurować interfejsu")
                return
            
            # Konfiguracja skrótu klawiszowego
            self.setup_hotkey()
            
            # Konfiguracja system tray
            self.create_tray_icon()
            self.run_tray()
            
            # Uruchomienie webview (blokujące)
            logger.info("Uruchamianie interfejsu...")
            
            # Ukrycie z paska zadań po uruchomieniu  
            def on_window_loaded():
                import time
                time.sleep(2)  # Poczekaj na pełne załadowanie okna
                logger.info("Próba ukrycia okna z paska zadań...")
                
                # Tymczasowo zwiększ poziom logowania
                old_level = logger.level
                logger.setLevel(10)  # DEBUG
                
                self.hide_from_taskbar()
                
                # Przywróć poziom logowania
                logger.setLevel(old_level)
            
            threading.Thread(target=on_window_loaded, daemon=True).start()
            
            webview.start(debug=utils.get_env("DEBUG", False, bool))
            
        except KeyboardInterrupt:
            logger.info("Aplikacja przerwana przez użytkownika")
        except Exception as e:
            logger.exception(f"Błąd aplikacji: {str(e)}")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Sprzątanie zasobów."""
        logger.info("Sprzątanie zasobów...")
        
        if self.animation_server:
            self.animation_server.stop()
        
        if self.audio_manager:
            self.audio_manager.close_audio()

def main():
    """Główna funkcja aplikacji."""
    app = HAAssistApp()
    app.run()

if __name__ == "__main__":
    main()