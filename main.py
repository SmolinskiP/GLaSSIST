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
        self.settings_window = None
        self.is_running = False
        self.tray_icon = None
        self.window_visible = True
        
    def create_tray_icon(self):
        """Utworzenie ikony w system tray."""
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
                image = Image.new('RGB', (64, 64), color='black')
                draw = ImageDraw.Draw(image)
                draw.ellipse([8, 8, 56, 56], fill='#4fc3f7', outline='white', width=2)
                draw.ellipse([24, 24, 40, 40], fill='white')
        else:
            logger.warning(f"Brak pliku ikony: {icon_path}")
            # Prosta ikona jako fallback
            image = Image.new('RGB', (64, 64), color='black')
            draw = ImageDraw.Draw(image)
            draw.ellipse([8, 8, 56, 56], fill='#4fc3f7', outline='white', width=2)
            draw.ellipse([24, 24, 40, 40], fill='white')
        
        # Menu kontekstowe
        menu = pystray.Menu(
            item('Aktywuj głos', self.trigger_voice_command),
            pystray.Menu.SEPARATOR,
            item('Ustawienia', self.open_settings),
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
        """Otwórz okno ustawień w Tkinter zamiast webview."""
        import tkinter as tk
        from tkinter import ttk, messagebox
        
        logger.info("Otwieranie okna ustawień (Tkinter)...")
        
        # Funkcja do zapisywania ustawień
        def save_config():
            # Pobierz aktualne wartości z interfejsu
            new_settings = {
                'HA_HOST': host_entry.get().strip(),
                'HA_TOKEN': token_entry.get().strip(),
                'HA_PIPELINE_ID': pipeline_entry.get().strip(),
                'HA_HOTKEY': hotkey_var.get(),
                'HA_SILENCE_THRESHOLD_SEC': str(round(silence_scale.get(), 1)),
                'HA_VAD_MODE': str(int(vad_mode_scale.get())),
                'DEBUG': 'true' if debug_var.get() else 'false',
                
                # Ukryte ustawienia - bierzemy z aktualnych wartości
                'HA_SAMPLE_RATE': utils.get_env('HA_SAMPLE_RATE', '16000'),
                'HA_CHANNELS': utils.get_env('HA_CHANNELS', '1'),
                'HA_FRAME_DURATION_MS': utils.get_env('HA_FRAME_DURATION_MS', '30'),
                'HA_CHUNK_SIZE': utils.get_env('HA_CHUNK_SIZE', '480'),
                'HA_PADDING_MS': utils.get_env('HA_PADDING_MS', '300'),
                'ANIMATION_PORT': utils.get_env('ANIMATION_PORT', '8765')
            }
            
            # Sprawdź czy host i token są podane
            if not new_settings['HA_HOST']:
                messagebox.showerror("Błąd", "Adres serwera Home Assistant jest wymagany!")
                return
                
            if not new_settings['HA_TOKEN']:
                messagebox.showerror("Błąd", "Token dostępu jest wymagany!")
                return
            
            try:
                # Znajdź plik .env
                env_path = None
                possible_paths = [
                    os.path.join(os.path.dirname(__file__), '.env'),
                    os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),
                    '.env'
                ]
                
                for path in possible_paths:
                    if os.path.exists(path):
                        env_path = path
                        break
                        
                # Jeśli nie znaleziono pliku .env, utwórz nowy w głównym katalogu
                if not env_path:
                    env_path = possible_paths[0]
                
                # Przygotuj zawartość pliku .env
                env_content = "# Ustawienia Home Assistant\n"
                env_content += f"HA_HOST={new_settings['HA_HOST']}\n"
                env_content += f"HA_TOKEN={new_settings['HA_TOKEN']}\n"
                if new_settings['HA_PIPELINE_ID']:
                    env_content += f"HA_PIPELINE_ID={new_settings['HA_PIPELINE_ID']}\n"
                
                env_content += "\n# Ustawienia audio\n"
                env_content += f"HA_SAMPLE_RATE={new_settings['HA_SAMPLE_RATE']}\n"
                env_content += f"HA_CHANNELS={new_settings['HA_CHANNELS']}\n"
                env_content += f"HA_FRAME_DURATION_MS={new_settings['HA_FRAME_DURATION_MS']}\n"
                env_content += f"HA_CHUNK_SIZE={new_settings['HA_CHUNK_SIZE']}\n"
                env_content += f"HA_PADDING_MS={new_settings['HA_PADDING_MS']}\n"
                env_content += f"HA_SILENCE_THRESHOLD_SEC={new_settings['HA_SILENCE_THRESHOLD_SEC']}\n"
                
                env_content += "\n# Ustawienia VAD\n"
                env_content += f"HA_VAD_MODE={new_settings['HA_VAD_MODE']}\n"
                
                env_content += f"\nHA_HOTKEY={new_settings['HA_HOTKEY']}\n"
                env_content += f"DEBUG={new_settings['DEBUG']}\n"
                
                env_content += "\n# Animation Server Configuration\n"
                env_content += f"ANIMATION_PORT={new_settings['ANIMATION_PORT']}\n"
                
                # Zapisz plik
                with open(env_path, 'w', encoding='utf-8') as f:
                    f.write(env_content)
                
                messagebox.showinfo("Sukces", f"Ustawienia zostały zapisane w {os.path.basename(env_path)}\nZresetuj aplikację aby zastosować zmiany.")
                root.destroy()
                
            except Exception as e:
                logger.exception(f"Błąd zapisu ustawień: {e}")
                messagebox.showerror("Błąd", f"Nie udało się zapisać ustawień: {str(e)}")
        
        # Załaduj aktualne ustawienia
        current_settings = {
            'HA_HOST': utils.get_env('HA_HOST', 'localhost:8123'),
            'HA_TOKEN': utils.get_env('HA_TOKEN', ''),
            'HA_PIPELINE_ID': utils.get_env('HA_PIPELINE_ID', ''),
            'HA_HOTKEY': utils.get_env('HA_HOTKEY', 'ctrl+shift+h'),
            'HA_VAD_MODE': utils.get_env('HA_VAD_MODE', 3, int),
            'HA_SILENCE_THRESHOLD_SEC': utils.get_env('HA_SILENCE_THRESHOLD_SEC', 0.8, float),
            'DEBUG': utils.get_env('DEBUG', False, bool)
        }
        # Tworzenie głównego okna
        root = tk.Tk()
        root.title("HA Assist - Ustawienia")
        root.geometry("600x400")
        root.resizable(True, True)
        
        icon_path = os.path.join(os.path.dirname(__file__), 'img', 'icon.ico')
        if os.path.exists(icon_path):
            try:
                root.iconbitmap(icon_path)
                logger.info(f"Ustawiono ikonę: {icon_path}")
            except Exception as e:
                logger.error(f"Błąd ustawienia ikony: {e}")
        # Styl
        style = ttk.Style()
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))
        
        # Główny kontener
        main_frame = ttk.Frame(root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Nagłówek
        header_label = ttk.Label(main_frame, text="Ustawienia Home Assistant Assist", style="Header.TLabel")
        header_label.pack(pady=(0, 20))
        
        # Ramka na ustawienia
        settings_frame = ttk.Frame(main_frame)
        settings_frame.pack(fill=tk.BOTH, expand=True)
        
        # Ustawienia Home Assistant
        ttk.Label(settings_frame, text="Adres serwera Home Assistant:").grid(row=0, column=0, sticky=tk.W, pady=5)
        host_entry = ttk.Entry(settings_frame, width=40)
        host_entry.grid(row=0, column=1, sticky=tk.W+tk.E, pady=5, padx=5)
        host_entry.insert(0, current_settings['HA_HOST'])
        
        ttk.Label(settings_frame, text="Token dostępu:").grid(row=1, column=0, sticky=tk.W, pady=5)
        token_entry = ttk.Entry(settings_frame, width=40, show="•")
        token_entry.grid(row=1, column=1, sticky=tk.W+tk.E, pady=5, padx=5)
        token_entry.insert(0, current_settings['HA_TOKEN'])
        
        ttk.Label(settings_frame, text="ID Pipeline (opcjonalnie):").grid(row=2, column=0, sticky=tk.W, pady=5)
        pipeline_entry = ttk.Entry(settings_frame, width=40)
        pipeline_entry.grid(row=2, column=1, sticky=tk.W+tk.E, pady=5, padx=5)
        pipeline_entry.insert(0, current_settings['HA_PIPELINE_ID'])
        
        # Skrót klawiszowy
        ttk.Label(settings_frame, text="Skrót klawiszowy:").grid(row=3, column=0, sticky=tk.W, pady=5)
        hotkey_var = tk.StringVar(value=current_settings['HA_HOTKEY'])
        hotkey_combo = ttk.Combobox(settings_frame, textvariable=hotkey_var, state="readonly", width=20)
        hotkey_combo["values"] = ("ctrl+shift+h", "ctrl+shift+g", "ctrl+alt+h", "ctrl+shift+a", "alt+space", "ctrl+shift+space")
        hotkey_combo.grid(row=3, column=1, sticky=tk.W, pady=5, padx=5)
        
        # Tryb VAD
        ttk.Label(settings_frame, text="Czułość detekcji głosu:").grid(row=4, column=0, sticky=tk.W, pady=5)
        vad_frame = ttk.Frame(settings_frame)
        vad_frame.grid(row=4, column=1, sticky=tk.W, pady=5, padx=5)
        
        vad_mode_scale = ttk.Scale(vad_frame, from_=0, to=3, orient=tk.HORIZONTAL, length=200)
        vad_mode_scale.set(current_settings['HA_VAD_MODE'])
        vad_mode_scale.pack(side=tk.LEFT)
        
        vad_mode_value = ttk.Label(vad_frame, text=str(current_settings['HA_VAD_MODE']), width=3)
        vad_mode_value.pack(side=tk.LEFT, padx=5)
        
        def update_vad_mode(event=None):
            vad_mode_value.config(text=str(int(vad_mode_scale.get())))
        vad_mode_scale.bind("<Motion>", update_vad_mode)
        vad_mode_scale.bind("<ButtonRelease-1>", update_vad_mode)
        
        # Próg ciszy
        ttk.Label(settings_frame, text="Próg ciszy (sekundy):").grid(row=5, column=0, sticky=tk.W, pady=5)
        silence_frame = ttk.Frame(settings_frame)
        silence_frame.grid(row=5, column=1, sticky=tk.W, pady=5, padx=5)
        
        silence_scale = ttk.Scale(silence_frame, from_=0.3, to=3.0, orient=tk.HORIZONTAL, length=200)
        silence_scale.set(current_settings['HA_SILENCE_THRESHOLD_SEC'])
        silence_scale.pack(side=tk.LEFT)
        
        silence_value = ttk.Label(silence_frame, text=str(current_settings['HA_SILENCE_THRESHOLD_SEC']) + "s", width=4)
        silence_value.pack(side=tk.LEFT, padx=5)
        
        def update_silence(event=None):
            value = round(silence_scale.get(), 1)
            silence_value.config(text=f"{value}s")
        silence_scale.bind("<Motion>", update_silence)
        silence_scale.bind("<ButtonRelease-1>", update_silence)
        
        # Tryb debugowania
        debug_var = tk.BooleanVar(value=current_settings['DEBUG'])
        debug_check = ttk.Checkbutton(settings_frame, text="Tryb debugowania", variable=debug_var)
        debug_check.grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # Przyciski na dole
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=15, fill=tk.X)
        
        save_button = ttk.Button(button_frame, text="Zapisz ustawienia", command=save_config)
        save_button.pack(side=tk.RIGHT, padx=5)
        
        cancel_button = ttk.Button(button_frame, text="Anuluj", command=root.destroy)
        cancel_button.pack(side=tk.RIGHT, padx=5)
        
        # Ustawienie okna na wierzchu
        root.attributes('-topmost', True)
        root.update()
        root.attributes('-topmost', False)
        
        # Centrum ekranu
        root.update_idletasks()
        width = root.winfo_width()
        height = root.winfo_height()
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f'+{x}+{y}')
        
        # Uruchomienie pętli głównej
        root.mainloop()

    def save_env_settings(self, settings):
        """Zapisz ustawienia do pliku .env."""
        try:
            # Znajdź gdzie jest (lub gdzie powinien być) plik .env
            possible_paths = [
                os.path.join(os.path.dirname(__file__), '.env'),  # Katalog główny aplikacji
                os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),  # Katalog wyżej
                '.env'  # Względna ścieżka
            ]
            
            env_path = None
            # Najpierw sprawdź czy istnieje
            for path in possible_paths:
                if os.path.exists(path):
                    env_path = path
                    logger.info(f"Znaleziono istniejący plik .env w: {path}")
                    break
            
            # Jeśli nie istnieje, użyj pierwszej ścieżki (katalog główny)
            if not env_path:
                env_path = possible_paths[0]
                logger.info(f"Tworzę nowy plik .env w: {env_path}")
            
            # Przygotuj zawartość pliku .env
            env_lines = []
            for key, value in settings.items():
                if value and str(value).strip():
                    # Zabezpieczenie przed spacjami w tokenach
                    clean_value = str(value).strip()
                    env_lines.append(f"{key}={clean_value}")
            
            # Upewnij się że katalog istnieje
            os.makedirs(os.path.dirname(env_path), exist_ok=True)
            
            # Zapisz do pliku
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(env_lines) + '\n')
            
            logger.info(f"Ustawienia zapisane do: {env_path} ({len(env_lines)} linii)")
            return {'success': True, 'message': f'Ustawienia zapisane do {os.path.basename(env_path)}'}
            
        except Exception as e:
            logger.error(f"Błąd zapisu ustawień: {e}")
            return {'success': False, 'message': f'Błąd zapisu: {str(e)}'}
    
    def test_ha_connection(self, host, token):
        """Testuj połączenie z Home Assistant."""
        try:
            import asyncio
            import websockets
            import json
            
            async def test_connection():
                protocol = "ws" if host.startswith(('localhost', '127.0.0.1', '192.168.', '10.', '172.')) else "wss"
                uri = f"{protocol}://{host}/api/websocket"
                
                try:
                    websocket = await websockets.connect(uri, timeout=5)
                    
                    # Odbierz wiadomość auth_required
                    auth_msg = await asyncio.wait_for(websocket.recv(), timeout=5)
                    auth_data = json.loads(auth_msg)
                    
                    if auth_data.get("type") != "auth_required":
                        return False, "Nieoczekiwana odpowiedź z serwera"
                    
                    # Wyślij token
                    await websocket.send(json.dumps({
                        "type": "auth",
                        "access_token": token
                    }))
                    
                    # Odbierz odpowiedź
                    result_msg = await asyncio.wait_for(websocket.recv(), timeout=5)
                    result_data = json.loads(result_msg)
                    
                    await websocket.close()
                    
                    if result_data.get("type") == "auth_ok":
                        return True, "Połączenie działa poprawnie!"
                    else:
                        return False, "Błędny token dostępu"
                        
                except asyncio.TimeoutError:
                    return False, "Timeout - serwer nie odpowiada"
                except Exception as e:
                    return False, f"Błąd połączenia: {str(e)}"
            
            # Uruchom test w nowej pętli asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                success, message = loop.run_until_complete(test_connection())
                return {'success': success, 'message': message}
            finally:
                loop.close()
                
        except Exception as e:
            logger.error(f"Błąd testu połączenia: {e}")
            return {'success': False, 'message': f'Błąd testu: {str(e)}'}
        """Testuj połączenie z Home Assistant."""
        try:
            import asyncio
            import websockets
            import json
            
            async def test_connection():
                protocol = "ws" if host.startswith(('localhost', '127.0.0.1', '192.168.', '10.', '172.')) else "wss"
                uri = f"{protocol}://{host}/api/websocket"
                
                try:
                    websocket = await websockets.connect(uri, timeout=5)
                    
                    # Odbierz wiadomość auth_required
                    auth_msg = await asyncio.wait_for(websocket.recv(), timeout=5)
                    auth_data = json.loads(auth_msg)
                    
                    if auth_data.get("type") != "auth_required":
                        return False, "Nieoczekiwana odpowiedź z serwera"
                    
                    # Wyślij token
                    await websocket.send(json.dumps({
                        "type": "auth",
                        "access_token": token
                    }))
                    
                    # Odbierz odpowiedź
                    result_msg = await asyncio.wait_for(websocket.recv(), timeout=5)
                    result_data = json.loads(result_msg)
                    
                    await websocket.close()
                    
                    if result_data.get("type") == "auth_ok":
                        return True, "Połączenie działa poprawnie!"
                    else:
                        return False, "Błędny token dostępu"
                        
                except asyncio.TimeoutError:
                    return False, "Timeout - serwer nie odpowiada"
                except Exception as e:
                    return False, f"Błąd połączenia: {str(e)}"
            
            # Uruchom test w nowej pętli asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                success, message = loop.run_until_complete(test_connection())
                return {'success': success, 'message': message}
            finally:
                loop.close()
                
        except Exception as e:
            logger.error(f"Błąd testu połączenia: {e}")
            return {'success': False, 'message': f'Błąd testu: {str(e)}'}

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
    # Znajdź plik .env i wyświetl jego ścieżkę
    possible_paths = [
        os.path.join(os.path.dirname(__file__), '.env'),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),
        '.env'
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            abs_path = os.path.abspath(path)
            print(f"UŻYWAM PLIKU .ENV: {abs_path}")
            
            # Wyświetl zawartość pliku
            with open(abs_path, 'r', encoding='utf-8') as f:
                content = f.read()
            print("ZAWARTOŚĆ PLIKU .ENV:")
            print(content)
            print("----------------------------------")
            break
    
    # Wyświetl wartości zmiennych środowiskowych
    print("WARTOŚCI ZMIENNYCH ŚRODOWISKOWYCH:")
    for key in ['HA_HOST', 'HA_TOKEN', 'HA_HOTKEY', 'HA_VAD_MODE', 'DEBUG']:
        value = os.environ.get(key, "BRAK")
        print(f"{key} = {value}")
    print("----------------------------------")
    
    app = HAAssistApp()
    app.run()

if __name__ == "__main__":
    main()