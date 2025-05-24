"""
Kompletna poprawka main.py - zachowuję oryginalny kod i dodaję tylko usprawnienia
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
from client import HomeAssistantClient  # Ta klasa już będzie ulepszona
from audio import AudioManager
from animation_server import AnimationServer

logger = utils.setup_logger()

class HAAssistApp:
    """Główna klasa aplikacji z ulepszonymi funkcjami."""
    
    def __init__(self):
        """Inicjalizacja aplikacji."""
        self.ha_client = None
        self.audio_manager = None
        self.animation_server = None
        self.window = None
        self.settings_window = None
        self.is_running = False
        self.tray_icon = None
        self.window_visible = True
        
        # NOWOŚĆ: Cache dla pipeline'ów
        self.cached_pipelines = []
        self.pipeline_cache_time = 0
        
    def create_tray_icon(self):
        """Utworzenie ikony w system tray z ulepszonymi opcjami."""
        # Stała ścieżka do ikony
        icon_path = os.path.join(os.path.dirname(__file__), 'img', 'icon.ico')
        
        if os.path.exists(icon_path):
            # Załaduj ikonę z pliku
            try:
                from PIL import Image
                image = Image.open(icon_path)
                logger.info(f"Załadowano ikonę tray: {icon_path}")
            except Exception as e:
                logger.error(f"Błąd ładowania ikony: {e}")
                # Prosta ikona jako fallback
                image = self._create_fallback_icon()
        else:
            logger.warning(f"Brak pliku ikony: {icon_path}")
            image = self._create_fallback_icon()
        
        # ULEPSZONE menu kontekstowe
        menu = pystray.Menu(
            item('🎤 Aktywuj głos (%s)' % utils.get_env("HA_HOTKEY", "ctrl+shift+h"), 
                 self.trigger_voice_command),
            pystray.Menu.SEPARATOR,
            item('⚙️ Ustawienia', self.open_settings),
            item('🔄 Test połączenia', self._quick_connection_test),
            pystray.Menu.SEPARATOR,
            item('❌ Zamknij', self.quit_application)
        )
        
        self.tray_icon = pystray.Icon(
            "HA Assist",
            image,
            "HA Assist Desktop",
            menu
        )
        
        logger.info("Ikona system tray utworzona z ulepszonymi opcjami")
    
    def _create_fallback_icon(self):
        """Tworzenie fallback ikony."""
        image = Image.new('RGB', (64, 64), color='black')
        draw = ImageDraw.Draw(image)
        draw.ellipse([8, 8, 56, 56], fill='#4fc3f7', outline='white', width=2)
        draw.ellipse([24, 24, 40, 40], fill='white')
        return image
    
    def _quick_connection_test(self, icon=None, item=None):
        """Szybki test połączenia z tray - Z ANIMACJĄ!"""
        def test_thread():
            try:
                # Utwórz tymczasowego klienta
                test_client = HomeAssistantClient()
                
                # Uruchom test w nowej pętli asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    success, message = loop.run_until_complete(test_client.test_connection())
                    
                    # Pokaż wynik w logach (jak wcześniej)
                    if success:
                        logger.info(f"Test połączenia: ✅ {message}")
                        print(f"✅ Test połączenia: {message}")
                        
                        # NOWY: Pokaż animację sukcesu
                        if self.animation_server:
                            self.animation_server.show_success("Connection successful", duration=3.0)
                    else:
                        logger.error(f"Test połączenia: ❌ {message}")
                        print(f"❌ Test połączenia: {message}")
                        
                        # NOWY: Pokaż animację błędu
                        if self.animation_server:
                            self.animation_server.show_error(f"Connection failed", duration=5.0)
                    
                finally:
                    loop.close()
                    
            except Exception as e:
                error_msg = f"Błąd testu: {str(e)}"
                logger.error(error_msg)
                print(f"❌ {error_msg}")
                
                # NOWY: Pokaż animację błędu dla wyjątków
                if self.animation_server:
                    self.animation_server.show_error("Test error", duration=5.0)
        
        threading.Thread(target=test_thread, daemon=True).start()
    
    def _show_pipelines_info(self, icon=None, item=None):
        """Pokaż informacje o dostępnych pipeline'ach - POPRAWIONA WERSJA."""
        def pipelines_thread():
            try:
                # Utwórz tymczasowego klienta
                test_client = HomeAssistantClient()
                
                # Uruchom połączenie w nowej pętli asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    success = loop.run_until_complete(test_client.connect())
                    
                    if success:
                        pipelines = test_client.get_available_pipelines()
                        current_pipeline = utils.get_env("HA_PIPELINE_ID", "(domyślny)")
                        
                        print(f"\n=== DOSTĘPNE PIPELINE'Y ({len(pipelines)}) ===")
                        print(f"Aktualnie używany: {current_pipeline}")
                        print("-" * 50)
                        
                        if not pipelines:
                            print("Brak dostępnych pipeline'ów lub błąd połączenia")
                        else:
                            for i, pipeline in enumerate(pipelines, 1):
                                # NAPRAWIONE: Sprawdź czy pipeline to string czy obiekt
                                if isinstance(pipeline, str):
                                    # Pipeline to po prostu string (ID lub nazwa)
                                    name = pipeline
                                    pipeline_id = pipeline
                                    language = "nieznany"
                                elif isinstance(pipeline, dict):
                                    # Pipeline to obiekt - używaj .get()
                                    name = pipeline.get("name", "Bez nazwy")
                                    pipeline_id = pipeline.get("id", "")
                                    language = pipeline.get("language", "nieznany")
                                else:
                                    # Nieznany typ - konwertuj na string
                                    name = str(pipeline)
                                    pipeline_id = str(pipeline)
                                    language = "nieznany"
                                
                                # Sprawdź czy to aktualnie używany pipeline
                                current_marker = " ← AKTUALNY" if pipeline_id == current_pipeline else ""
                                
                                print(f"{i}. {name}")
                                print(f"   ID: {pipeline_id}{current_marker}")
                                if language != "nieznany":
                                    print(f"   Język: {language}")
                                print()
                            
                            print("=" * 50)
                            print("Użyj 'Ustawienia' aby zmienić pipeline.")
                            
                            # BONUS: Podpowiedź jak skopiować ID
                            if len(pipelines) > 1:
                                print("\n💡 WSKAZÓWKA:")
                                print("Skopiuj ID wybranego pipeline'u i wklej w ustawieniach aplikacji.")
                                
                    else:
                        print("❌ Nie można połączyć się z Home Assistant")
                        print("Sprawdź ustawienia połączenia.")
                    
                finally:
                    loop.close()
                    
            except Exception as e:
                error_msg = f"Błąd pobierania pipeline'ów: {str(e)}"
                logger.error(error_msg)
                print(f"❌ {error_msg}")
                
                # DODATKOWE DEBUG INFO
                print(f"📋 DEBUG: Typ błędu: {type(e).__name__}")
                if hasattr(e, '__traceback__'):
                    import traceback
                    print("📋 Stos wywołań:")
                    traceback.print_exc()
        
        threading.Thread(target=pipelines_thread, daemon=True).start()

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
        
        icon_path = os.path.join(os.path.dirname(__file__), 'img', 'icon.ico')
        # Pobierz rozmiar okna z ustawień
        window_width = utils.get_env("WINDOW_WIDTH", 400, int)
        window_height = utils.get_env("WINDOW_HEIGHT", 400, int)
        
        # Utworzenie okna webview - ukryte z paska zadań
        self.window = webview.create_window(
            'HA Assist',
            index_path,
            width=window_width,
            height=window_height,
            resizable=False,
            fullscreen=False,
            minimized=False,
            on_top=True,
            shadow=False,
            frameless=True,
            transparent=True,
            y=10
        )
        
        logger.info(f"Webview window skonfigurowane ({window_width}x{window_height}, ukryte z paska zadań)")
        return True

    def open_settings(self, icon=None, item=None):
        """Otwórz ulepszone okno ustawień."""
        logger.info("Otwieranie ulepszonych ustawień...")
        
        try:
            from improved_settings_dialog import show_improved_settings
            show_improved_settings(self.animation_server)
            
        except ImportError as e:
            logger.error(f"Nie znaleziono improved_settings_dialog.py: {e}")
            
            # Emergency fallback - przynajmniej powiedz użytkownikowi co zrobić
            import tkinter as tk
            from tkinter import messagebox
            
            root = tk.Tk()
            root.withdraw()  # Ukryj główne okno
            
            messagebox.showerror(
                "Błąd ustawień", 
                "Nie znaleziono pliku improved_settings_dialog.py!\n\n"
                "Utwórz ten plik w folderze aplikacji\n"
                "lub sprawdź czy wszystkie pliki zostały skopiowane."
            )
            root.destroy()
            
        except Exception as e:
            logger.exception(f"Błąd otwierania ustawień: {e}")
            
            # Emergency fallback
            import tkinter as tk
            from tkinter import messagebox
            
            root = tk.Tk()
            root.withdraw()
            
            messagebox.showerror(
                "Błąd ustawień", 
                f"Wystąpił błąd podczas otwierania ustawień:\n\n{str(e)}\n\n"
                "Sprawdź logi aplikacji dla szczegółów."
            )
            root.destroy()

    async def process_voice_command(self):
        """Ulepszone przetwarzanie komendy głosowej z walidacją pipeline'u."""
        try:
            # Zmień stan na nasłuchiwanie
            self.animation_server.change_state("listening")
            
            # Inicjalizacja klientów
            self.ha_client = HomeAssistantClient()  # Już ulepszona wersja
            self.audio_manager = AudioManager()
            
            # NOWOŚĆ: Pre-validation pipeline'u
            pipeline_id = utils.get_env("HA_PIPELINE_ID")
            if pipeline_id:
                logger.info(f"Sprawdzam dostępność pipeline'u: {pipeline_id}")
            
            # Inicjalizacja mikrofonu
            self.audio_manager.init_audio()
            
            # Połączenie z Home Assistant (już z obsługą pipeline'ów)
            if not await self.ha_client.connect():
                logger.error("Nie udało się połączyć z Home Assistant")
                self.animation_server.change_state("error", "Nie można połączyć się z Home Assistant")
                await asyncio.sleep(8)
                self.animation_server.change_state("hidden")
                return False
            
            logger.info("Połączono z Home Assistant")
            
            # NOWOŚĆ: Sprawdź czy wybrany pipeline jest dostępny
            if pipeline_id and not self.ha_client.validate_pipeline_id(pipeline_id):
                logger.warning(f"Pipeline '{pipeline_id}' nie jest dostępny - używam domyślnego")
                # Możesz tutaj wyświetlić ostrzeżenie lub zmienić na błąd
                
            # Uruchomienie pipeline Assist z timeout
            if not await self.ha_client.start_assist_pipeline(timeout_seconds=30):
                logger.error("Nie udało się uruchomić pipeline Assist")
                self.animation_server.change_state("error", "Nie można uruchomić asystenta głosowego")
                await asyncio.sleep(8)
                self.animation_server.change_state("hidden")
                return False
            
            logger.info("Pipeline Assist uruchomiony pomyślnie")
            
            print("\n=== MÓWISZ ===")
            print("(Oczekiwanie na głos, mów do mikrofonu...)")
            
            # Rejestracja funkcji callback dla fragmentów audio
            async def on_audio_chunk(audio_chunk):
                # Wyślij dane audio do animacji
                self.animation_server.send_audio_data(audio_chunk)
                # Wyślij do Home Assistant (z obsługą błędów)
                success = await self.ha_client.send_audio_chunk(audio_chunk)
                if not success:
                    logger.warning("Błąd wysyłania audio chunk")
            
            async def on_audio_end():
                # Zmień stan na przetwarzanie Z MAŁYM OPÓŹNIENIEM
                logger.info("=== PRZECHODZĘ DO PRZETWARZANIA ===")
                self.animation_server.change_state("processing")
                
                # KRÓTKIE OPÓŹNIENIE - żeby animacja processing była widoczna
                await asyncio.sleep(0.8)
                
                success = await self.ha_client.end_audio()
                if not success:
                    logger.warning("Błąd kończenia audio")
            
            # Rozpoczęcie nagrywania
            if await self.audio_manager.record_audio(on_audio_chunk, on_audio_end):
                logger.info("Audio wysłane pomyślnie")
                
                # Odbieranie odpowiedzi z konfiguracją timeout
                logger.info("=== ODBIERAM ODPOWIEDŹ ===")
                results = await self.ha_client.receive_response(timeout_seconds=45)
                
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
                            
                            # SPECJALNE OBSŁUGI DLA TYPOWYCH BŁĘDÓW
                            if error_code == "stt-stream-failed":
                                full_error_message = "Nie rozpoznano mowy. Spróbuj ponownie."
                            elif error_code == "intent-failed":
                                full_error_message = "Nie rozumiem polecenia. Powiedz jaśniej."
                            elif error_code == "pipeline-not-found":
                                full_error_message = "Błąd konfiguracji. Sprawdź ustawienia."
                            
                            self.animation_server.change_state("error", full_error_message)
                            await asyncio.sleep(8)
                            self.animation_server.change_state("hidden")
                            
                            error_found = True
                            break
                
                if not error_found:
                    # NIE MA BŁĘDU - NORMALNA ODPOWIEDŹ
                    response = self.ha_client.extract_assistant_response(results)
                    
                    if response and response != "Brak odpowiedzi od asystenta":
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
                            success = utils.play_audio_from_url(audio_url, self.ha_client.host, self.animation_server)
                            if not success:
                                logger.warning("Nie udało się odtworzyć audio odpowiedzi")
                        
                        # Powrót do stanu hidden po 3 sekundach
                        await asyncio.sleep(3)
                        self.animation_server.change_state("hidden")
                    else:
                        print("\nBrak odpowiedzi od asystenta lub błąd przetwarzania.")
                        self.animation_server.change_state("error", "Asystent nie odpowiedział")
                        await asyncio.sleep(8)
                        self.animation_server.change_state("hidden")
            else:
                logger.error("Nie udało się nagrać i wysłać audio")
                self.animation_server.change_state("error", "Błąd nagrywania audio")
                await asyncio.sleep(8)
                self.animation_server.change_state("hidden")
                
        except asyncio.TimeoutError:
            logger.error("Timeout podczas przetwarzania komendy głosowej")
            self.animation_server.change_state("error", "Timeout - asystent nie odpowiada")
            await asyncio.sleep(8)
            self.animation_server.change_state("hidden")
            
        except Exception as e:
            logger.exception(f"Wystąpił błąd podczas przetwarzania: {str(e)}")
            
            # WYCIĄGNIJ INFORMACJĘ O BŁĘDZIE I PRZEKAŻ DO ANIMACJI
            error_msg = str(e)
            if len(error_msg) > 80:  # Ogranicz długość wiadomości błędu
                error_msg = error_msg[:77] + "..."
            
            self.animation_server.change_state("error", f"Błąd: {error_msg}")
            
            # Po błędzie też wracamy do hidden - WYDŁUŻONO CZAS
            await asyncio.sleep(10)
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
        """ORYGINALNA metoda run() - ZACHOWANA!"""
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


