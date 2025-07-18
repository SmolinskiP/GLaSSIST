"""
Enhanced settings dialog with pipeline selection for Home Assistant
"""
import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
import threading
import os
import webbrowser
import utils
import subprocess
import platform
from client import HomeAssistantClient
from audio import AudioManager

logger = utils.setup_logger()

class ImprovedSettingsDialog:
    """Enhanced settings dialog with connection testing and pipeline selection."""
    
    def __init__(self, animation_server=None):
        self.root = None
        self.pipelines_data = []
        self.test_client = None
        self.animation_server = animation_server
        
    def _refresh_microphones(self):
        """Załaduj dostępne mikrofony do listy."""
        try:
            # Tymczasowy AudioManager tylko do pobrania listy mikrofonów
            temp_audio = AudioManager()
            temp_audio.init_audio()
            
            microphones = temp_audio.get_available_microphones()
            temp_audio.close_audio()
            
            # Przygotuj opcje dla combobox
            mic_options = ["(automatic)"]  # Opcja domyślna
            mic_mapping = {"(automatic)": -1}
            
            for mic in microphones:
                display_name = f"{mic['name']} (ID: {mic['index']})"
                mic_options.append(display_name)
                mic_mapping[display_name] = mic['index']
            
            self.mic_combo['values'] = mic_options
            self.mic_mapping = mic_mapping
            
            # Ustaw aktualny wybór
            current_mic_index = utils.get_env("HA_MICROPHONE_INDEX", -1, int)
            if current_mic_index == -1:
                self.mic_var.set("(automatic)")
            else:
                # Znajdź odpowiadającą opcję
                for option, index in mic_mapping.items():
                    if index == current_mic_index:
                        self.mic_var.set(option)
                        break
                else:
                    self.mic_var.set(f"⚠️ Unknown: {current_mic_index}")
            
            logger.info(f"Loaded {len(microphones)} microphones")
            
        except Exception as e:
            logger.error(f"Failed to load microphones: {e}")
            self.mic_combo['values'] = ["(automatic)", "Error loading microphones"]
            self.mic_var.set("(automatic)")
            self.mic_mapping = {"(automatic)": -1}

    def show_settings(self):
        """Display settings dialog with proper cleanup."""
        current_settings = {
            'HA_HOST': utils.get_env('HA_HOST', 'localhost:8123'),
            'HA_TOKEN': utils.get_env('HA_TOKEN', ''),
            'HA_PIPELINE_ID': utils.get_env('HA_PIPELINE_ID', ''),
            'HA_HOTKEY': utils.get_env('HA_HOTKEY', 'ctrl+shift+h'),
            'HA_VAD_MODE': utils.get_env('HA_VAD_MODE', 3, int),
            'HA_SILENCE_THRESHOLD_SEC': utils.get_env('HA_SILENCE_THRESHOLD_SEC', 0.8, float),
            'HA_SOUND_FEEDBACK': utils.get_env('HA_SOUND_FEEDBACK', 'true'),
            'DEBUG': utils.get_env('DEBUG', 'false'),
            'HA_SILENCE_THRESHOLD_SEC': utils.get_env('HA_SILENCE_THRESHOLD_SEC', 0.8, float),
            'HA_WAKE_WORD_ENABLED': utils.get_env('HA_WAKE_WORD_ENABLED', 'false'),
            'HA_WAKE_WORD_MODELS': utils.get_env('HA_WAKE_WORD_MODELS', 'alexa'),
            'HA_WAKE_WORD_THRESHOLD': utils.get_env('HA_WAKE_WORD_THRESHOLD', 0.5, float),
            'HA_WAKE_WORD_VAD_THRESHOLD': utils.get_env('HA_WAKE_WORD_VAD_THRESHOLD', 0.3, float),
            'HA_WAKE_WORD_NOISE_SUPPRESSION': utils.get_env('HA_WAKE_WORD_NOISE_SUPPRESSION', 'false'),
        }
        
        # Pause wake word detection temporarily for better GUI responsiveness
        wake_word_was_paused = False
        try:
            # Try to pause wake word detection if animation_server is available
            if self.animation_server and hasattr(self.animation_server, 'pause_wake_word_detection'):
                self.animation_server.pause_wake_word_detection()
                wake_word_was_paused = True
                logger.info("Wake word detection paused for settings dialog")
        except Exception as e:
            logger.debug(f"Could not pause wake word detection: {e}")
        
        try:
            self.root = tk.Tk()
            self.root.title("GLaSSIST - Settings")
            self.root.geometry("750x700")
            self.root.resizable(True, True)
            
            # Add proper cleanup on window close
            self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
            
            icon_path = os.path.join(os.path.dirname(__file__), 'img', 'icon.ico')
            if os.path.exists(icon_path):
                try:
                    self.root.iconbitmap(icon_path)
                except Exception as e:
                    logger.error(f"Error setting icon: {e}")
            
            style = ttk.Style()
            style.configure("TLabel", font=("Segoe UI", 10))
            style.configure("TButton", font=("Segoe UI", 10))
            style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))
            style.configure("Success.TLabel", foreground="green")
            style.configure("Error.TLabel", foreground="red")
            style.configure("Link.TLabel", foreground="blue", cursor="hand2")
            
            main_frame = ttk.Frame(self.root, padding="20")
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            header_label = ttk.Label(main_frame, text="GLaSSIST Desktop Settings", style="Header.TLabel")
            header_label.pack(pady=(0, 5))
            
            # Update warning text to be more informative
            warning_text = "💡 Wake word detection is temporarily paused for better responsiveness" if wake_word_was_paused else "⚠ If settings are not responding restart the application. ⚠"
            warning_label = ttk.Label(main_frame, text=warning_text, style="TLabel")
            warning_label.pack(pady=(0, 20))
            
            notebook = ttk.Notebook(main_frame)
            notebook.pack(fill=tk.X, pady=(0, 10))
            
            connection_frame = ttk.Frame(notebook, padding="10")
            notebook.add(connection_frame, text="Connection")
            
            audio_frame = ttk.Frame(notebook, padding="10")
            notebook.add(audio_frame, text="Audio & VAD")

            models_frame = ttk.Frame(notebook, padding="10")
            notebook.add(models_frame, text="Wake Word")
            
            advanced_frame = ttk.Frame(notebook, padding="10")
            notebook.add(advanced_frame, text="Advanced")
            
            about_frame = ttk.Frame(notebook, padding="10")
            notebook.add(about_frame, text="About")
            
            self._create_connection_tab(connection_frame, current_settings)
            self._create_audio_tab(audio_frame, current_settings)
            self._create_models_tab(models_frame, current_settings)
            self._create_advanced_tab(advanced_frame, current_settings)
            self._create_about_tab(about_frame)
            
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(pady=15, fill=tk.X)
            
            save_button = ttk.Button(button_frame, text="💾 Save Settings", command=self._save_config)
            save_button.pack(side=tk.RIGHT, padx=5)
            
            test_button = ttk.Button(button_frame, text="🔄 Test Connection", command=self._test_connection)
            test_button.pack(side=tk.RIGHT, padx=5)
            
            cancel_button = ttk.Button(button_frame, text="❌ Cancel", command=self._on_closing)
            cancel_button.pack(side=tk.RIGHT, padx=5)
            
            self.root.update_idletasks()
            width = self.root.winfo_width()
            height = self.root.winfo_height()
            x = (self.root.winfo_screenwidth() // 2) - (width // 2)
            y = (self.root.winfo_screenheight() // 2) - (height // 2)
            self.root.geometry(f'+{x}+{y}')
            
            # Start mainloop with proper exception handling
            self.root.mainloop()
            
        except Exception as e:
            logger.error(f"Error in settings dialog: {e}")
            self._cleanup()
            raise
        finally:
            # Resume wake word detection if it was paused
            if wake_word_was_paused:
                try:
                    if self.animation_server and hasattr(self.animation_server, 'resume_wake_word_detection'):
                        self.animation_server.resume_wake_word_detection()
                        logger.info("Wake word detection resumed")
                except Exception as e:
                    logger.error(f"Error resuming wake word detection: {e}")
            
            self._cleanup()
    
    def _on_closing(self):
        """Handle window closing with proper cleanup."""
        global _settings_dialog_instance
        logger.info("Settings dialog closing")
        
        try:
            # Cancel any running operations
            if hasattr(self, 'test_client') and self.test_client:
                try:
                    # Close test client connections
                    self.test_client = None
                except Exception:
                    pass
            
            # Destroy the window
            if self.root:
                self.root.quit()
                self.root.destroy()
                
        except Exception as e:
            logger.error(f"Error during settings cleanup: {e}")
        finally:
            _settings_dialog_instance = None
    
    def _cleanup(self):
        """Clean up resources."""
        try:
            if hasattr(self, 'test_client') and self.test_client:
                self.test_client = None
            
            if hasattr(self, 'root') and self.root:
                try:
                    self.root.quit()
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error in cleanup: {e}")
    
    def _create_models_tab(self, parent, current_settings):
        """Create wake word models tab with proper scrollable layout."""
        # Create main container with scrollbar
        main_container = ttk.Frame(parent)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Create canvas and scrollbar
        canvas = tk.Canvas(main_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        # Configure scrolling
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        # Create window that fills canvas width
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Make scrollable_frame expand to canvas width
        def _configure_scroll_frame(event):
            canvas_width = event.width
            canvas.itemconfig(canvas_window, width=canvas_width)
        
        canvas.bind('<Configure>', _configure_scroll_frame)
        
        # Pack canvas and scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        def _bind_to_mousewheel(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        def _unbind_from_mousewheel(event):
            canvas.unbind_all("<MouseWheel>")
        
        canvas.bind('<Enter>', _bind_to_mousewheel)
        canvas.bind('<Leave>', _unbind_from_mousewheel)
        
        # Wake word activation section
        activation_frame = ttk.LabelFrame(scrollable_frame, text="🎤 Wake Word Activation", padding="10")
        activation_frame.pack(fill=tk.X, pady=(0, 10), padx=(10, 5))
        
        self.wake_word_enabled_var = tk.BooleanVar(value=utils.get_env_bool('HA_WAKE_WORD_ENABLED', False))
        self.wake_word_check = ttk.Checkbutton(
            activation_frame, 
            text="Enable wake word detection", 
            variable=self.wake_word_enabled_var,
            command=self._on_wake_word_toggle
        )
        self.wake_word_check.pack(anchor=tk.W)
        
        wake_word_desc = ttk.Label(
            activation_frame, 
            text="Allows voice activation using words like 'Alexa', 'Hey Jarvis', etc.",
            font=("Segoe UI", 9), 
            foreground="gray"
        )
        wake_word_desc.pack(anchor=tk.W, pady=(5, 0))
        
        # Check openWakeWord status
        try:
            import openwakeword
            status_text = "✅ openWakeWord installed and ready"
            status_color = "green"
        except ImportError:
            status_text = "❌ openWakeWord not installed - run: pip install openwakeword"
            status_color = "red"
        
        self.status_label = ttk.Label(
            activation_frame,
            text=status_text,
            font=("Segoe UI", 9, "bold"),
            foreground=status_color
        )
        self.status_label.pack(anchor=tk.W, pady=(5, 0))
        
        # Model selection section
        self.models_config_frame = ttk.LabelFrame(scrollable_frame, text="📋 Model Configuration", padding="10")
        self.models_config_frame.pack(fill=tk.X, pady=(0, 10), padx=(10, 5))
        
        # Available models dropdown
        models_selection_frame = ttk.Frame(self.models_config_frame)
        models_selection_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(models_selection_frame, text="Available models:").pack(side=tk.LEFT)
        
        self.available_models_var = tk.StringVar()
        self.available_models_combo = ttk.Combobox(
            models_selection_frame, 
            textvariable=self.available_models_var,
            values=["alexa", "hey_jarvis", "hey_mycroft", "timers", "weather"],
            state="readonly",
            width=20
        )
        self.available_models_combo.pack(side=tk.LEFT, padx=10)
        self.available_models_combo.set("alexa")
        
        self.add_model_button = ttk.Button(
            models_selection_frame, 
            text="➕ Add", 
            command=self._add_model
        )
        self.add_model_button.pack(side=tk.LEFT, padx=5)
        
        # Selected models list
        selected_models_frame = ttk.Frame(self.models_config_frame)
        selected_models_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(selected_models_frame, text="Selected models:").pack(anchor=tk.W)
        
        listbox_frame = ttk.Frame(selected_models_frame)
        listbox_frame.pack(fill=tk.X, pady=5)
        
        self.selected_models_listbox = tk.Listbox(listbox_frame, height=4)
        self.selected_models_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        models_scrollbar = ttk.Scrollbar(listbox_frame, orient="vertical")
        models_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.selected_models_listbox.config(yscrollcommand=models_scrollbar.set)
        models_scrollbar.config(command=self.selected_models_listbox.yview)
        
        self.remove_model_button = ttk.Button(
            selected_models_frame, 
            text="➖ Remove Selected", 
            command=self._remove_model
        )
        self.remove_model_button.pack(anchor=tk.W, pady=5)
        
        # Detection settings section
        self.thresholds_frame = ttk.LabelFrame(scrollable_frame, text="🎯 Detection Settings", padding="10")
        self.thresholds_frame.pack(fill=tk.X, pady=(0, 10), padx=(10, 5))
        
        # Wake word threshold
        threshold_frame = ttk.Frame(self.thresholds_frame)
        threshold_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(threshold_frame, text="Detection threshold:", width=20).pack(side=tk.LEFT)
        
        self.wake_word_threshold_scale = ttk.Scale(
            threshold_frame, 
            from_=0.1, to=1.0, 
            orient=tk.HORIZONTAL, 
            length=200
        )
        self.wake_word_threshold_scale.set(float(current_settings.get('HA_WAKE_WORD_THRESHOLD', 0.5)))
        self.wake_word_threshold_scale.pack(side=tk.LEFT, padx=10)
        
        self.wake_word_threshold_value = ttk.Label(
            threshold_frame, 
            text=str(current_settings.get('HA_WAKE_WORD_THRESHOLD', 0.5)), 
            width=6
        )
        self.wake_word_threshold_value.pack(side=tk.LEFT, padx=5)
        
        def update_wake_word_threshold(event=None):
            value = round(self.wake_word_threshold_scale.get(), 2)
            self.wake_word_threshold_value.config(text=str(value))
        
        self.wake_word_threshold_scale.bind("<Motion>", update_wake_word_threshold)
        self.wake_word_threshold_scale.bind("<ButtonRelease-1>", update_wake_word_threshold)
        
        threshold_desc = ttk.Label(
            self.thresholds_frame, 
            text="Higher = less sensitive (fewer false positives, but may miss quiet words)", 
            font=("Segoe UI", 9), 
            foreground="gray"
        )
        threshold_desc.pack(anchor=tk.W, pady=2)
        
        # VAD threshold
        vad_frame = ttk.Frame(self.thresholds_frame)
        vad_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(vad_frame, text="Voice detection:", width=20).pack(side=tk.LEFT)
        
        self.wake_word_vad_scale = ttk.Scale(
            vad_frame, 
            from_=0.0, to=1.0, 
            orient=tk.HORIZONTAL, 
            length=200
        )
        self.wake_word_vad_scale.set(float(current_settings.get('HA_WAKE_WORD_VAD_THRESHOLD', 0.3)))
        self.wake_word_vad_scale.pack(side=tk.LEFT, padx=10)
        
        self.wake_word_vad_value = ttk.Label(
            vad_frame, 
            text=str(current_settings.get('HA_WAKE_WORD_VAD_THRESHOLD', 0.3)), 
            width=6
        )
        self.wake_word_vad_value.pack(side=tk.LEFT, padx=5)
        
        def update_vad_threshold(event=None):
            value = round(self.wake_word_vad_scale.get(), 2)
            self.wake_word_vad_value.config(text=str(value))
        
        self.wake_word_vad_scale.bind("<Motion>", update_vad_threshold)
        self.wake_word_vad_scale.bind("<ButtonRelease-1>", update_vad_threshold)
        
        vad_desc = ttk.Label(
            self.thresholds_frame, 
            text="Helps reduce false activations from non-speech sounds (0.0 = disabled)", 
            font=("Segoe UI", 9), 
            foreground="gray"
        )
        vad_desc.pack(anchor=tk.W, pady=2)
        
        # Noise suppression
        self.noise_suppression_var = tk.BooleanVar(
            value=utils.get_env_bool('HA_WAKE_WORD_NOISE_SUPPRESSION', False)
        )
        
        # Model management section
        self.management_frame = ttk.LabelFrame(scrollable_frame, text="📦 Model Management", padding="10")
        self.management_frame.pack(fill=tk.X, pady=(0, 10), padx=(10, 5))
        
        buttons_frame1 = ttk.Frame(self.management_frame)
        buttons_frame1.pack(fill=tk.X, pady=5)
        
        self.download_button = ttk.Button(
            buttons_frame1, 
            text="📥 Download Default Models", 
            command=self._download_models
        )
        self.download_button.pack(side=tk.LEFT, padx=5)
        
        self.refresh_button = ttk.Button(
            buttons_frame1, 
            text="🔄 Refresh Model List", 
            command=self._refresh_models
        )
        self.refresh_button.pack(side=tk.LEFT, padx=5)
        
        buttons_frame2 = ttk.Frame(self.management_frame)
        buttons_frame2.pack(fill=tk.X, pady=5)
        
        self.models_folder_button = ttk.Button(
            buttons_frame2, 
            text="📁 Open Models Folder", 
            command=self._open_models_folder
        )
        self.models_folder_button.pack(side=tk.LEFT, padx=5)
        
        self.test_wake_word_button = ttk.Button(
            buttons_frame2,
            text="🎯 Test Detection",
            command=self._test_wake_word_detection
        )
        self.test_wake_word_button.pack(side=tk.LEFT, padx=5)
        
        # Tips section
        tips_frame = ttk.LabelFrame(scrollable_frame, text="💡 Tips & Information", padding="10")
        tips_frame.pack(fill=tk.X, pady=(0, 10), padx=(10, 5))
        
        tips_text = """• Start with 'alexa' model - it's the most reliable
    • Higher thresholds = fewer false activations but might miss quiet speech
    • Test different settings to find what works in your environment
    • Place microphone away from speakers to avoid feedback
    • Wake words work best in quiet environments
    • You can use multiple models simultaneously"""
        
        tips_label = ttk.Label(
            tips_frame,
            text=tips_text,
            font=("Segoe UI", 9),
            foreground="blue",
            justify=tk.LEFT
        )
        tips_label.pack(anchor=tk.W, pady=5)
        
        # Store references for toggle functionality
        self.models_widgets = [
            self.available_models_combo,
            self.add_model_button,
            self.selected_models_listbox,
            self.remove_model_button,
            self.wake_word_threshold_scale,
            self.wake_word_vad_scale,
            self.download_button,
            self.refresh_button,
            self.models_folder_button,
            self.test_wake_word_button
        ]
        
        # Initialize
        self._populate_selected_models(current_settings.get('HA_WAKE_WORD_MODELS', 'alexa'))
        self._on_wake_word_toggle()

    def _on_wake_word_toggle(self):
        """Handle wake word enable/disable toggle."""
        try:
            enabled = self.wake_word_enabled_var.get()
            state = "normal" if enabled else "disabled"
            
            # Lista wszystkich kontrolek do toggle
            widgets_to_toggle = [
                self.available_models_combo,
                self.add_model_button,
                self.selected_models_listbox,
                self.remove_model_button,
                self.wake_word_threshold_scale,
                self.wake_word_vad_scale,
                self.download_button,
                self.refresh_button,
                self.models_folder_button,
                self.test_wake_word_button
            ]
            
            # Toggle poszczególnych kontrolek
            for widget in widgets_to_toggle:
                try:
                    if hasattr(widget, 'configure'):
                        if isinstance(widget, tk.Listbox):
                            widget.configure(state=state if state == "normal" else "disabled")
                        else:
                            widget.configure(state=state)
                except Exception:
                    # Niektóre widgety mogą nie wspierać state
                    continue
            
            # Toggle całych ramek
            frames_to_toggle = [self.models_config_frame, self.thresholds_frame, self.management_frame]
            for frame in frames_to_toggle:
                try:
                    if hasattr(frame, 'winfo_children'):
                        self._toggle_frame_widgets(frame, state)
                except Exception:
                    continue
                    
        except Exception as e:
            logger.error(f"Error in wake word toggle: {e}")
    
    def _toggle_frame_widgets(self, frame, state):
        """Recursively toggle widget states in a frame."""
        for child in frame.winfo_children():
            try:
                if hasattr(child, 'configure'):
                    child.configure(state=state)
            except Exception:
                pass
            # Recursively handle child widgets
            if hasattr(child, 'winfo_children'):
                self._toggle_frame_widgets(child, state)
    
    def _populate_selected_models(self, models_string):
        """Populate selected models listbox."""
        self.selected_models_listbox.delete(0, tk.END)
        
        if isinstance(models_string, str):
            models = [m.strip() for m in models_string.split(',') if m.strip()]
        else:
            models = models_string if models_string else []
        
        for model in models:
            self.selected_models_listbox.insert(tk.END, model)
    
    def _add_model(self):
        """Add selected model to the list."""
        model = self.available_models_var.get()
        if not model:
            return
        
        current_models = list(self.selected_models_listbox.get(0, tk.END))
        if model not in current_models:
            self.selected_models_listbox.insert(tk.END, model)
            logger.info(f"Added wake word model: {model}")
        else:
            messagebox.showinfo("Model Already Added", f"Model '{model}' is already in the list.")
    
    def _remove_model(self):
        """Remove selected model from the list."""
        selection = self.selected_models_listbox.curselection()
        if selection:
            model = self.selected_models_listbox.get(selection[0])
            self.selected_models_listbox.delete(selection[0])
            logger.info(f"Removed wake word model: {model}")
        else:
            messagebox.showinfo("No Selection", "Select a model to remove.")
    
    def _download_models(self):
        """Download default openWakeWord models with better thread safety."""
        # Disable button to prevent multiple clicks
        self.download_button.config(state="disabled", text="Downloading...")
        
        def download_thread():
            try:
                import openwakeword
                logger.info("Downloading openWakeWord models...")
                
                if self.animation_server:
                    self.animation_server.change_state("processing")
                
                openwakeword.utils.download_models()
                
                # Use thread-safe GUI update
                def show_success():
                    if self.root and self.root.winfo_exists():
                        messagebox.showinfo(
                            "Success", 
                            "Default wake word models downloaded successfully!\n\n"
                            "Available models:\n• alexa\n• hey_jarvis\n• hey_mycroft\n• timers\n• weather"
                        )
                        self.download_button.config(state="normal", text="📥 Download Default Models")
                
                if self.root and self.root.winfo_exists():
                    self.root.after(0, show_success)
                
                if self.animation_server:
                    self.animation_server.show_success("Models downloaded", duration=3.0)
                
            except ImportError:
                def show_import_error():
                    if self.root and self.root.winfo_exists():
                        messagebox.showerror(
                            "Error", 
                            "openWakeWord not installed!\n\nInstall with:\npip install openwakeword"
                        )
                        self.download_button.config(state="normal", text="📥 Download Default Models")
                
                if self.root and self.root.winfo_exists():
                    self.root.after(0, show_import_error)
                
                if self.animation_server:
                    self.animation_server.show_error("openWakeWord not installed", duration=5.0)
                
            except Exception as e:
                error_msg = f"Failed to download models: {str(e)}"
                logger.error(error_msg)
                
                def show_general_error():
                    if self.root and self.root.winfo_exists():
                        messagebox.showerror("Error", error_msg)
                        self.download_button.config(state="normal", text="📥 Download Default Models")
                
                if self.root and self.root.winfo_exists():
                    self.root.after(0, show_general_error)
                
                if self.animation_server:
                    self.animation_server.show_error("Download failed", duration=5.0)
        
        threading.Thread(target=download_thread, daemon=True).start()
    
    def _refresh_models(self):
        """Refresh available models list."""
        try:
            models_dir = os.path.join(os.path.dirname(__file__), 'models')
            default_models = ["alexa", "hey_jarvis", "hey_mycroft", "timers", "weather"]
            available_models = default_models.copy()
            
            # Add custom models from models directory
            if os.path.exists(models_dir):
                for filename in os.listdir(models_dir):
                    if filename.endswith(('.onnx', '.tflite')):
                        model_name = os.path.splitext(filename)[0]
                        if model_name not in available_models:
                            available_models.append(model_name)
            
            self.available_models_combo['values'] = available_models
            logger.info(f"Refreshed models list: {len(available_models)} models available")
            
            messagebox.showinfo(
                "Models Refreshed", 
                f"Found {len(available_models)} available models:\n" + 
                "\n".join(f"• {model}" for model in available_models)
            )
            
            if self.animation_server:
                self.animation_server.show_success("Models refreshed", duration=2.0)
                
        except Exception as e:
            logger.error(f"Failed to refresh models: {e}")
            messagebox.showerror("Error", f"Failed to refresh models: {str(e)}")
    
    def _open_models_folder(self):
        """Open models folder in file explorer - cross-platform."""
        try:
            from platform_utils import open_file_manager
            
            models_dir = os.path.join(os.path.dirname(__file__), 'models')
            
            if not os.path.exists(models_dir):
                os.makedirs(models_dir)
            
            success = open_file_manager(models_dir)
            if success:
                logger.info(f"Opened models folder: {models_dir}")
            else:
                messagebox.showerror("Error", f"Failed to open models folder: {models_dir}")
            
        except Exception as e:
            logger.error(f"Failed to open models folder: {e}")
            messagebox.showerror("Error", f"Failed to open models folder: {str(e)}")

    def _test_wake_word_detection(self):
        """Test wake word detection."""
        if not self.wake_word_enabled_var.get():
            messagebox.showwarning("Wake Word Disabled", "Enable wake word detection first!")
            return
        
        try:
            import openwakeword
        except ImportError:
            messagebox.showerror("Error", "openWakeWord not installed!\n\nInstall with: pip install openwakeword")
            return
        
        # Simple test dialog
        test_dialog = tk.Toplevel(self.root)
        test_dialog.title("Wake Word Test")
        test_dialog.geometry("450x300")
        test_dialog.transient(self.root)
        test_dialog.grab_set()
        
        # Center the dialog
        test_dialog.update_idletasks()
        x = (test_dialog.winfo_screenwidth() // 2) - (test_dialog.winfo_width() // 2)
        y = (test_dialog.winfo_screenheight() // 2) - (test_dialog.winfo_height() // 2)
        test_dialog.geometry(f"+{x}+{y}")
        
        # Content
        ttk.Label(test_dialog, text="🎤 Wake Word Detection Test", 
                 font=("Segoe UI", 16, "bold")).pack(pady=20)
        
        current_models = list(self.selected_models_listbox.get(0, tk.END))
        models_text = ", ".join(current_models) if current_models else "No models selected"
        
        ttk.Label(test_dialog, text=f"Selected models: {models_text}", 
                 font=("Segoe UI", 12)).pack(pady=10)
        
        threshold = round(self.wake_word_threshold_scale.get(), 2)
        ttk.Label(test_dialog, text=f"Detection threshold: {threshold}", 
                 font=("Segoe UI", 12)).pack(pady=5)
        
        status_label = ttk.Label(test_dialog, text="Click 'Start Test' to begin listening...", 
                                font=("Segoe UI", 12), foreground="blue")
        status_label.pack(pady=20)
        
        def start_test():
            status_label.config(text="🔴 Listening for wake words...\nSay one of your selected wake words!", 
                               foreground="red")
            test_dialog.after(5000, lambda: status_label.config(
                text="Test completed!\n\nFor real testing, save settings and restart the app.", 
                foreground="green"
            ))
        
        button_frame = ttk.Frame(test_dialog)
        button_frame.pack(pady=20)
        
        ttk.Button(button_frame, text="🎯 Start Test", command=start_test).pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="❌ Close", command=test_dialog.destroy).pack(side=tk.LEFT, padx=10)
        
        info_label = ttk.Label(
            test_dialog,
            text="💡 Note: This is a simple test. For full functionality,\nsave your settings and restart GLaSSIST.",
            font=("Segoe UI", 9),
            foreground="gray"
        )
        info_label.pack(pady=10)

    def _create_connection_tab(self, parent, current_settings):
        """Create connection tab."""
        conn_settings_frame = ttk.LabelFrame(parent, text="Connection Parameters", padding="10")
        conn_settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(conn_settings_frame, text="Home Assistant server address:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.host_entry = ttk.Entry(conn_settings_frame, width=40)
        self.host_entry.grid(row=0, column=1, sticky=tk.W+tk.E, pady=5, padx=5)
        self.host_entry.insert(0, current_settings['HA_HOST'])
        
        ttk.Label(conn_settings_frame, text="Access token:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.token_entry = ttk.Entry(conn_settings_frame, width=40, show="•")
        self.token_entry.grid(row=1, column=1, sticky=tk.W+tk.E, pady=5, padx=5)
        self.token_entry.insert(0, current_settings['HA_TOKEN'])
        
        test_frame = ttk.Frame(conn_settings_frame)
        test_frame.grid(row=2, column=0, columnspan=2, pady=10, sticky=tk.W+tk.E)
        
        self.test_button = ttk.Button(test_frame, text="Test Connection", command=self._test_connection)
        self.test_button.pack(side=tk.LEFT)
        
        self.test_status_label = ttk.Label(test_frame, text="")
        self.test_status_label.pack(side=tk.LEFT, padx=(10, 0))
        
        conn_settings_frame.columnconfigure(1, weight=1)
        
        pipeline_frame = ttk.LabelFrame(parent, text="Assist Pipeline Selection", padding="10")
        pipeline_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        info_label = ttk.Label(pipeline_frame, 
                              text="Pipeline determines how the assistant processes your voice commands.\n"
                                   "Test connection first to load available pipelines.")
        info_label.pack(pady=(0, 10))
        
        pipeline_select_frame = ttk.Frame(pipeline_frame)
        pipeline_select_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(pipeline_select_frame, text="Pipeline:").pack(side=tk.LEFT)
        
        self.pipeline_var = tk.StringVar()
        self.pipeline_combo = ttk.Combobox(pipeline_select_frame, textvariable=self.pipeline_var, 
                                          state="readonly", width=40)
        self.pipeline_combo.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        
        current_pipeline_id = current_settings['HA_PIPELINE_ID']
        if current_pipeline_id:
            self.pipeline_combo['values'] = [f"Current: {current_pipeline_id}"]
            self.pipeline_var.set(f"Current: {current_pipeline_id}")
        else:
            self.pipeline_combo['values'] = ["(default)"]
            self.pipeline_var.set("(default)")
        
        refresh_button = ttk.Button(pipeline_select_frame, text="Refresh", 
                                   command=self._refresh_pipelines)
        refresh_button.pack(side=tk.RIGHT, padx=(5, 0))
    
    def _create_audio_tab(self, parent, current_settings):
        
        """Create audio and VAD tab."""
        hotkey_frame = ttk.LabelFrame(parent, text="Activation", padding="10")
        hotkey_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(hotkey_frame, text="Hotkey:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.hotkey_var = tk.StringVar(value=current_settings['HA_HOTKEY'])
        hotkey_combo = ttk.Combobox(hotkey_frame, textvariable=self.hotkey_var, state="readonly", width=20)
        hotkey_combo["values"] = ("ctrl+shift+h", "ctrl+shift+g", "ctrl+alt+h", "ctrl+shift+a", "alt+space", "ctrl+shift+space")
        hotkey_combo.grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)
        
        feedback_frame = ttk.LabelFrame(parent, text="Audio Feedback", padding="10")
        feedback_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.sound_feedback_var = tk.BooleanVar(value=current_settings.get('HA_SOUND_FEEDBACK', True))
        sound_check = ttk.Checkbutton(feedback_frame, text="Play sounds on activation/deactivation", variable=self.sound_feedback_var)
        sound_check.pack(anchor=tk.W)
        
        sound_desc = ttk.Label(feedback_frame, 
                              text="Plays activation.wav and deactivation.wav from 'sound' folder",
                              font=("Segoe UI", 9), foreground="gray")
        sound_desc.pack(anchor=tk.W, pady=(5, 0))

        vad_frame = ttk.LabelFrame(parent, text="Voice Activity Detection (VAD)", padding="10")
        vad_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(vad_frame, text="Voice detection sensitivity:").grid(row=0, column=0, sticky=tk.W, pady=5)
        vad_control_frame = ttk.Frame(vad_frame)
        vad_control_frame.grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)
        
        self.vad_mode_scale = ttk.Scale(vad_control_frame, from_=0, to=3, orient=tk.HORIZONTAL, length=200)
        self.vad_mode_scale.set(current_settings['HA_VAD_MODE'])
        self.vad_mode_scale.pack(side=tk.LEFT)
        
        self.vad_mode_value = ttk.Label(vad_control_frame, text=str(current_settings['HA_VAD_MODE']), width=3)
        self.vad_mode_value.pack(side=tk.LEFT, padx=5)

        mic_frame = ttk.LabelFrame(parent, text="Microphone Selection", padding="10")
        mic_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(mic_frame, text="Microphone:").grid(row=0, column=0, sticky=tk.W, pady=5)         

        self.mic_var = tk.StringVar()
        self.mic_combo = ttk.Combobox(mic_frame, textvariable=self.mic_var, 
                                    state="readonly", width=40)
        self.mic_combo.grid(row=0, column=1, sticky=tk.W+tk.E, pady=5, padx=5)


        # Załadować listę mikrofonów
        self._refresh_microphones()

        refresh_mic_button = ttk.Button(mic_frame, text="Refresh", 
                                    command=self._refresh_microphones)
        refresh_mic_button.grid(row=0, column=2, padx=(5, 0))
        
        def update_vad_mode(event=None):
            self.vad_mode_value.config(text=str(int(self.vad_mode_scale.get())))
        self.vad_mode_scale.bind("<Motion>", update_vad_mode)
        self.vad_mode_scale.bind("<ButtonRelease-1>", update_vad_mode)
        
        vad_desc = ttk.Label(vad_frame, text="0 = least sensitive, 3 = most sensitive", 
                            font=("Segoe UI", 9), foreground="gray")
        vad_desc.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        ttk.Label(vad_frame, text="Silence threshold (seconds):").grid(row=2, column=0, sticky=tk.W, pady=5)
        silence_control_frame = ttk.Frame(vad_frame)
        silence_control_frame.grid(row=2, column=1, sticky=tk.W, pady=5, padx=5)
        
        self.silence_scale = ttk.Scale(silence_control_frame, from_=0.3, to=3.0, orient=tk.HORIZONTAL, length=200)
        self.silence_scale.set(current_settings['HA_SILENCE_THRESHOLD_SEC'])
        self.silence_scale.pack(side=tk.LEFT)
        
        self.silence_value = ttk.Label(silence_control_frame, text=str(current_settings['HA_SILENCE_THRESHOLD_SEC']) + "s", width=4)
        self.silence_value.pack(side=tk.LEFT, padx=5)
        
        def update_silence(event=None):
            value = round(self.silence_scale.get(), 1)
            self.silence_value.config(text=f"{value}s")
        self.silence_scale.bind("<Motion>", update_silence)
        self.silence_scale.bind("<ButtonRelease-1>", update_silence)
        
        silence_desc = ttk.Label(vad_frame, text="How long to wait for silence before ending recording", 
                                font=("Segoe UI", 9), foreground="gray")
        silence_desc.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=2)
    
    def _create_advanced_tab(self, parent, current_settings):
        """Create advanced settings tab."""
        debug_frame = ttk.LabelFrame(parent, text="Debugging", padding="10")
        debug_frame.pack(fill=tk.X, pady=(0, 10))
        
        interface_frame = ttk.LabelFrame(parent, text="Interface & Performance", padding="10")
        interface_frame.pack(fill=tk.X, pady=(0, 10))

        self.animations_var = tk.BooleanVar(value=utils.get_env_bool('HA_ANIMATIONS_ENABLED', True))
        animations_check = ttk.Checkbutton(
            interface_frame, 
            text="Enable visual animations", 
            variable=self.animations_var
        )
        animations_check.pack(anchor=tk.W)

        animations_desc = ttk.Label(
            interface_frame, 
            text="Three.js animations with audio visualization. Disable to save CPU/memory.",
            font=("Segoe UI", 9), 
            foreground="gray"
        )
        animations_desc.pack(anchor=tk.W, pady=(5, 0))

        self.response_text_var = tk.BooleanVar(value=utils.get_env_bool('HA_RESPONSE_TEXT_ENABLED', True))
        response_text_check = ttk.Checkbutton(
            interface_frame, 
            text="Show response text on screen", 
            variable=self.response_text_var
        )
        response_text_check.pack(anchor=tk.W, pady=(10, 0))

        response_text_desc = ttk.Label(
            interface_frame, 
            text="Display assistant responses as animated text overlay.",
            font=("Segoe UI", 9), 
            foreground="gray"
        )
        response_text_desc.pack(anchor=tk.W, pady=(5, 0))
 
        self.debug_var = tk.BooleanVar(value=current_settings['DEBUG'])
        debug_check = ttk.Checkbutton(debug_frame, text="Debug mode (detailed logs)", variable=self.debug_var)
        debug_check.pack(anchor=tk.W)
        
        audio_advanced_frame = ttk.LabelFrame(parent, text="Advanced Audio Settings", padding="10")
        audio_advanced_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(audio_advanced_frame, text="Sample rate:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.sample_rate_var = tk.StringVar(value=utils.get_env('HA_SAMPLE_RATE', '16000'))
        sample_rate_combo = ttk.Combobox(audio_advanced_frame, textvariable=self.sample_rate_var, 
                                        values=["8000", "16000", "22050", "44100", "48000"], 
                                        state="readonly", width=10)
        sample_rate_combo.grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)
        
        ttk.Label(audio_advanced_frame, text="Hz (default: 16000)", 
                 font=("Segoe UI", 9), foreground="gray").grid(row=0, column=2, sticky=tk.W, padx=5)
        
        ttk.Label(audio_advanced_frame, text="VAD frame duration:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.frame_duration_var = tk.StringVar(value=utils.get_env('HA_FRAME_DURATION_MS', '30'))
        frame_duration_combo = ttk.Combobox(audio_advanced_frame, textvariable=self.frame_duration_var,
                                           values=["10", "20", "30"], state="readonly", width=10)
        frame_duration_combo.grid(row=1, column=1, sticky=tk.W, pady=5, padx=5)
        
        ttk.Label(audio_advanced_frame, text="ms (default: 30)", 
                 font=("Segoe UI", 9), foreground="gray").grid(row=1, column=2, sticky=tk.W, padx=5)
        
        info_advanced = ttk.Label(audio_advanced_frame, 
                                 text="⚠️ Only change these settings if you know what you're doing.\n"
                                      "Incorrect values may cause audio problems.",
                                 font=("Segoe UI", 9), foreground="orange")
        info_advanced.grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=10)
        
        network_frame = ttk.LabelFrame(parent, text="Network", padding="10")
        network_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(network_frame, text="Animation server port:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.animation_port_var = tk.StringVar(value=utils.get_env('ANIMATION_PORT', '8765'))
        animation_port_entry = ttk.Entry(network_frame, textvariable=self.animation_port_var, width=10)
        animation_port_entry.grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)
        
        ttk.Label(network_frame, text="(default: 8765)", 
                 font=("Segoe UI", 9), foreground="gray").grid(row=0, column=2, sticky=tk.W, padx=5)
    
    def _create_about_tab(self, parent):
        """Create about tab."""
        main_info_frame = ttk.Frame(parent)
        main_info_frame.pack(fill=tk.BOTH, expand=True, pady=20)
        
        title_label = ttk.Label(main_info_frame, text="🎤 GLaSSIST Desktop", 
                               font=("Segoe UI", 18, "bold"))
        title_label.pack(pady=(0, 10))
        
        version_label = ttk.Label(main_info_frame, text="Voice Assistant for Home Assistant", 
                                 font=("Segoe UI", 12))
        version_label.pack(pady=(0, 20))
        
        creator_frame = ttk.LabelFrame(main_info_frame, text="Created by", padding="15")
        creator_frame.pack(fill=tk.X, pady=(0, 20))
        
        creator_label = ttk.Label(creator_frame, text="Patryk Smoliński", 
                                 font=("Segoe UI", 14, "bold"))
        creator_label.pack()
        
        github_frame = ttk.Frame(creator_frame)
        github_frame.pack(pady=(10, 0))
        
        github_label = ttk.Label(github_frame, text="🔗 GitHub: ", font=("Segoe UI", 11))
        github_label.pack(side=tk.LEFT)
        
        github_link = ttk.Label(github_frame, text="https://github.com/SmolinskiP", 
                               font=("Segoe UI", 11), style="Link.TLabel")
        github_link.pack(side=tk.LEFT)
        github_link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/SmolinskiP"))
        
        support_frame = ttk.LabelFrame(main_info_frame, text="Support the Project", padding="15")
        support_frame.pack(fill=tk.X, pady=(0, 20))
        
        support_text = ttk.Label(support_frame, 
                               text="Like my work? Buy me a coffee! ☕", 
                               font=("Segoe UI", 12))
        support_text.pack(pady=(0, 10))
        
        coffee_frame = ttk.Frame(support_frame)
        coffee_frame.pack()
        
        coffee_label = ttk.Label(coffee_frame, text="☕ ", font=("Segoe UI", 14))
        coffee_label.pack(side=tk.LEFT)
        
        coffee_link = ttk.Label(coffee_frame, text="https://buymeacoffee.com/smolinskip", 
                               font=("Segoe UI", 11), style="Link.TLabel")
        coffee_link.pack(side=tk.LEFT)
        coffee_link.bind("<Button-1>", lambda e: webbrowser.open("https://buymeacoffee.com/smolinskip"))
    
    def _test_connection(self):
        """Test connection to Home Assistant with improved thread safety."""
        host = self.host_entry.get().strip()
        token = self.token_entry.get().strip()
        
        if not host or not token:
            self.test_status_label.config(text="Enter host and token!", style="Error.TLabel")
            if self.animation_server:
                self.animation_server.show_error("Missing connection details", duration=4.0)
            return
        
        # Prevent multiple concurrent tests
        if hasattr(self, '_testing') and self._testing:
            return
            
        self._testing = True
        self.test_button.config(state="disabled", text="Testing...")
        self.test_status_label.config(text="Connecting...", style="")
        
        def test_thread():
            try:
                test_client = HomeAssistantClient()
                test_client.host = host
                test_client.token = token
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    success, message = loop.run_until_complete(test_client.test_connection())
                    
                    # Store results for GUI update
                    pipelines_data = None
                    if success:
                        try:
                            pipelines_data = test_client.get_available_pipelines()
                        except Exception as e:
                            logger.warning(f"Failed to get pipelines: {e}")
                    
                    # Thread-safe GUI update
                    def update_gui():
                        if self.root and self.root.winfo_exists():
                            self._testing = False
                            self.test_button.config(state="normal", text="Test Connection")
                            
                            if success:
                                self.test_status_label.config(text=f"✅ {message}", style="Success.TLabel")
                                if self.animation_server:
                                    self.animation_server.show_success("Connection successful", duration=3.0)
                                
                                # Update pipelines if available
                                if pipelines_data:
                                    self.pipelines_data = pipelines_data
                                    self._update_pipeline_list()
                            else:
                                self.test_status_label.config(text=f"❌ {message}", style="Error.TLabel")
                                if self.animation_server:
                                    self.animation_server.show_error(f"Connection failed: {message}", duration=5.0)
                    
                    if self.root and self.root.winfo_exists():
                        self.root.after(0, update_gui)
                    
                finally:
                    loop.close()
                    
            except Exception as e:
                error_msg = f"Test error: {str(e)}"
                logger.error(error_msg)
                
                def update_error_gui():
                    if self.root and self.root.winfo_exists():
                        self._testing = False
                        self.test_button.config(state="normal", text="Test Connection")
                        self.test_status_label.config(text=f"❌ {error_msg}", style="Error.TLabel")
                        if self.animation_server:
                            self.animation_server.show_error(f"Test failed: {error_msg}", duration=5.0)
                
                if self.root and self.root.winfo_exists():
                    self.root.after(0, update_error_gui)
        
        threading.Thread(target=test_thread, daemon=True).start()



    def _update_pipeline_list(self):
        """Update pipeline list."""
        if not self.pipelines_data:
            return
        
        pipeline_options = ["(default)"]
        pipeline_mapping = {"(default)": ""}
        
        for pipeline in self.pipelines_data:
            name = pipeline.get("name", "Unnamed")
            pipeline_id = pipeline.get("id", "")
            is_preferred = pipeline.get("is_preferred", False)
            
            star = " ⭐" if is_preferred else ""
            display_name = f"{name}{star} (ID: {pipeline_id})"
            
            pipeline_options.append(display_name)
            pipeline_mapping[display_name] = pipeline_id
        
        self.pipeline_combo["values"] = pipeline_options
        
        current_pipeline_id = utils.get_env('HA_PIPELINE_ID', '')
        if current_pipeline_id:
            for option, pid in pipeline_mapping.items():
                if pid == current_pipeline_id:
                    self.pipeline_var.set(option)
                    break
            else:
                self.pipeline_var.set(f"⚠️ Unknown: {current_pipeline_id}")
        else:
            self.pipeline_var.set("(default)")
        
        self.pipeline_mapping = pipeline_mapping
        logger.info(f"Updated pipeline list: {len(self.pipelines_data)} available")
    
    def _refresh_pipelines(self):
        """Refresh pipeline list with automatic connection test first."""
        host = self.host_entry.get().strip()
        token = self.token_entry.get().strip()
        
        if not host or not token:
            self.test_status_label.config(text="Enter host and token first!", style="Error.TLabel")
            if self.animation_server:
                self.animation_server.show_error("Missing connection details", duration=4.0)
            return
        
        # Disable refresh button during operation
        refresh_button = None
        for child in self.test_status_label.master.winfo_children():
            if isinstance(child, ttk.Button) and "Refresh" in child.cget('text'):
                refresh_button = child
                break
        
        if refresh_button:
            refresh_button.config(state="disabled", text="Refreshing...")
        
        self.test_status_label.config(text="Testing connection...", style="")
        
        def refresh_thread():
            try:
                # First test connection
                self.test_client = HomeAssistantClient()
                self.test_client.host = host
                self.test_client.token = token
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    success, message = loop.run_until_complete(self.test_client.test_connection())
                    
                    if success:
                        # Connection successful - now fetch pipelines
                        self.root.after(0, lambda: self.test_status_label.config(
                            text="✅ Connected - fetching pipelines...", style="Success.TLabel"
                        ))
                        
                        # Fetch fresh pipeline data
                        loop.run_until_complete(self.test_client.fetch_available_pipelines())
                        self.pipelines_data = self.test_client.get_available_pipelines()
                        
                        # Update UI on main thread
                        self.root.after(0, self._update_pipeline_list)
                        self.root.after(0, lambda: self.test_status_label.config(
                            text=f"✅ Refreshed - {len(self.pipelines_data)} pipelines found", 
                            style="Success.TLabel"
                        ))
                        
                        if self.animation_server:
                            self.animation_server.show_success(
                                f"Found {len(self.pipelines_data)} pipelines", 
                                duration=3.0
                            )
                        
                    else:
                        # Connection failed
                        self.root.after(0, lambda: self.test_status_label.config(
                            text=f"❌ {message}", style="Error.TLabel"
                        ))
                        
                        if self.animation_server:
                            self.animation_server.show_error(f"Connection failed: {message}", duration=5.0)
                    
                finally:
                    loop.close()
                    
            except Exception as e:
                error_msg = f"Refresh error: {str(e)}"
                self.root.after(0, lambda: self.test_status_label.config(
                    text=f"❌ {error_msg}", style="Error.TLabel"
                ))
                
                if self.animation_server:
                    self.animation_server.show_error("Refresh failed", duration=5.0)
            
            finally:
                # Re-enable refresh button
                if refresh_button:
                    self.root.after(0, lambda: refresh_button.config(
                        state="normal", text="Refresh"
                    ))
        
        threading.Thread(target=refresh_thread, daemon=True).start()
    
    def _save_config(self):
        """Save configuration."""
        try:
            selected_pipeline_display = self.pipeline_var.get()
            selected_pipeline_id = ""
            selected_models = list(self.selected_models_listbox.get(0, tk.END))
            models_string = ','.join(selected_models) if selected_models else 'alexa'
            selected_mic_display = self.mic_var.get()
            selected_mic_index = -1
            if hasattr(self, 'mic_mapping') and selected_mic_display in self.mic_mapping:
                selected_mic_index = self.mic_mapping[selected_mic_display]
            elif selected_mic_display.startswith("⚠️ Unknown:"):
                try:
                    selected_mic_index = int(selected_mic_display.split(": ", 1)[1])
                except:
                    selected_mic_index = -1
            
            if hasattr(self, 'pipeline_mapping') and selected_pipeline_display in self.pipeline_mapping:
                selected_pipeline_id = self.pipeline_mapping[selected_pipeline_display]
            elif selected_pipeline_display.startswith("⚠️ Unknown:"):
                selected_pipeline_id = selected_pipeline_display.split(": ", 1)[1]
            
            new_settings = {
                'HA_HOST': self.host_entry.get().strip(),
                'HA_TOKEN': self.token_entry.get().strip(),
                'HA_PIPELINE_ID': selected_pipeline_id,
                'HA_HOTKEY': self.hotkey_var.get(),
                'HA_SILENCE_THRESHOLD_SEC': str(round(self.silence_scale.get(), 1)),
                'HA_VAD_MODE': str(int(self.vad_mode_scale.get())),
                'DEBUG': 'true' if self.debug_var.get() else 'false',
                'HA_ANIMATIONS_ENABLED': 'true' if self.animations_var.get() else 'false',
                'HA_RESPONSE_TEXT_ENABLED': 'true' if self.response_text_var.get() else 'false',
                'HA_SAMPLE_RATE': self.sample_rate_var.get(),
                'HA_FRAME_DURATION_MS': self.frame_duration_var.get(),
                'ANIMATION_PORT': self.animation_port_var.get(),
                'HA_SOUND_FEEDBACK': 'true' if self.sound_feedback_var.get() else 'false',
                'HA_MICROPHONE_INDEX': str(selected_mic_index),
                
                'HA_CHANNELS': utils.get_env('HA_CHANNELS', '1'),
                'HA_PADDING_MS': utils.get_env('HA_PADDING_MS', '300'),

                'HA_WAKE_WORD_ENABLED': 'true' if self.wake_word_enabled_var.get() else 'false',
                'HA_WAKE_WORD_MODELS': models_string,
                'HA_WAKE_WORD_THRESHOLD': str(round(self.wake_word_threshold_scale.get(), 2)),
                'HA_WAKE_WORD_VAD_THRESHOLD': str(round(self.wake_word_vad_scale.get(), 2)),
                'HA_WAKE_WORD_NOISE_SUPPRESSION': 'true' if self.noise_suppression_var.get() else 'false'
            }
            
            if not new_settings['HA_HOST']:
                messagebox.showerror("Error", "Home Assistant server address is required!")
                return
                
            if not new_settings['HA_TOKEN']:
                messagebox.showerror("Error", "Access token is required!")
                return
            
            if self.wake_word_enabled_var.get():
                if not selected_models:
                    messagebox.showerror("Error", "Select at least one wake word model!")
                    return
                
                try:
                    import openwakeword
                except ImportError:
                    messagebox.showerror("Error", 
                        "openWakeWord not installed!\n\n"
                        "Install with: pip install openwakeword\n"
                        "or disable wake word detection.")
                    return

            try:
                port = int(new_settings['ANIMATION_PORT'])
                if port < 1024 or port > 65535:
                    messagebox.showerror("Error", "Animation port must be between 1024-65535!")
                    return
            except ValueError:
                messagebox.showerror("Error", "Animation port must be a number!")
                return
            
            result = self._save_env_file(new_settings)
            
            if result['success']:
                messagebox.showinfo("Success", 
                                   f"{result['message']}\n\nRestart the application to apply changes.")
                self.root.destroy()
            else:
                messagebox.showerror("Error", result['message'])
                
        except Exception as e:
            logger.exception(f"Error saving settings: {e}")
            messagebox.showerror("Error", f"Failed to save settings: {str(e)}")
    
    def _save_env_file(self, settings):
        """Save settings to .env file."""
        try:
            possible_paths = [
                os.path.join(os.path.dirname(__file__), '.env'),
                os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),
                '.env'
            ]
            
            env_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    env_path = path
                    break
                    
            if not env_path:
                env_path = possible_paths[0]
            
            env_content = "# GLaSSIST Desktop Settings\n"
            env_content += "# Generated automatically by the application\n\n"
            
            env_content += "# === CONNECTION ===\n"
            env_content += f"HA_HOST={settings['HA_HOST']}\n"
            env_content += f"HA_TOKEN={settings['HA_TOKEN']}\n"
            if settings['HA_PIPELINE_ID']:
                env_content += f"HA_PIPELINE_ID={settings['HA_PIPELINE_ID']}\n"
            
            env_content += "\n# === ACTIVATION ===\n"
            env_content += f"HA_HOTKEY={settings['HA_HOTKEY']}\n"
            
            env_content += "\n# === AUDIO ===\n"
            env_content += f"HA_SAMPLE_RATE={settings['HA_SAMPLE_RATE']}\n"
            env_content += f"HA_CHANNELS={settings['HA_CHANNELS']}\n"
            env_content += f"HA_FRAME_DURATION_MS={settings['HA_FRAME_DURATION_MS']}\n"
            env_content += f"HA_PADDING_MS={settings['HA_PADDING_MS']}\n"
            env_content += f"HA_MICROPHONE_INDEX={settings['HA_MICROPHONE_INDEX']}\n"
            
            env_content += "\n# === VOICE DETECTION (VAD) ===\n"
            env_content += f"HA_VAD_MODE={settings['HA_VAD_MODE']}\n"
            env_content += f"HA_SILENCE_THRESHOLD_SEC={settings['HA_SILENCE_THRESHOLD_SEC']}\n"
            
            env_content += "\n# === INTERFACE & PERFORMANCE ===\n"
            env_content += f"HA_ANIMATIONS_ENABLED={settings.get('HA_ANIMATIONS_ENABLED', 'true')}\n"
            env_content += f"HA_RESPONSE_TEXT_ENABLED={settings.get('HA_RESPONSE_TEXT_ENABLED', 'true')}\n"

            env_content += "\n# === NETWORK ===\n"
            env_content += f"ANIMATION_PORT={settings['ANIMATION_PORT']}\n"
            
            env_content += "\n# === AUDIO FEEDBACK ===\n"
            env_content += f"HA_SOUND_FEEDBACK={settings['HA_SOUND_FEEDBACK']}\n"

            env_content += "\n# === WAKE WORD DETECTION ===\n"
            env_content += f"HA_WAKE_WORD_ENABLED={settings.get('HA_WAKE_WORD_ENABLED', 'false')}\n"
            env_content += f"HA_WAKE_WORD_MODELS={settings.get('HA_WAKE_WORD_MODELS', 'alexa')}\n"
            env_content += f"HA_WAKE_WORD_THRESHOLD={settings.get('HA_WAKE_WORD_THRESHOLD', '0.5')}\n"
            env_content += f"HA_WAKE_WORD_VAD_THRESHOLD={settings.get('HA_WAKE_WORD_VAD_THRESHOLD', '0.3')}\n"
            env_content += f"HA_WAKE_WORD_NOISE_SUPPRESSION={settings.get('HA_WAKE_WORD_NOISE_SUPPRESSION', 'false')}\n"
            
            env_content += "\n# === DEBUG ===\n"
            env_content += f"DEBUG={settings['DEBUG']}\n"
            
            os.makedirs(os.path.dirname(env_path), exist_ok=True)
            
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write(env_content)
            
            logger.info(f"Settings saved to: {env_path}")
            return {
                'success': True, 
                'message': f'Settings saved to {os.path.basename(env_path)}'
            }
            
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            return {
                'success': False, 
                'message': f'Save error: {str(e)}'
            }


# Global variable to prevent multiple settings windows
_settings_dialog_instance = None

def show_improved_settings(animation_server=None):
    """Helper function to display enhanced settings with singleton pattern."""
    global _settings_dialog_instance
    
    # Prevent multiple instances
    if _settings_dialog_instance is not None:
        try:
            # Try to bring existing window to front
            if _settings_dialog_instance.root and _settings_dialog_instance.root.winfo_exists():
                _settings_dialog_instance.root.lift()
                _settings_dialog_instance.root.focus_force()
                logger.info("Settings window already open - bringing to front")
                return _settings_dialog_instance
        except (tk.TclError, AttributeError):
            # Window was destroyed, reset the instance
            _settings_dialog_instance = None
    
    # Create new instance
    try:
        _settings_dialog_instance = ImprovedSettingsDialog(animation_server)
        _settings_dialog_instance.show_settings()
        return _settings_dialog_instance
    except Exception as e:
        logger.error(f"Failed to create settings dialog: {e}")
        _settings_dialog_instance = None
        raise