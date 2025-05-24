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
from client import HomeAssistantClient

logger = utils.setup_logger()

class ImprovedSettingsDialog:
    """Enhanced settings dialog with connection testing and pipeline selection."""
    
    def __init__(self, animation_server=None):
        self.root = None
        self.pipelines_data = []
        self.test_client = None
        self.animation_server = animation_server
        
    def show_settings(self):
        """Display settings dialog."""
        # Load current settings
        current_settings = {
            'HA_HOST': utils.get_env('HA_HOST', 'localhost:8123'),
            'HA_TOKEN': utils.get_env('HA_TOKEN', ''),
            'HA_PIPELINE_ID': utils.get_env('HA_PIPELINE_ID', ''),
            'HA_HOTKEY': utils.get_env('HA_HOTKEY', 'ctrl+shift+h'),
            'HA_VAD_MODE': utils.get_env('HA_VAD_MODE', 3, int),
            'HA_SILENCE_THRESHOLD_SEC': utils.get_env('HA_SILENCE_THRESHOLD_SEC', 0.8, float),
            'HA_SOUND_FEEDBACK': utils.get_env('HA_SOUND_FEEDBACK', 'true'),
            'DEBUG': utils.get_env('DEBUG', False, bool)
        }
        
        # Create main window
        self.root = tk.Tk()
        self.root.title("HA Assist - Settings")
        self.root.geometry("750x600")
        self.root.resizable(True, True)
        
        # Icon
        icon_path = os.path.join(os.path.dirname(__file__), 'img', 'icon.ico')
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception as e:
                logger.error(f"Error setting icon: {e}")
        
        # Style
        style = ttk.Style()
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("Success.TLabel", foreground="green")
        style.configure("Error.TLabel", foreground="red")
        style.configure("Link.TLabel", foreground="blue", cursor="hand2")
        
        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header_label = ttk.Label(main_frame, text="Home Assistant Assist Settings", style="Header.TLabel")
        header_label.pack(pady=(0, 20))
        
        # Notebook for tabs - FIXED: no expand=True
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.X, pady=(0, 10))
        
        # Tab 1: Connection
        connection_frame = ttk.Frame(notebook, padding="10")
        notebook.add(connection_frame, text="Connection")
        
        # Tab 2: Audio & VAD
        audio_frame = ttk.Frame(notebook, padding="10")
        notebook.add(audio_frame, text="Audio & VAD")
        
        # Tab 3: Advanced
        advanced_frame = ttk.Frame(notebook, padding="10")
        notebook.add(advanced_frame, text="Advanced")
        
        # Tab 4: About
        about_frame = ttk.Frame(notebook, padding="10")
        notebook.add(about_frame, text="About")
        
        # Create tab content
        self._create_connection_tab(connection_frame, current_settings)
        self._create_audio_tab(audio_frame, current_settings)
        self._create_advanced_tab(advanced_frame, current_settings)
        self._create_about_tab(about_frame)
        
        # Buttons at bottom
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=15, fill=tk.X)
        
        save_button = ttk.Button(button_frame, text="💾 Save Settings", command=self._save_config)
        save_button.pack(side=tk.RIGHT, padx=5)
        
        test_button = ttk.Button(button_frame, text="🔄 Test Connection", command=self._test_connection)
        test_button.pack(side=tk.RIGHT, padx=5)
        
        cancel_button = ttk.Button(button_frame, text="❌ Cancel", command=self.root.destroy)
        cancel_button.pack(side=tk.RIGHT, padx=5)
        
        # Center window
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'+{x}+{y}')
        
        # Start main loop
        self.root.mainloop()
    
    def _create_connection_tab(self, parent, current_settings):
        """Create connection tab."""
        # Connection settings frame
        conn_settings_frame = ttk.LabelFrame(parent, text="Connection Parameters", padding="10")
        conn_settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Host
        ttk.Label(conn_settings_frame, text="Home Assistant server address:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.host_entry = ttk.Entry(conn_settings_frame, width=40)
        self.host_entry.grid(row=0, column=1, sticky=tk.W+tk.E, pady=5, padx=5)
        self.host_entry.insert(0, current_settings['HA_HOST'])
        
        # Token
        ttk.Label(conn_settings_frame, text="Access token:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.token_entry = ttk.Entry(conn_settings_frame, width=40, show="•")
        self.token_entry.grid(row=1, column=1, sticky=tk.W+tk.E, pady=5, padx=5)
        self.token_entry.insert(0, current_settings['HA_TOKEN'])
        
        # Connection test
        test_frame = ttk.Frame(conn_settings_frame)
        test_frame.grid(row=2, column=0, columnspan=2, pady=10, sticky=tk.W+tk.E)
        
        self.test_button = ttk.Button(test_frame, text="Test Connection", command=self._test_connection)
        self.test_button.pack(side=tk.LEFT)
        
        self.test_status_label = ttk.Label(test_frame, text="")
        self.test_status_label.pack(side=tk.LEFT, padx=(10, 0))
        
        # Grid configuration
        conn_settings_frame.columnconfigure(1, weight=1)
        
        # Pipeline selection section
        pipeline_frame = ttk.LabelFrame(parent, text="Assist Pipeline Selection", padding="10")
        pipeline_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        # Pipeline info
        info_label = ttk.Label(pipeline_frame, 
                              text="Pipeline determines how the assistant processes your voice commands.\n"
                                   "Test connection first to load available pipelines.")
        info_label.pack(pady=(0, 10))
        
        # Pipeline selection
        pipeline_select_frame = ttk.Frame(pipeline_frame)
        pipeline_select_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(pipeline_select_frame, text="Pipeline:").pack(side=tk.LEFT)
        
        self.pipeline_var = tk.StringVar()
        self.pipeline_combo = ttk.Combobox(pipeline_select_frame, textvariable=self.pipeline_var, 
                                          state="readonly", width=40)
        self.pipeline_combo.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        
        # Load current pipeline
        current_pipeline_id = current_settings['HA_PIPELINE_ID']
        if current_pipeline_id:
            self.pipeline_combo['values'] = [f"Current: {current_pipeline_id}"]
            self.pipeline_var.set(f"Current: {current_pipeline_id}")
        else:
            self.pipeline_combo['values'] = ["(default)"]
            self.pipeline_var.set("(default)")
        
        # Refresh button
        refresh_button = ttk.Button(pipeline_select_frame, text="Refresh", 
                                   command=self._refresh_pipelines)
        refresh_button.pack(side=tk.RIGHT, padx=(5, 0))
    
    def _create_audio_tab(self, parent, current_settings):
        """Create audio and VAD tab."""
        # Hotkey
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

        # VAD (Voice Activity Detection)
        vad_frame = ttk.LabelFrame(parent, text="Voice Activity Detection (VAD)", padding="10")
        vad_frame.pack(fill=tk.X, pady=(0, 10))
        
        # VAD mode
        ttk.Label(vad_frame, text="Voice detection sensitivity:").grid(row=0, column=0, sticky=tk.W, pady=5)
        vad_control_frame = ttk.Frame(vad_frame)
        vad_control_frame.grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)
        
        self.vad_mode_scale = ttk.Scale(vad_control_frame, from_=0, to=3, orient=tk.HORIZONTAL, length=200)
        self.vad_mode_scale.set(current_settings['HA_VAD_MODE'])
        self.vad_mode_scale.pack(side=tk.LEFT)
        
        self.vad_mode_value = ttk.Label(vad_control_frame, text=str(current_settings['HA_VAD_MODE']), width=3)
        self.vad_mode_value.pack(side=tk.LEFT, padx=5)
        
        def update_vad_mode(event=None):
            self.vad_mode_value.config(text=str(int(self.vad_mode_scale.get())))
        self.vad_mode_scale.bind("<Motion>", update_vad_mode)
        self.vad_mode_scale.bind("<ButtonRelease-1>", update_vad_mode)
        
        # VAD description
        vad_desc = ttk.Label(vad_frame, text="0 = least sensitive, 3 = most sensitive", 
                            font=("Segoe UI", 9), foreground="gray")
        vad_desc.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        # Silence threshold
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
        
        # Silence description
        silence_desc = ttk.Label(vad_frame, text="How long to wait for silence before ending recording", 
                                font=("Segoe UI", 9), foreground="gray")
        silence_desc.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=2)
    
    def _create_advanced_tab(self, parent, current_settings):
        """Create advanced settings tab."""
        # Debug mode
        debug_frame = ttk.LabelFrame(parent, text="Debugging", padding="10")
        debug_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.debug_var = tk.BooleanVar(value=current_settings['DEBUG'])
        debug_check = ttk.Checkbutton(debug_frame, text="Debug mode (detailed logs)", variable=self.debug_var)
        debug_check.pack(anchor=tk.W)
        
        # Advanced audio settings
        audio_advanced_frame = ttk.LabelFrame(parent, text="Advanced Audio Settings", padding="10")
        audio_advanced_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Sample rate
        ttk.Label(audio_advanced_frame, text="Sample rate:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.sample_rate_var = tk.StringVar(value=utils.get_env('HA_SAMPLE_RATE', '16000'))
        sample_rate_combo = ttk.Combobox(audio_advanced_frame, textvariable=self.sample_rate_var, 
                                        values=["8000", "16000", "22050", "44100", "48000"], 
                                        state="readonly", width=10)
        sample_rate_combo.grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)
        
        ttk.Label(audio_advanced_frame, text="Hz (default: 16000)", 
                 font=("Segoe UI", 9), foreground="gray").grid(row=0, column=2, sticky=tk.W, padx=5)
        
        # Frame duration
        ttk.Label(audio_advanced_frame, text="VAD frame duration:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.frame_duration_var = tk.StringVar(value=utils.get_env('HA_FRAME_DURATION_MS', '30'))
        frame_duration_combo = ttk.Combobox(audio_advanced_frame, textvariable=self.frame_duration_var,
                                           values=["10", "20", "30"], state="readonly", width=10)
        frame_duration_combo.grid(row=1, column=1, sticky=tk.W, pady=5, padx=5)
        
        ttk.Label(audio_advanced_frame, text="ms (default: 30)", 
                 font=("Segoe UI", 9), foreground="gray").grid(row=1, column=2, sticky=tk.W, padx=5)
        
        # Warning about advanced settings
        info_advanced = ttk.Label(audio_advanced_frame, 
                                 text="⚠️ Only change these settings if you know what you're doing.\n"
                                      "Incorrect values may cause audio problems.",
                                 font=("Segoe UI", 9), foreground="orange")
        info_advanced.grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=10)
        
        # Network settings
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
        # Main info frame
        main_info_frame = ttk.Frame(parent)
        main_info_frame.pack(fill=tk.BOTH, expand=True, pady=20)
        
        # App logo/title
        title_label = ttk.Label(main_info_frame, text="🎤 HA Assist Desktop", 
                               font=("Segoe UI", 18, "bold"))
        title_label.pack(pady=(0, 10))
        
        # Version info
        version_label = ttk.Label(main_info_frame, text="Voice Assistant for Home Assistant", 
                                 font=("Segoe UI", 12))
        version_label.pack(pady=(0, 20))
        
        # Creator info
        creator_frame = ttk.LabelFrame(main_info_frame, text="Created by", padding="15")
        creator_frame.pack(fill=tk.X, pady=(0, 20))
        
        creator_label = ttk.Label(creator_frame, text="Patryk Smoliński", 
                                 font=("Segoe UI", 14, "bold"))
        creator_label.pack()
        
        # GitHub link
        github_frame = ttk.Frame(creator_frame)
        github_frame.pack(pady=(10, 0))
        
        github_label = ttk.Label(github_frame, text="🔗 GitHub: ", font=("Segoe UI", 11))
        github_label.pack(side=tk.LEFT)
        
        github_link = ttk.Label(github_frame, text="https://github.com/SmolinskiP", 
                               font=("Segoe UI", 11), style="Link.TLabel")
        github_link.pack(side=tk.LEFT)
        github_link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/SmolinskiP"))
        
        # Support section
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
        """Test connection to Home Assistant."""
        host = self.host_entry.get().strip()
        token = self.token_entry.get().strip()
        
        if not host or not token:
            self.test_status_label.config(text="Enter host and token!", style="Error.TLabel")
            return
        
        # Run test in separate thread
        self.test_button.config(state="disabled", text="Testing...")
        self.test_status_label.config(text="Connecting...", style="")
        
        def test_thread():
            try:
                # Create temporary client for testing
                self.test_client = HomeAssistantClient()
                self.test_client.host = host
                self.test_client.token = token
                
                # Run test in new asyncio loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    success, message = loop.run_until_complete(self.test_client.test_connection())
                    
                    # Update UI in main thread
                    self.root.after(0, self._update_test_result, success, message)
                    
                    if success:
                        # If connection OK, get pipelines
                        self.pipelines_data = self.test_client.get_available_pipelines()
                        self.root.after(0, self._update_pipeline_list)
                    
                finally:
                    loop.close()
                    
            except Exception as e:
                error_msg = f"Test error: {str(e)}"
                self.root.after(0, self._update_test_result, False, error_msg)
        
        threading.Thread(target=test_thread, daemon=True).start()
    
    def _update_test_result(self, success, message):
            """Update connection test result."""
            self.test_button.config(state="normal", text="Test Connection")
            
            if success:
                self.test_status_label.config(text=f"✅ {message}", style="Success.TLabel")
                
                # NOWY: Wyślij animację sukcesu do animation server jeśli dostępny
                self._show_success_animation("Connection successful")
            else:
                self.test_status_label.config(text=f"❌ {message}", style="Error.TLabel")
                
                # OPCJONALNIE: Możesz też wysłać animację błędu
                self._show_error_animation(f"Connection failed: {message}")

    def _show_success_animation(self, message):
        """Pokaż animację sukcesu w głównym oknie aplikacji."""
        if self.animation_server:
            # Bezpośrednie użycie animation server
            self.animation_server.show_success(message, duration=3.0)
        else:
            logger.debug("Animation server nie jest dostępny - pomijam animację sukcesu")
    
    def _show_error_animation(self, message):
        """Pokaż animację błędu w głównym oknie aplikacji."""
        if self.animation_server:
            # Bezpośrednie użycie animation server
            self.animation_server.show_error(message, duration=5.0)
        else:
            logger.debug("Animation server nie jest dostępny - pomijam animację błędu")

    def _update_pipeline_list(self):
        """Update pipeline list."""
        if not self.pipelines_data:
            return
        
        # Prepare options for combobox
        pipeline_options = ["(default)"]
        pipeline_mapping = {"(default)": ""}
        
        for pipeline in self.pipelines_data:
            name = pipeline.get("name", "Unnamed")
            pipeline_id = pipeline.get("id", "")
            is_preferred = pipeline.get("is_preferred", False)
            
            # Add star for preferred pipeline
            star = " ⭐" if is_preferred else ""
            display_name = f"{name}{star} (ID: {pipeline_id})"
            
            pipeline_options.append(display_name)
            pipeline_mapping[display_name] = pipeline_id
        
        # Update combobox
        self.pipeline_combo["values"] = pipeline_options
        
        # Set currently selected pipeline
        current_pipeline_id = utils.get_env('HA_PIPELINE_ID', '')
        if current_pipeline_id:
            # Find matching entry in list
            for option, pid in pipeline_mapping.items():
                if pid == current_pipeline_id:
                    self.pipeline_var.set(option)
                    break
            else:
                # Not found - pipeline may have been deleted
                self.pipeline_var.set(f"⚠️ Unknown: {current_pipeline_id}")
        else:
            self.pipeline_var.set("(default)")
        
        # Save mapping for later use
        self.pipeline_mapping = pipeline_mapping
        
        logger.info(f"Updated pipeline list: {len(self.pipelines_data)} available")
    
    def _refresh_pipelines(self):
        """Refresh pipeline list."""
        if not self.test_client or not self.test_client.connected:
            messagebox.showwarning("No Connection", 
                                 "Test connection first to load pipeline list.")
            return
        
        # Get pipelines again
        def refresh_thread():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    loop.run_until_complete(self.test_client.fetch_available_pipelines())
                    self.pipelines_data = self.test_client.get_available_pipelines()
                    self.root.after(0, self._update_pipeline_list)
                    
                finally:
                    loop.close()
                    
            except Exception as e:
                error_msg = f"Refresh error: {str(e)}"
                self.root.after(0, lambda: messagebox.showerror("Error", error_msg))
        
        threading.Thread(target=refresh_thread, daemon=True).start()
    
    def _save_config(self):
        """Save configuration."""
        try:
            # Get selected pipeline
            selected_pipeline_display = self.pipeline_var.get()
            selected_pipeline_id = ""
            
            if hasattr(self, 'pipeline_mapping') and selected_pipeline_display in self.pipeline_mapping:
                selected_pipeline_id = self.pipeline_mapping[selected_pipeline_display]
            elif selected_pipeline_display.startswith("⚠️ Unknown:"):
                # Keep unknown pipeline ID
                selected_pipeline_id = selected_pipeline_display.split(": ", 1)[1]
            
            # Prepare settings to save
            new_settings = {
                'HA_HOST': self.host_entry.get().strip(),
                'HA_TOKEN': self.token_entry.get().strip(),
                'HA_PIPELINE_ID': selected_pipeline_id,
                'HA_HOTKEY': self.hotkey_var.get(),
                'HA_SILENCE_THRESHOLD_SEC': str(round(self.silence_scale.get(), 1)),
                'HA_VAD_MODE': str(int(self.vad_mode_scale.get())),
                'DEBUG': 'true' if self.debug_var.get() else 'false',
                
                # Advanced audio settings
                'HA_SAMPLE_RATE': self.sample_rate_var.get(),
                'HA_FRAME_DURATION_MS': self.frame_duration_var.get(),
                'ANIMATION_PORT': self.animation_port_var.get(),
                'HA_SOUND_FEEDBACK': 'true' if self.sound_feedback_var.get() else 'false',
                
                # Keep current values for hidden settings
                'HA_CHANNELS': utils.get_env('HA_CHANNELS', '1'),
                'HA_PADDING_MS': utils.get_env('HA_PADDING_MS', '300'),
            }
            
            # Validate required fields
            if not new_settings['HA_HOST']:
                messagebox.showerror("Error", "Home Assistant server address is required!")
                return
                
            if not new_settings['HA_TOKEN']:
                messagebox.showerror("Error", "Access token is required!")
                return
            
            # Validate port
            try:
                port = int(new_settings['ANIMATION_PORT'])
                if port < 1024 or port > 65535:
                    messagebox.showerror("Error", "Animation port must be between 1024-65535!")
                    return
            except ValueError:
                messagebox.showerror("Error", "Animation port must be a number!")
                return
            
            # Save to .env file
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
            # Find .env file
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
                    
            # If not found, create new in main directory
            if not env_path:
                env_path = possible_paths[0]
            
            # Prepare .env content with comments
            env_content = "# Home Assistant Assist Settings\n"
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
            
            env_content += "\n# === VOICE DETECTION (VAD) ===\n"
            env_content += f"HA_VAD_MODE={settings['HA_VAD_MODE']}\n"
            env_content += f"HA_SILENCE_THRESHOLD_SEC={settings['HA_SILENCE_THRESHOLD_SEC']}\n"
            
            env_content += "\n# === NETWORK ===\n"
            env_content += f"ANIMATION_PORT={settings['ANIMATION_PORT']}\n"
            env_content += "\n# === AUDIO FEEDBACK ===\n"
            env_content += f"HA_SOUND_FEEDBACK={settings['HA_SOUND_FEEDBACK']}\n"
            env_content += "\n# === DEBUG ===\n"
            env_content += f"DEBUG={settings['DEBUG']}\n"
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(env_path), exist_ok=True)
            
            # Save to file
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


def show_improved_settings(animation_server=None):
    """Helper function to display enhanced settings."""
    dialog = ImprovedSettingsDialog(animation_server)
    dialog.show_settings()