# NOWOŚĆ: Funkcja pomocnicza do walidacji konfiguracji
def validate_configuration():
    """Waliduje konfigurację aplikacji i zwraca listę problemów."""
    issues = []
    
    # Sprawdź podstawowe ustawienia
    host = utils.get_env("HA_HOST")
    token = utils.get_env("HA_TOKEN")
    
    if not host:
        issues.append("Brak adresu serwera Home Assistant (HA_HOST)")
    
    if not token:
        issues.append("Brak tokena dostępu (HA_TOKEN)")
    
    # Sprawdź ustawienia audio
    sample_rate = utils.get_env("HA_SAMPLE_RATE", 16000, int)
    if sample_rate not in [8000, 16000, 22050, 44100, 48000]:
        issues.append(f"Nietypowa częstotliwość próbkowania: {sample_rate}Hz")
    
    frame_duration = utils.get_env("HA_FRAME_DURATION_MS", 30, int)
    if frame_duration not in [10, 20, 30]:
        issues.append(f"Nieprawidłowa długość ramki VAD: {frame_duration}ms (dozwolone: 10, 20, 30)")
    
    vad_mode = utils.get_env("HA_VAD_MODE", 3, int)
    if vad_mode < 0 or vad_mode > 3:
        issues.append(f"Nieprawidłowy tryb VAD: {vad_mode} (dozwolone: 0-3)")
    
    # Sprawdź port animacji
    try:
        anim_port = utils.get_env("ANIMATION_PORT", 8765, int)
        if anim_port < 1024 or anim_port > 65535:
            issues.append(f"Nieprawidłowy port animacji: {anim_port} (dozwolone: 1024-65535)")
    except (ValueError, TypeError):
        issues.append("Port animacji musi być liczbą")
    
    return issues


def main():
    """Główna funkcja aplikacji z walidacją konfiguracji."""
    print("=== HA ASSIST DESKTOP ===")
    print("Uruchamianie aplikacji...")
    
    # Znajdź plik .env i wyświetl jego ścieżkę
    possible_paths = [
        os.path.join(os.path.dirname(__file__), '.env'),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),
        '.env'
    ]
    
    env_found = False
    for path in possible_paths:
        if os.path.exists(path):
            abs_path = os.path.abspath(path)
            print(f"📄 UŻYWAM PLIKU .ENV: {abs_path}")
            env_found = True
            
            # Wyświetl zawartość pliku (bez tokenów)
            with open(abs_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Ukryj token w wyświetlaniu
            lines = content.split('\n')
            filtered_lines = []
            for line in lines:
                if line.startswith('HA_TOKEN=') and len(line) > 20:
                    filtered_lines.append(f"HA_TOKEN=***UKRYTY*** (długość: {len(line.split('=', 1)[1])} znaków)")
                else:
                    filtered_lines.append(line)
            
            print("ZAWARTOŚĆ PLIKU .ENV:")
            print('\n'.join(filtered_lines))
            print("-" * 50)
            break
    
    if not env_found:
        print("⚠️  BRAK PLIKU .ENV - używam domyślnych ustawień")
        print("Uruchom aplikację i przejdź do 'Ustawienia' aby skonfigurować połączenie.")
        print("-" * 50)
    
    # Walidacja konfiguracji
    print("🔍 SPRAWDZAM KONFIGURACJĘ...")
    config_issues = validate_configuration()
    
    if config_issues:
        print("⚠️  ZNALEZIONE PROBLEMY KONFIGURACJI:")
        for issue in config_issues:
            print(f"   • {issue}")
        print("\nAplikacja może nie działać poprawnie.")
        print("Przejdź do 'Ustawienia' aby naprawić problemy.")
    else:
        print("✅ Konfiguracja wygląda poprawnie")
    
    print("-" * 50)
    
    # Wyświetl najważniejsze ustawienia (bez tokena)
    print("📋 KLUCZOWE USTAWIENIA:")
    important_settings = {
        'HA_HOST': utils.get_env('HA_HOST', 'BRAK'),
        'HA_PIPELINE_ID': utils.get_env('HA_PIPELINE_ID', '(domyślny)'),
        'HA_HOTKEY': utils.get_env('HA_HOTKEY', 'ctrl+shift+h'),
        'HA_VAD_MODE': utils.get_env('HA_VAD_MODE', '3'),
        'DEBUG': utils.get_env('DEBUG', 'false')
    }
    
    for key, value in important_settings.items():
        print(f"   {key} = {value}")
    
    token_length = len(utils.get_env('HA_TOKEN', ''))
    if token_length > 0:
        print(f"   HA_TOKEN = ***UKRYTY*** ({token_length} znaków)")
    else:
        print(f"   HA_TOKEN = BRAK")
    
    print("=" * 50)
    
    # Uruchom aplikację
    app = HAAssistApp()
    app.run()


if __name__ == "__main__":
    main()