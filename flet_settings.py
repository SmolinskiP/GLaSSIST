"""
Flet-based settings dialog for GLaSSIST Desktop
Replaces the problematic Tkinter-based settings
"""
import flet as ft
import asyncio
import os
import threading
import webbrowser
import subprocess
import platform as platform_module
import utils
from client import HomeAssistantClient
from audio import AudioManager

logger = utils.setup_logger()

class FletSettingsApp:
    def __init__(self, animation_server=None):
        self.animation_server = animation_server
        self.pipelines_data = []
        self.test_client = None
        self.mic_mapping = {}
        
    async def main(self, page: ft.Page):
        """Main Flet application entry point"""
        page.title = "GLaSSIST Settings"
        page.theme_mode = ft.ThemeMode.SYSTEM
        page.window_width = 1400
        page.window_height = 1000
        page.window_resizable = True
        
        # Try different fullscreen approaches
        try:
            page.window_maximized = True
        except:
            try:
                page.window_full_screen = True
            except:
                pass
        
        # Center window manually (window_center() not available in older Flet versions)
        try:
            page.window_center()
        except (AttributeError, TypeError):
            # Fallback for older Flet versions
            pass
        
        # Set app icon if available
        icon_path = os.path.join(os.path.dirname(__file__), 'img', 'icon.ico')
        if os.path.exists(icon_path):
            try:
                page.window_icon = icon_path
                logger.info(f"Settings window icon set: {icon_path}")
            except Exception as e:
                logger.debug(f"Could not set window icon: {e}")
        
        # Also try setting window icon via different property names
        try:
            page.window_icon_path = icon_path
        except:
            pass
        
        # Handle window closing properly
        def on_window_event(e):
            if e.data == "close":
                logger.info("Settings window closing...")
                try:
                    # Cleanup and close
                    page.window_destroy()
                except:
                    pass
        
        page.on_window_event = on_window_event
        
        # Handle keyboard shortcuts
        def on_keyboard(e):
            if e.key == "Escape":
                logger.info("Escape pressed - closing settings")
                page.window_close()
        
        page.on_keyboard_event = on_keyboard
        
        # Load current settings
        current_settings = self._load_current_settings()
        
        # Create main layout
        self.page = page
        await self._create_ui(current_settings)
        
    def _load_current_settings(self):
        """Load current settings from environment"""
        return {
            'HA_HOST': utils.get_env('HA_HOST', 'localhost:8123'),
            'HA_TOKEN': utils.get_env('HA_TOKEN', ''),
            'HA_PIPELINE_ID': utils.get_env('HA_PIPELINE_ID', ''),
            'HA_HOTKEY': utils.get_env('HA_HOTKEY', 'ctrl+shift+h'),
            'HA_VAD_MODE': utils.get_env('HA_VAD_MODE', 3, int),
            'HA_SILENCE_THRESHOLD_SEC': utils.get_env('HA_SILENCE_THRESHOLD_SEC', 0.8, float),
            'HA_SOUND_FEEDBACK': utils.get_env('HA_SOUND_FEEDBACK', 'true'),
            'HA_MICROPHONE_INDEX': utils.get_env('HA_MICROPHONE_INDEX', -1, int),
            'DEBUG': utils.get_env('DEBUG', 'false'),
            'HA_ANIMATIONS_ENABLED': utils.get_env('HA_ANIMATIONS_ENABLED', 'true'),
            'HA_RESPONSE_TEXT_ENABLED': utils.get_env('HA_RESPONSE_TEXT_ENABLED', 'true'),
            'HA_SAMPLE_RATE': utils.get_env('HA_SAMPLE_RATE', '16000'),
            'HA_FRAME_DURATION_MS': utils.get_env('HA_FRAME_DURATION_MS', '30'),
            'ANIMATION_PORT': utils.get_env('ANIMATION_PORT', '8765'),
            'HA_WAKE_WORD_ENABLED': utils.get_env('HA_WAKE_WORD_ENABLED', 'false'),
            'HA_WAKE_WORD_MODELS': utils.get_env('HA_WAKE_WORD_MODELS', 'alexa'),
            'HA_WAKE_WORD_THRESHOLD': utils.get_env('HA_WAKE_WORD_THRESHOLD', 0.5, float),
            'HA_WAKE_WORD_VAD_THRESHOLD': utils.get_env('HA_WAKE_WORD_VAD_THRESHOLD', 0.3, float),
            'HA_WAKE_WORD_NOISE_SUPPRESSION': utils.get_env('HA_WAKE_WORD_NOISE_SUPPRESSION', 'false'),
            'HA_MEDIA_PLAYER_ENTITIES': utils.get_env('HA_MEDIA_PLAYER_ENTITIES', ''),
            'HA_MEDIA_PLAYER_TARGET_VOLUME': utils.get_env('HA_MEDIA_PLAYER_TARGET_VOLUME', 0.3, float),
        }
    
    async def _create_ui(self, current_settings):
        """Create the main UI"""
        # Title with icon
        title = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.SETTINGS, size=32, color=ft.Colors.BLUE_600),
                    ft.Text(
                        "GLaSSIST Desktop Settings",
                        size=28,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.BLUE_800
                    )
                ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
                ft.Text(
                    "🎤 Voice Assistant Configuration",
                    size=14,
                    color=ft.Colors.GREY_600,
                    text_align=ft.TextAlign.CENTER
                )
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.only(bottom=20)
        )
        
        # Create tabs with scrollable content
        tabs = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            expand=1,
            scrollable=True,
            tabs=[
                ft.Tab(
                    text="Connection",
                    icon=ft.Icons.WIFI,
                    content=await self._create_connection_tab(current_settings)
                ),
                ft.Tab(
                    text="Audio & VAD", 
                    icon=ft.Icons.MIC,
                    content=await self._create_audio_tab(current_settings)
                ),
                ft.Tab(
                    text="Wake Word",
                    icon=ft.Icons.RECORD_VOICE_OVER,
                    content=await self._create_wake_word_tab(current_settings)
                ),
                ft.Tab(
                    text="Media Players",
                    icon=ft.Icons.VOLUME_UP,
                    content=await self._create_media_players_tab(current_settings)
                ),
                ft.Tab(
                    text="Advanced",
                    icon=ft.Icons.SETTINGS_APPLICATIONS,
                    content=await self._create_advanced_tab(current_settings)
                ),
                ft.Tab(
                    text="About",
                    icon=ft.Icons.INFO_OUTLINE,
                    content=await self._create_about_tab()
                )
            ]
        )
        
        # Action buttons
        button_row = ft.Row([
            ft.FilledTonalButton(
                "Test Connection", 
                icon=ft.Icons.WIFI_FIND,
                on_click=self._test_connection_async
            ),
            ft.FilledButton(
                "Save Settings",
                icon=ft.Icons.SAVE,
                on_click=self._save_settings_async
            )
        ], 
        alignment=ft.MainAxisAlignment.END,
        spacing=10
        )
        
        # Main layout with scroll - fixed buttons at bottom
        main_container = ft.Column([
            ft.Container(
                content=ft.Column([
                    title,
                    ft.Divider(height=2),
                    tabs,
                ], 
                spacing=10,
                scroll=ft.ScrollMode.AUTO
                ),
                padding=ft.padding.only(left=30, right=30, top=30),
                expand=True
            ),
            ft.Container(
                content=ft.Column([
                    ft.Divider(height=2),
                    button_row
                ]),
                padding=ft.padding.only(left=30, right=30, bottom=30)
            )
        ], expand=True)
        
        self.page.add(main_container)
        
        # Auto-refresh wake word models after all UI is created
        try:
            await self._refresh_wake_word_models()
            logger.info("Wake word models refreshed on startup")
        except Exception as e:
            logger.debug(f"Could not refresh models on startup: {e}")
    
    async def _create_connection_tab(self, current_settings):
        """Create connection settings tab"""
        # Input fields
        self.host_field = ft.TextField(
            label="Home Assistant Server Address",
            value=current_settings['HA_HOST'],
            prefix_icon=ft.Icons.HOME,
            helper_text="e.g., homeassistant.local:8123 or 192.168.1.100:8123",
            expand=True
        )
        
        self.token_field = ft.TextField(
            label="Long-Lived Access Token",
            value=current_settings['HA_TOKEN'],
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.Icons.KEY,
            helper_text="Generate in Home Assistant: Profile → Long-Lived Access Tokens",
            expand=True
        )
        
        # Status display
        self.connection_status = ft.Text(
            "Click 'Test Connection' to verify settings",
            size=14,
            color=ft.Colors.GREY_600
        )
        
        # Pipeline dropdown  
        self.pipeline_dropdown = ft.Dropdown(
            label="Assist Pipeline",
            helper_text="Test connection first to load available pipelines",
            options=[ft.dropdown.Option("(default)", "")],
            value="",
            expand=True
        )
        
        # Set current pipeline
        current_pipeline = current_settings.get('HA_PIPELINE_ID', '')
        if current_pipeline:
            self.pipeline_dropdown.options.append(
                ft.dropdown.Option(f"Current: {current_pipeline}", current_pipeline)
            )
            self.pipeline_dropdown.value = current_pipeline
        
        return ft.Container(
            content=ft.Column([
                # Connection settings card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("🔗 Connection Settings", size=18, weight=ft.FontWeight.BOLD),
                            self.host_field,
                            self.token_field,
                            ft.Container(height=10),
                            ft.Row([
                                ft.ElevatedButton(
                                    "Test Connection",
                                    icon=ft.Icons.WIFI_FIND,
                                    on_click=self._test_connection_async
                                ),
                                ft.Container(expand=True),
                                self.connection_status
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ]),
                        padding=20
                    ),
                    elevation=2
                ),
                
                # Pipeline selection card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("🎯 Pipeline Selection", size=18, weight=ft.FontWeight.BOLD),
                            ft.Text(
                                "Pipeline determines how the assistant processes your voice commands. "
                                "Different pipelines may use different STT/TTS engines or languages.",
                                color=ft.Colors.GREY_700,
                                size=13
                            ),
                            ft.Container(height=10),
                            ft.Row([
                                self.pipeline_dropdown,
                                ft.ElevatedButton(
                                    "Refresh",
                                    icon=ft.Icons.REFRESH,
                                    on_click=self._refresh_pipelines_async
                                )
                            ], spacing=10)
                        ]),
                        padding=20
                    ),
                    elevation=2
                )
            ]),
            padding=10
        )
    
    async def _create_audio_tab(self, current_settings):
        """Create audio settings tab"""
        # Hotkey dropdown
        self.hotkey_dropdown = ft.Dropdown(
            label="Activation Hotkey",
            value=current_settings['HA_HOTKEY'],
            options=[
                ft.dropdown.Option("ctrl+shift+h"),
                ft.dropdown.Option("ctrl+shift+g"), 
                ft.dropdown.Option("ctrl+alt+h"),
                ft.dropdown.Option("alt+space"),
                ft.dropdown.Option("ctrl+shift+space"),
            ],
            expand=True
        )
        
        # Sound feedback switch
        self.sound_feedback_switch = ft.Switch(
            label="Play activation/deactivation sounds",
            value=current_settings['HA_SOUND_FEEDBACK'] == 'true',
            active_color=ft.Colors.GREEN_600
        )
        
        # VAD sensitivity slider
        self.vad_slider = ft.Slider(
            min=0, max=3, divisions=3,
            value=current_settings['HA_VAD_MODE'],
            label="VAD Mode: {value}",
            on_change=self._on_vad_change,
            active_color=ft.Colors.BLUE_600
        )
        
        self.vad_value_text = ft.Text(f"Current: {current_settings['HA_VAD_MODE']}", size=14)
        
        # Silence threshold slider  
        self.silence_slider = ft.Slider(
            min=0.3, max=3.0, divisions=27,
            value=current_settings['HA_SILENCE_THRESHOLD_SEC'],
            label="Silence: {value}s", 
            on_change=self._on_silence_change,
            active_color=ft.Colors.ORANGE_600
        )
        
        self.silence_value_text = ft.Text(f"Current: {current_settings['HA_SILENCE_THRESHOLD_SEC']:.1f}s", size=14)
        
        # Microphone dropdown
        self.microphone_dropdown = ft.Dropdown(
            label="Microphone Device",
            helper_text="Select specific microphone or use automatic detection",
            options=[ft.dropdown.Option("(automatic)", -1)],
            value=-1,
            expand=True
        )
        
        # Load microphones asynchronously
        await self._refresh_microphones_async()
        
        
        # Auto-refresh pipelines if we have connection details
        host = self.host_field.value.strip()
        token = self.token_field.value.strip()
        if host and token:
            try:
                # Try to load pipelines in background
                asyncio.create_task(self._auto_load_pipelines(host, token))
            except Exception as e:
                logger.debug(f"Could not auto-load pipelines: {e}")
        
        return ft.Container(
            content=ft.Column([
                # Activation card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("🎤 Activation Settings", size=18, weight=ft.FontWeight.BOLD),
                            self.hotkey_dropdown,
                            ft.Container(height=10),
                            self.sound_feedback_switch,
                            ft.Text(
                                "Plays activation.wav and deactivation.wav from the 'sound' folder",
                                color=ft.Colors.GREY_600, size=12
                            )
                        ]),
                        padding=20
                    ),
                    elevation=2
                ),
                
                # Voice detection card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("🔊 Voice Activity Detection (VAD)", size=18, weight=ft.FontWeight.BOLD),
                            ft.Container(height=10),
                            ft.Text("Voice detection sensitivity:", size=14, weight=ft.FontWeight.W_500),
                            self.vad_slider,
                            self.vad_value_text,
                            ft.Text("0 = least sensitive (quiet environments), 3 = most sensitive (noisy environments)", 
                                   size=12, color=ft.Colors.GREY_600),
                            ft.Container(height=15),
                            ft.Text("Silence threshold (recording end delay):", size=14, weight=ft.FontWeight.W_500),
                            self.silence_slider,
                            self.silence_value_text,
                            ft.Text("How long to wait for silence before ending recording",
                                   size=12, color=ft.Colors.GREY_600)
                        ]),
                        padding=20
                    ),
                    elevation=2
                ),
                
                # Microphone card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("🎙️ Microphone Selection", size=18, weight=ft.FontWeight.BOLD),
                            ft.Row([
                                self.microphone_dropdown,
                                ft.ElevatedButton(
                                    "Refresh",
                                    icon=ft.Icons.REFRESH,
                                    on_click=lambda _: asyncio.create_task(self._refresh_microphones_async())
                                )
                            ], spacing=10),
                            ft.Text(
                                "Select 'automatic' to use system default microphone",
                                size=12, color=ft.Colors.GREY_600
                            )
                        ]),
                        padding=20
                    ),
                    elevation=2
                )
            ]),
            padding=10
        )
    
    async def _create_wake_word_tab(self, current_settings):
        """Create wake word settings tab"""
        # Wake word enable switch
        self.wake_word_enabled = ft.Switch(
            label="Enable wake word detection",
            value=current_settings['HA_WAKE_WORD_ENABLED'] == 'true',
            on_change=self._on_wake_word_toggle,
            active_color=ft.Colors.GREEN_600
        )
        
        # Check openWakeWord status
        try:
            import openwakeword
            status_text = "✅ openWakeWord installed and ready"
            status_color = ft.Colors.GREEN_600
        except ImportError:
            status_text = "❌ openWakeWord not installed - run: pip install openwakeword"
            status_color = ft.Colors.RED_600
        
        # Models management
        self.available_models_dropdown = ft.Dropdown(
            label="Available Models",
            options=[
                ft.dropdown.Option("alexa"),
                ft.dropdown.Option("hey_jarvis"),
                ft.dropdown.Option("hey_mycroft"),
                ft.dropdown.Option("timers"),
                ft.dropdown.Option("weather"),
            ],
            value="alexa",
            expand=True
        )
        
        # Selected models list
        self.selected_models_column = ft.Column(spacing=5, scroll=ft.ScrollMode.AUTO, height=200)
        
        # Threshold sliders
        self.wake_threshold_slider = ft.Slider(
            min=0.1, max=1.0, divisions=90,
            value=current_settings['HA_WAKE_WORD_THRESHOLD'],
            label="Detection: {value}",
            on_change=self._on_wake_threshold_change,
            active_color=ft.Colors.PURPLE_600
        )
        
        self.wake_threshold_text = ft.Text(f"Current: {current_settings['HA_WAKE_WORD_THRESHOLD']:.2f}", size=14)
        
        self.vad_threshold_slider = ft.Slider(
            min=0.0, max=1.0, divisions=100,
            value=current_settings['HA_WAKE_WORD_VAD_THRESHOLD'],
            label="VAD: {value}",
            on_change=self._on_wake_vad_change,
            active_color=ft.Colors.CYAN_600
        )
        
        self.vad_threshold_text = ft.Text(f"Current: {current_settings['HA_WAKE_WORD_VAD_THRESHOLD']:.2f}", size=14)
        
        # Noise suppression
        self.noise_suppression_switch = ft.Switch(
            label="Enable noise suppression",
            value=current_settings['HA_WAKE_WORD_NOISE_SUPPRESSION'] == 'true',
            active_color=ft.Colors.INDIGO_600
        )
        
        # Populate selected models
        await self._populate_wake_word_models(current_settings['HA_WAKE_WORD_MODELS'])
        
        # Enable/disable controls based on initial state
        await self._toggle_wake_word_controls()
        
        return ft.Container(
            content=ft.Column([
                # Activation card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("🎤 Wake Word Activation", size=18, weight=ft.FontWeight.BOLD),
                            self.wake_word_enabled,
                            ft.Text(
                                "Allows voice activation using words like 'Alexa', 'Hey Jarvis', etc.",
                                color=ft.Colors.GREY_600, size=12
                            ),
                            ft.Container(height=10),
                            ft.Text(status_text, size=14, color=status_color, weight=ft.FontWeight.BOLD)
                        ]),
                        padding=20
                    ),
                    elevation=2
                ),
                
                # Model configuration card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("📋 Model Configuration", size=18, weight=ft.FontWeight.BOLD),
                            ft.Row([
                                self.available_models_dropdown,
                                ft.ElevatedButton(
                                    "Add Model",
                                    icon=ft.Icons.ADD,
                                    on_click=self._add_wake_word_model
                                )
                            ], spacing=10),
                            ft.Container(height=10),
                            ft.Text("Selected Models:", size=14, weight=ft.FontWeight.W_500),
                            ft.Container(
                                content=self.selected_models_column,
                                border=ft.border.all(1, ft.Colors.GREY_300),
                                border_radius=8,
                                padding=10
                            )
                        ]),
                        padding=20
                    ),
                    elevation=2
                ),
                
                # Detection settings card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("🎯 Detection Settings", size=18, weight=ft.FontWeight.BOLD),
                            ft.Container(height=10),
                            ft.Text("Detection threshold:", size=14, weight=ft.FontWeight.W_500),
                            self.wake_threshold_slider,
                            self.wake_threshold_text,
                            ft.Text("Higher = less sensitive (fewer false positives, but may miss quiet words)",
                                   size=12, color=ft.Colors.GREY_600),
                            ft.Container(height=15),
                            ft.Text("Voice activity threshold:", size=14, weight=ft.FontWeight.W_500),
                            self.vad_threshold_slider,
                            self.vad_threshold_text,
                            ft.Text("Helps reduce false activations from non-speech sounds (0.0 = disabled)",
                                   size=12, color=ft.Colors.GREY_600),
                            ft.Container(height=15),
                            self.noise_suppression_switch
                        ]),
                        padding=20
                    ),
                    elevation=2
                ),
                
                # Management card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("📦 Model Management", size=18, weight=ft.FontWeight.BOLD),
                            ft.Row([
                                ft.ElevatedButton(
                                    "Open Models Folder",
                                    icon=ft.Icons.FOLDER_OPEN,
                                    on_click=self._open_models_folder
                                )
                            ], spacing=10, wrap=True),
                            ft.Container(height=10),
                            ft.Text(
                                "💡 Tips: Start with 'alexa' model - it's most reliable. "
                                "Higher thresholds = fewer false activations. "
                                "Test different settings for your environment.",
                                size=12, color=ft.Colors.BLUE_700,
                                text_align=ft.TextAlign.LEFT
                            )
                        ]),
                        padding=20
                    ),
                    elevation=2
                )
            ]),
            padding=10
        )
    
    async def _create_media_players_tab(self, current_settings):
        """Create media players volume management tab"""
        # Media player entities selection
        self.media_player_entities_field = ft.TextField(
            label="Media Player Entities (comma-separated)",
            value=current_settings['HA_MEDIA_PLAYER_ENTITIES'],
            helper_text="e.g., media_player.living_room,media_player.bedroom",
            prefix_icon=ft.Icons.SPEAKER,
            expand=True,
            multiline=True,
            min_lines=2,
            max_lines=4
        )
        
        # Available media players list
        self.available_players_column = ft.Column(spacing=5, scroll=ft.ScrollMode.AUTO, height=350)
        
        # Target volume slider
        self.target_volume_slider = ft.Slider(
            min=0.0, max=1.0, divisions=100,
            value=current_settings['HA_MEDIA_PLAYER_TARGET_VOLUME'],
            label="Volume: {value}%",
            on_change=self._on_target_volume_change,
            active_color=ft.Colors.GREEN_600
        )
        
        self.target_volume_text = ft.Text(f"Target: {int(current_settings['HA_MEDIA_PLAYER_TARGET_VOLUME'] * 100)}%", size=14)
        
        # Load available media players if we have connection
        await self._refresh_media_players_async()
        
        return ft.Container(
            content=ft.Column([
                # Configuration card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("🔊 Volume Management Configuration", size=18, weight=ft.FontWeight.BOLD),
                            ft.Text(
                                "GLaSSIST can automatically adjust media player volumes during voice interactions. "
                                "Select media players below or enter entity IDs manually.",
                                color=ft.Colors.GREY_700,
                                size=13
                            ),
                            ft.Container(height=10),
                            ft.Text("Target volume during voice interaction:", size=14, weight=ft.FontWeight.W_500),
                            self.target_volume_slider,
                            self.target_volume_text,
                            ft.Text("Volume will be temporarily set to this level, then restored after interaction",
                                   size=12, color=ft.Colors.GREY_600)
                        ]),
                        padding=20
                    ),
                    elevation=2
                ),
                
                # Manual entry card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("📝 Manual Entity Configuration", size=18, weight=ft.FontWeight.BOLD),
                            self.media_player_entities_field,
                            ft.Text("Enter entity IDs separated by commas. Use the list below to find available entities.",
                                   size=12, color=ft.Colors.GREY_600)
                        ]),
                        padding=20
                    ),
                    elevation=2
                ),
                
                # Available players card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("🎵 Available Media Players", size=18, weight=ft.FontWeight.BOLD),
                            ft.Row([
                                ft.ElevatedButton(
                                    "Refresh List",
                                    icon=ft.Icons.REFRESH,
                                    on_click=lambda _: asyncio.create_task(self._refresh_media_players_async())
                                ),
                                ft.ElevatedButton(
                                    "Add All",
                                    icon=ft.Icons.ADD_CIRCLE,
                                    on_click=self._add_all_media_players
                                ),
                                ft.ElevatedButton(
                                    "Clear All",
                                    icon=ft.Icons.CLEAR,
                                    on_click=self._clear_media_players
                                )
                            ], spacing=10),
                            ft.Container(height=10),
                            ft.Text("Click entities to add them to your configuration:", size=14, weight=ft.FontWeight.W_500),
                            ft.Container(
                                content=self.available_players_column,
                                border=ft.border.all(1, ft.Colors.GREY_300),
                                border_radius=8,
                                padding=10
                            )
                        ]),
                        padding=20
                    ),
                    elevation=2
                )
            ]),
            padding=10
        )
    
    async def _create_advanced_tab(self, current_settings):
        """Create advanced settings tab"""
        # Interface settings
        self.animations_switch = ft.Switch(
            label="Enable visual animations (Three.js)",
            value=current_settings['HA_ANIMATIONS_ENABLED'] == 'true',
            active_color=ft.Colors.PURPLE_600
        )
        
        self.response_text_switch = ft.Switch(
            label="Show response text on screen",
            value=current_settings['HA_RESPONSE_TEXT_ENABLED'] == 'true', 
            active_color=ft.Colors.BLUE_600
        )
        
        # Debug mode
        self.debug_switch = ft.Switch(
            label="Debug mode (detailed logs)",
            value=current_settings['DEBUG'] == 'true',
            active_color=ft.Colors.ORANGE_600
        )
        
        # Audio settings
        self.sample_rate_dropdown = ft.Dropdown(
            label="Sample Rate (Hz)",
            value=current_settings['HA_SAMPLE_RATE'],
            options=[
                ft.dropdown.Option("8000"),
                ft.dropdown.Option("16000"),
                ft.dropdown.Option("22050"),
                ft.dropdown.Option("44100"),
                ft.dropdown.Option("48000"),
            ],
            expand=True
        )
        
        self.frame_duration_dropdown = ft.Dropdown(
            label="VAD Frame Duration (ms)",
            value=current_settings['HA_FRAME_DURATION_MS'],
            options=[
                ft.dropdown.Option("10"),
                ft.dropdown.Option("20"),
                ft.dropdown.Option("30"),
            ],
            expand=True
        )
        
        # Network settings
        self.animation_port_field = ft.TextField(
            label="Animation Server Port",
            value=current_settings['ANIMATION_PORT'],
            helper_text="Port for WebSocket animation server (1024-65535)",
            prefix_icon=ft.Icons.ROUTER
        )
        
        return ft.Container(
            content=ft.Column([
                # Interface card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("🎨 Interface & Performance", size=18, weight=ft.FontWeight.BOLD),
                            self.animations_switch,
                            ft.Text("Three.js animations with audio visualization. Disable to save CPU/memory.",
                                   color=ft.Colors.GREY_600, size=12),
                            ft.Container(height=10),
                            self.response_text_switch,
                            ft.Text("Display assistant responses as animated text overlay.",
                                   color=ft.Colors.GREY_600, size=12)
                        ]),
                        padding=20
                    ),
                    elevation=2
                ),
                
                # Debug card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("🐛 Debugging", size=18, weight=ft.FontWeight.BOLD),
                            self.debug_switch,
                            ft.Text("Enables detailed logging to help diagnose issues",
                                   color=ft.Colors.GREY_600, size=12)
                        ]),
                        padding=20
                    ),
                    elevation=2
                ),
                
                # Advanced audio card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("🔧 Advanced Audio Settings", size=18, weight=ft.FontWeight.BOLD),
                            ft.Text("⚠️ Only change these if you know what you're doing!",
                                   color=ft.Colors.ORANGE_600, size=14, weight=ft.FontWeight.BOLD),
                            ft.Row([
                                self.sample_rate_dropdown,
                                self.frame_duration_dropdown
                            ], spacing=20),
                            ft.Text("Default: 16000 Hz, 30ms frame duration works best for most setups",
                                   color=ft.Colors.GREY_600, size=12)
                        ]),
                        padding=20
                    ),
                    elevation=2
                ),
                
                # Network card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("🌐 Network Settings", size=18, weight=ft.FontWeight.BOLD),
                            self.animation_port_field,
                            ft.Text("WebSocket port for browser-based animations. Change if port conflicts occur.",
                                   color=ft.Colors.GREY_600, size=12)
                        ]),
                        padding=20
                    ),
                    elevation=2
                )
            ]),
            padding=10
        )
    
    async def _create_about_tab(self):
        """Create about tab"""
        return ft.Container(
            content=ft.Column([
                ft.Container(height=40),
                ft.Text("🎤 GLaSSIST Desktop", size=32, weight=ft.FontWeight.BOLD,
                       text_align=ft.TextAlign.CENTER),
                ft.Text("Voice Assistant for Home Assistant", size=18, color=ft.Colors.GREY_600,
                       text_align=ft.TextAlign.CENTER),
                ft.Container(height=40),
                
                # Creator card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("👨‍💻 Created by", size=18, weight=ft.FontWeight.BOLD,
                                   text_align=ft.TextAlign.CENTER),
                            ft.Text("Patryk Smoliński", size=24, weight=ft.FontWeight.BOLD,
                                   text_align=ft.TextAlign.CENTER, color=ft.Colors.BLUE_600),
                            ft.Container(height=15),
                            ft.ElevatedButton(
                                "🔗 Visit GitHub Profile",
                                icon=ft.Icons.OPEN_IN_NEW,
                                on_click=lambda _: webbrowser.open("https://github.com/SmolinskiP")
                            )
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=30
                    ),
                    elevation=2
                ),
                
                # Support card
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("☕ Support the Project", size=18, weight=ft.FontWeight.BOLD,
                                   text_align=ft.TextAlign.CENTER),
                            ft.Text("Like my work? Buy me a coffee!", size=16,
                                   text_align=ft.TextAlign.CENTER, color=ft.Colors.GREY_700),
                            ft.Container(height=15),
                            ft.ElevatedButton(
                                "☕ Buy me a coffee",
                                icon=ft.Icons.FAVORITE,
                                style=ft.ButtonStyle(bgcolor=ft.Colors.ORANGE_600),
                                on_click=lambda _: webbrowser.open("https://buymeacoffee.com/smolinskip")
                            )
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=30
                    ),
                    elevation=2
                ),
            ], 
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=20),
            padding=20
        )
    
    # Event handlers
    def _on_vad_change(self, e):
        self.vad_value_text.value = f"Current: {int(e.control.value)}"
        self.page.update()
    
    def _on_silence_change(self, e):
        self.silence_value_text.value = f"Current: {e.control.value:.1f}s"
        self.page.update()
    
    def _on_wake_threshold_change(self, e):
        self.wake_threshold_text.value = f"Current: {e.control.value:.2f}"
        self.page.update()
    
    def _on_wake_vad_change(self, e):
        self.vad_threshold_text.value = f"Current: {e.control.value:.2f}"
        self.page.update()
    
    def _on_target_volume_change(self, e):
        volume_percent = int(e.control.value * 100)
        self.target_volume_text.value = f"Target: {volume_percent}%"
        self.page.update()
    
    async def _on_wake_word_toggle(self, e):
        await self._toggle_wake_word_controls()
        
    async def _toggle_wake_word_controls(self):
        """Enable/disable wake word controls based on main switch"""
        enabled = self.wake_word_enabled.value
        
        # List of controls to toggle
        controls = [
            self.available_models_dropdown,
            self.wake_threshold_slider,
            self.vad_threshold_slider,
            self.noise_suppression_switch
        ]
        
        for control in controls:
            control.disabled = not enabled
        
        # Also disable the selected models
        for control in self.selected_models_column.controls:
            if hasattr(control, 'trailing') and hasattr(control.trailing, 'disabled'):
                control.trailing.disabled = not enabled
        
        self.page.update()
    
    # Async operations
    async def _test_connection_async(self, e):
        """Test connection to Home Assistant"""
        self.connection_status.value = "Testing connection..."
        self.connection_status.color = ft.Colors.ORANGE_600
        self.page.update()
        
        try:
            host = self.host_field.value.strip()
            token = self.token_field.value.strip()
            
            if not host or not token:
                self.connection_status.value = "❌ Please enter both host and token"
                self.connection_status.color = ft.Colors.RED_600
                self.page.update()
                return
            
            # Test connection in thread to avoid blocking UI
            def test_connection():
                try:
                    test_client = HomeAssistantClient()
                    test_client.host = host
                    test_client.token = token
                    
                    # Run in new event loop
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    try:
                        success, message = loop.run_until_complete(test_client.test_connection())
                        
                        if success:
                            # Try to get pipelines
                            try:
                                pipelines = test_client.get_available_pipelines()
                                return True, message, pipelines
                            except Exception:
                                return True, message, []
                        else:
                            return False, message, []
                    finally:
                        loop.close()
                        
                except Exception as ex:
                    return False, str(ex), []
            
            # Run in thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(test_connection)
                success, message, pipelines = future.result(timeout=30)
            
            if success:
                self.connection_status.value = f"✅ {message}"
                self.connection_status.color = ft.Colors.GREEN_600
                
                if self.animation_server:
                    self.animation_server.show_success("Connection successful", duration=3.0)
                
                # Update pipelines
                if pipelines:
                    self.pipelines_data = pipelines
                    await self._update_pipeline_dropdown()
                    
            else:
                self.connection_status.value = f"❌ {message}"
                self.connection_status.color = ft.Colors.RED_600
                
                if self.animation_server:
                    self.animation_server.show_error(f"Connection failed", duration=5.0)
                
        except concurrent.futures.TimeoutError:
            self.connection_status.value = "❌ Connection timeout (30s)"
            self.connection_status.color = ft.Colors.RED_600
        except Exception as ex:
            self.connection_status.value = f"❌ Error: {str(ex)}"
            self.connection_status.color = ft.Colors.RED_600
            logger.error(f"Connection test failed: {ex}")
        
        self.page.update()
    
    async def _refresh_pipelines_async(self, e):
        """Refresh pipelines list"""
        # First test connection to get fresh pipeline data
        await self._test_connection_async(e)
    
    async def _update_pipeline_dropdown(self):
        """Update pipeline dropdown with fresh data"""
        options = [ft.dropdown.Option(text="(default)", key="")]
        
        for pipeline in self.pipelines_data:
            name = pipeline.get("name", "Unnamed")
            pipeline_id = pipeline.get("id", "")
            is_preferred = pipeline.get("is_preferred", False)
            
            star = " ⭐" if is_preferred else ""
            display_name = f"{name}{star}"
            
            options.append(ft.dropdown.Option(text=display_name, key=pipeline_id))
        
        self.pipeline_dropdown.options = options
        
        # Set current value if it exists
        current_pipeline_id = utils.get_env('HA_PIPELINE_ID', '')
        if current_pipeline_id:
            # Find matching option
            for option in options:
                if option.key == current_pipeline_id:
                    self.pipeline_dropdown.value = current_pipeline_id
                    break
            else:
                # Current pipeline not found, add it
                self.pipeline_dropdown.options.append(
                    ft.dropdown.Option(f"⚠️ Unknown: {current_pipeline_id}", current_pipeline_id)
                )
                self.pipeline_dropdown.value = current_pipeline_id
        
        self.page.update()
        logger.info(f"Updated pipeline list: {len(self.pipelines_data)} available")
    
    async def _refresh_microphones_async(self):
        """Refresh microphone list"""
        try:
            def get_mics():
                temp_audio = AudioManager()
                temp_audio.init_audio()
                mics = temp_audio.get_available_microphones()
                temp_audio.close_audio()
                return mics
            
            # Run in thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(get_mics)
                microphones = future.result(timeout=10)
            
            options = [ft.dropdown.Option(text="(automatic)", key=-1)]
            self.mic_mapping = {"(automatic)": -1}
            
            for mic in microphones:
                # Handle special characters in microphone names
                try:
                    mic_name = mic['name']
                    # Clean up problematic characters
                    if isinstance(mic_name, bytes):
                        mic_name = mic_name.decode('utf-8', errors='replace')
                    
                    # Replace common problematic characters
                    mic_name = str(mic_name).replace('\x00', '').strip()
                    
                    if not mic_name or len(mic_name) == 0:
                        mic_name = f"Microphone {mic['index']}"
                        
                except Exception as e:
                    logger.debug(f"Error processing mic name: {e}")
                    mic_name = f"Microphone {mic['index']}"
                
                display_name = f"{mic_name} (ID: {mic['index']})"
                options.append(ft.dropdown.Option(text=display_name, key=mic['index']))
                self.mic_mapping[display_name] = mic['index']
            
            self.microphone_dropdown.options = options
            
            # Set current selection
            current_mic_index = utils.get_env("HA_MICROPHONE_INDEX", -1, int)
            if current_mic_index == -1:
                self.microphone_dropdown.value = -1
            else:
                # Find matching microphone
                found = False
                for option in options:
                    if option.key == current_mic_index:
                        self.microphone_dropdown.value = current_mic_index
                        found = True
                        break
                
                if not found:
                    # Add unknown microphone
                    options.append(ft.dropdown.Option(f"⚠️ Unknown: {current_mic_index}", current_mic_index))
                    self.microphone_dropdown.value = current_mic_index
            
            self.page.update()
            logger.info(f"Loaded {len(microphones)} microphones")
            
        except Exception as e:
            logger.error(f"Failed to refresh microphones: {e}")
            self.microphone_dropdown.options = [ft.dropdown.Option("(automatic)", -1), 
                                               ft.dropdown.Option("Error loading microphones", -2)]
            self.microphone_dropdown.value = -1
            self.page.update()
    
    async def _populate_wake_word_models(self, models_string):
        """Populate selected wake word models"""
        if isinstance(models_string, str):
            models = [m.strip() for m in models_string.split(',') if m.strip()]
        else:
            models = models_string if models_string else []
        
        self.selected_models_column.controls.clear()
        
        for model in models:
            model_tile = ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.MIC, size=20, color=ft.Colors.BLUE_600),
                    ft.Text(model, expand=True, size=14, color=ft.Colors.BLACK),
                    ft.IconButton(
                        ft.Icons.DELETE,
                        icon_color=ft.Colors.RED_600,
                        tooltip="Remove model",
                        on_click=lambda e, m=model: self._remove_model_by_name(m)
                    )
                ]),
                padding=10,
                border_radius=8,
                bgcolor=ft.Colors.BLUE_50,
                border=ft.border.all(1, ft.Colors.BLUE_200)
            )
            self.selected_models_column.controls.append(model_tile)
        
        if not models:
            self.selected_models_column.controls.append(
                ft.Text("No models selected", color=ft.Colors.GREY_500, italic=True)
            )
        
        self.page.update()
    
    def _add_wake_word_model(self, e):
        """Add wake word model to selected list"""
        model = self.available_models_dropdown.value
        if not model:
            return
            
        # Check if already exists
        for control in self.selected_models_column.controls:
            if hasattr(control, 'content') and hasattr(control.content, 'controls'):
                row = control.content
                if len(row.controls) > 1 and hasattr(row.controls[1], 'value'):
                    if row.controls[1].value == model:
                        return  # Already exists
        
        # Remove "no models" message if present
        if (len(self.selected_models_column.controls) == 1 and 
            isinstance(self.selected_models_column.controls[0], ft.Text)):
            self.selected_models_column.controls.clear()
        
        # Add new model
        model_tile = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.MIC, size=20, color=ft.Colors.BLUE_600),
                ft.Text(model, expand=True, size=14, color=ft.Colors.BLACK),
                ft.IconButton(
                    ft.Icons.DELETE,
                    icon_color=ft.Colors.RED_600,
                    tooltip="Remove model",
                    on_click=lambda _, m=model: self._remove_model_by_name(m)
                )
            ]),
            padding=10,
            border_radius=8,
            bgcolor=ft.Colors.BLUE_50,
            border=ft.border.all(1, ft.Colors.BLUE_200)
        )
        
        self.selected_models_column.controls.append(model_tile)
        self.page.update()
        
        logger.info(f"Added wake word model: {model}")
    
    def _remove_model_by_name(self, model_name):
        """Remove model by name"""
        self.selected_models_column.controls = [
            control for control in self.selected_models_column.controls 
            if not (hasattr(control, 'content') and 
                   hasattr(control.content, 'controls') and
                   len(control.content.controls) > 1 and
                   hasattr(control.content.controls[1], 'value') and
                   control.content.controls[1].value == model_name)
        ]
        
        # Add "no models" message if empty
        if not self.selected_models_column.controls:
            self.selected_models_column.controls.append(
                ft.Text("No models selected", color=ft.Colors.GREY_500, italic=True)
            )
        
        self.page.update()
        logger.info(f"Removed wake word model: {model_name}")
    
    async def _refresh_media_players_async(self):
        """Refresh available media players list"""
        try:
            host = getattr(self, 'host_field', None)
            token = getattr(self, 'token_field', None)
            
            if not host or not token or not host.value.strip() or not token.value.strip():
                self.available_players_column.controls.clear()
                self.available_players_column.controls.append(
                    ft.Text("Enter connection details and test connection first", 
                           color=ft.Colors.GREY_500, italic=True)
                )
                self.page.update()
                return
            
            def get_media_players():
                test_client = HomeAssistantClient()
                test_client.host = host.value.strip()
                test_client.token = token.value.strip()
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # Connect and get media players
                    success = loop.run_until_complete(test_client.connect())
                    if success:
                        media_players = loop.run_until_complete(test_client.get_media_player_entities())
                        return True, media_players
                    return False, []
                finally:
                    loop.run_until_complete(test_client.close())
                    loop.close()
            
            # Run in thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(get_media_players)
                success, media_players = future.result(timeout=15)
            
            self.available_players_column.controls.clear()
            
            if success and media_players:
                for player in media_players:
                    entity_id = player['entity_id']
                    friendly_name = player['friendly_name']
                    current_volume = player['current_volume']
                    
                    volume_text = f"Volume: {int(current_volume * 100)}%" if current_volume is not None else "Volume: N/A"
                    
                    player_tile = ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.SPEAKER, size=20, color=ft.Colors.BLUE_600),
                            ft.Column([
                                ft.Text(friendly_name, size=14, weight=ft.FontWeight.W_500, color=ft.Colors.BLACK),
                                ft.Text(entity_id, size=12, weight=ft.FontWeight.W_500, color=ft.Colors.BLUE_800),
                                ft.Text(volume_text, size=11, color=ft.Colors.GREY_700)
                            ], spacing=2, expand=True),
                            ft.IconButton(
                                ft.Icons.ADD,
                                icon_color=ft.Colors.GREEN_600,
                                tooltip="Add to configuration",
                                on_click=lambda e, eid=entity_id: self._add_media_player_entity(eid)
                            )
                        ]),
                        padding=10,
                        border_radius=8,
                        bgcolor=ft.Colors.BLUE_50,
                        border=ft.border.all(1, ft.Colors.BLUE_200)
                    )
                    self.available_players_column.controls.append(player_tile)
                
                logger.info(f"Loaded {len(media_players)} media players")
            else:
                self.available_players_column.controls.append(
                    ft.Text("No media players found or connection failed", 
                           color=ft.Colors.ORANGE_600, italic=True)
                )
            
            self.page.update()
            
        except Exception as e:
            logger.error(f"Failed to refresh media players: {e}")
            self.available_players_column.controls.clear()
            self.available_players_column.controls.append(
                ft.Text(f"Error loading media players: {str(e)}", 
                       color=ft.Colors.RED_600, italic=True)
            )
            self.page.update()
    
    def _add_media_player_entity(self, entity_id):
        """Add media player entity to the configuration field"""
        current_entities = self.media_player_entities_field.value.strip()
        entity_list = [e.strip() for e in current_entities.split(',') if e.strip()]
        
        if entity_id not in entity_list:
            entity_list.append(entity_id)
            self.media_player_entities_field.value = ','.join(entity_list)
            self.page.update()
            logger.info(f"Added media player entity: {entity_id}")
    
    def _add_all_media_players(self, e):
        """Add all available media players to configuration"""
        entity_ids = []
        for control in self.available_players_column.controls:
            if hasattr(control, 'content') and hasattr(control.content, 'controls'):
                row = control.content
                if len(row.controls) > 1 and hasattr(row.controls[1], 'controls'):
                    column = row.controls[1]
                    if len(column.controls) > 1:
                        entity_text = column.controls[1].value  # entity_id text
                        if entity_text.startswith('media_player.'):
                            entity_ids.append(entity_text)
        
        if entity_ids:
            self.media_player_entities_field.value = ','.join(entity_ids)
            self.page.update()
            logger.info(f"Added all media players: {len(entity_ids)} entities")
    
    def _clear_media_players(self, e):
        """Clear all media player entities"""
        self.media_player_entities_field.value = ""
        self.page.update()
        logger.info("Cleared all media player entities")
    
    async def _refresh_wake_word_models(self):
        """Refresh available wake word models list"""
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
            
            # Update dropdown options
            options = []
            for model in available_models:
                options.append(ft.dropdown.Option(text=model, key=model))
            
            self.available_models_dropdown.options = options
            if available_models:
                self.available_models_dropdown.value = available_models[0]
            
            # Force UI update
            if hasattr(self, 'page') and self.page:
                self.page.update()
            
            logger.info(f"Refreshed wake word models: {len(available_models)} models available")
            
        except Exception as e:
            logger.error(f"Failed to refresh wake word models: {e}")
    
    async def _auto_load_pipelines(self, host, token):
        """Auto-load pipelines in background"""
        try:
            def load_pipelines():
                test_client = HomeAssistantClient()
                test_client.host = host
                test_client.token = token
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    success, _ = loop.run_until_complete(test_client.test_connection())
                    if success:
                        pipelines = test_client.get_available_pipelines()
                        return True, pipelines
                    return False, []
                finally:
                    loop.close()
            
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(load_pipelines)
                success, pipelines = future.result(timeout=10)
            
            if success and pipelines:
                self.pipelines_data = pipelines
                await self._update_pipeline_dropdown()
                logger.info(f"Auto-loaded {len(pipelines)} pipelines")
                
        except Exception as e:
            logger.debug(f"Auto-load pipelines failed: {e}")
    
    async def _download_models_async(self, e):
        """Download default openWakeWord models"""
        logger.info("🔥 DOWNLOAD MODELS CLICKED!")
        try:
            import openwakeword
        except ImportError:
            await self._show_dialog("Error", 
                "openWakeWord not installed!\n\nInstall with: pip install openwakeword")
            return
        
        # Show progress
        progress_dialog = ft.AlertDialog(
            title=ft.Text("Downloading Models"),
            content=ft.Column([
                ft.Text("Downloading default wake word models..."),
                ft.ProgressRing()
            ], height=100, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            modal=True
        )
        
        self.page.dialog = progress_dialog
        progress_dialog.open = True
        self.page.update()
        
        try:
            def download():
                import openwakeword.utils
                openwakeword.utils.download_models()
                return True
            
            # Run in thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(download)
                success = future.result(timeout=120)  # 2 minute timeout
            
            progress_dialog.open = False
            self.page.update()
            
            if success:
                await self._show_dialog("Success", 
                    "Default wake word models downloaded successfully!\n\n"
                    "Available models:\n• alexa\n• hey_jarvis\n• hey_mycroft\n• timers\n• weather")
                
                if self.animation_server:
                    self.animation_server.show_success("Models downloaded", duration=3.0)
                
                # Refresh models list after download
                await self._refresh_wake_word_models()
            
        except concurrent.futures.TimeoutError:
            progress_dialog.open = False
            self.page.update()
            await self._show_dialog("Error", "Download timeout. Please try again.")
        except Exception as ex:
            progress_dialog.open = False
            self.page.update()
            await self._show_dialog("Error", f"Failed to download models: {str(ex)}")
            logger.error(f"Model download failed: {ex}")
    
    def _open_models_folder(self, e):
        """Open models folder"""
        try:
            models_dir = os.path.join(os.path.dirname(__file__), 'models')
            
            if not os.path.exists(models_dir):
                os.makedirs(models_dir)
            
            # Cross-platform folder opening
            if platform_module.system() == "Windows":
                os.startfile(models_dir)
            elif platform_module.system() == "Darwin":  # macOS
                subprocess.run(["open", models_dir])
            else:  # Linux
                subprocess.run(["xdg-open", models_dir])
                
            logger.info(f"Opened models folder: {models_dir}")
            
        except Exception as ex:
            asyncio.create_task(self._show_dialog("Error", f"Failed to open models folder: {str(ex)}"))
            logger.error(f"Failed to open models folder: {ex}")
    
    async def _test_wake_word_async(self, e):
        """Test wake word detection"""
        if not self.wake_word_enabled.value:
            await self._show_dialog("Wake Word Disabled", "Enable wake word detection first!")
            return
        
        try:
            import openwakeword
        except ImportError:
            await self._show_dialog("Error", "openWakeWord not installed!\n\nInstall with: pip install openwakeword")
            return
        
        # Get selected models
        selected_models = []
        for control in self.selected_models_column.controls:
            if (hasattr(control, 'content') and hasattr(control.content, 'controls') and
                len(control.content.controls) > 1 and hasattr(control.content.controls[1], 'value')):
                selected_models.append(control.content.controls[1].value)
        
        if not selected_models:
            await self._show_dialog("No Models", "Please select at least one wake word model first!")
            return
        
        # Show test dialog
        test_dialog = ft.AlertDialog(
            title=ft.Text("🎤 Wake Word Detection Test"),
            content=ft.Column([
                ft.Text(f"Selected models: {', '.join(selected_models)}", size=14),
                ft.Text(f"Detection threshold: {self.wake_threshold_slider.value:.2f}", size=14),
                ft.Container(height=10),
                ft.Text("This is a simulation. For real testing, save settings and restart GLaSSIST.", 
                       color=ft.Colors.BLUE_600, size=12),
                ft.Container(height=10),
                ft.Text("🔴 Click 'Start Test' and say one of your wake words!", 
                       color=ft.Colors.RED_600, weight=ft.FontWeight.BOLD)
            ], height=150),
            actions=[
                ft.TextButton("Start Test", on_click=lambda _: self._simulate_test(test_dialog)),
                ft.TextButton("Close", on_click=lambda _: self._close_dialog(test_dialog))
            ],
            modal=True
        )
        
        self.page.dialog = test_dialog
        test_dialog.open = True
        self.page.update()
    
    def _simulate_test(self, dialog):
        """Simulate wake word test"""
        # Update dialog content to show "listening"
        dialog.content = ft.Column([
            ft.Text("🔴 Listening for wake words...", color=ft.Colors.RED_600, 
                   weight=ft.FontWeight.BOLD, size=16),
            ft.Text("Say one of your selected wake words!", size=14),
            ft.Container(height=10),
            ft.ProgressRing()
        ], height=120, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        
        dialog.actions = [ft.TextButton("Stop Test", on_click=lambda _: self._close_dialog(dialog))]
        self.page.update()
        
        # After 5 seconds, show completion
        def complete_test():
            import time
            time.sleep(5)
            
            # Update to completion state
            dialog.content = ft.Column([
                ft.Text("✅ Test completed!", color=ft.Colors.GREEN_600, 
                       weight=ft.FontWeight.BOLD, size=16),
                ft.Text("For real wake word testing, save your settings and restart GLaSSIST.", 
                       size=14, color=ft.Colors.BLUE_600),
                ft.Container(height=10),
                ft.Text("💡 Tip: Adjust thresholds if you get too many false positives or missed detections.",
                       size=12, color=ft.Colors.GREY_600)
            ], height=120, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            
            dialog.actions = [ft.TextButton("Close", on_click=lambda _: self._close_dialog(dialog))]
            self.page.update()
        
        threading.Thread(target=complete_test, daemon=True).start()
    
    async def _save_settings_async(self, e):
        """Save all settings to .env file"""
        logger.info("🔥 SAVE SETTINGS CLICKED!")
        try:
            # Validate required fields
            if not self.host_field.value.strip():
                await self._show_dialog("Validation Error", "Home Assistant server address is required!")
                return
                
            if not self.token_field.value.strip():
                await self._show_dialog("Validation Error", "Access token is required!")
                return
            
            # Validate wake word settings if enabled
            if self.wake_word_enabled.value:
                selected_models = []
                for control in self.selected_models_column.controls:
                    if (hasattr(control, 'content') and hasattr(control.content, 'controls') and
                        len(control.content.controls) > 1 and hasattr(control.content.controls[1], 'value')):
                        selected_models.append(control.content.controls[1].value)
                
                if not selected_models:
                    await self._show_dialog("Validation Error", "Select at least one wake word model when wake word detection is enabled!")
                    return
                
                try:
                    import openwakeword
                except ImportError:
                    await self._show_dialog("Validation Error", 
                        "openWakeWord not installed!\n\nInstall with: pip install openwakeword\nor disable wake word detection.")
                    return
            else:
                selected_models = ['alexa']  # Default fallback
            
            # Validate animation port
            try:
                port = int(self.animation_port_field.value)
                if port < 1024 or port > 65535:
                    await self._show_dialog("Validation Error", "Animation port must be between 1024-65535!")
                    return
            except ValueError:
                await self._show_dialog("Validation Error", "Animation port must be a number!")
                return
            
            # Get selected microphone index
            selected_mic_index = self.microphone_dropdown.value
            if selected_mic_index is None:
                selected_mic_index = -1
            
            # Get selected pipeline ID  
            selected_pipeline_id = self.pipeline_dropdown.value
            if selected_pipeline_id is None:
                selected_pipeline_id = ""
            
            # Debug - log what we're saving
            logger.info(f"Saving settings:")
            logger.info(f"  Host: {self.host_field.value}")
            logger.info(f"  Pipeline ID: {selected_pipeline_id}")
            logger.info(f"  Microphone: {selected_mic_index}")
            logger.info(f"  Wake word enabled: {self.wake_word_enabled.value}")
            
            # Prepare settings dictionary
            new_settings = {
                'HA_HOST': self.host_field.value.strip(),
                'HA_TOKEN': self.token_field.value.strip(),
                'HA_PIPELINE_ID': selected_pipeline_id,
                'HA_HOTKEY': self.hotkey_dropdown.value,
                'HA_SILENCE_THRESHOLD_SEC': str(round(self.silence_slider.value, 1)),
                'HA_VAD_MODE': str(int(self.vad_slider.value)),
                'HA_MICROPHONE_INDEX': str(selected_mic_index),
                'HA_SOUND_FEEDBACK': 'true' if self.sound_feedback_switch.value else 'false',
                'DEBUG': 'true' if self.debug_switch.value else 'false',
                'HA_ANIMATIONS_ENABLED': 'true' if self.animations_switch.value else 'false',
                'HA_RESPONSE_TEXT_ENABLED': 'true' if self.response_text_switch.value else 'false',
                'HA_SAMPLE_RATE': self.sample_rate_dropdown.value,
                'HA_FRAME_DURATION_MS': self.frame_duration_dropdown.value,
                'ANIMATION_PORT': self.animation_port_field.value,
                
                # Preserved settings
                'HA_CHANNELS': utils.get_env('HA_CHANNELS', '1'),
                'HA_PADDING_MS': utils.get_env('HA_PADDING_MS', '300'),
                
                # Wake word settings
                'HA_WAKE_WORD_ENABLED': 'true' if self.wake_word_enabled.value else 'false',
                'HA_WAKE_WORD_MODELS': ','.join(selected_models),
                'HA_WAKE_WORD_THRESHOLD': str(round(self.wake_threshold_slider.value, 2)),
                'HA_WAKE_WORD_VAD_THRESHOLD': str(round(self.vad_threshold_slider.value, 2)),
                'HA_WAKE_WORD_NOISE_SUPPRESSION': 'true' if self.noise_suppression_switch.value else 'false',
                
                # Media player settings
                'HA_MEDIA_PLAYER_ENTITIES': self.media_player_entities_field.value.strip(),
                'HA_MEDIA_PLAYER_TARGET_VOLUME': str(round(self.target_volume_slider.value, 2))
            }
            
            # Save to .env file
            result = self._save_env_file(new_settings)
            
            if result['success']:
                await self._show_dialog("Settings Saved", 
                    f"{result['message']}\n\nRestart GLaSSIST to apply changes.",
                    on_close=lambda: self.page.window_close())
                
                if self.animation_server:
                    self.animation_server.show_success("Settings saved", duration=3.0)
            else:
                await self._show_dialog("Save Error", result['message'])
                
        except Exception as ex:
            logger.error(f"Error saving settings: {ex}")
            await self._show_dialog("Save Error", f"Failed to save settings: {str(ex)}")
    
    def _save_env_file(self, settings):
        """Save settings to .env file"""
        try:
            # Find .env file location
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
            
            # Generate .env content
            env_content = "# GLaSSIST Desktop Settings\n"
            env_content += "# Generated by Flet-based settings dialog\n\n"
            
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
            env_content += f"HA_ANIMATIONS_ENABLED={settings['HA_ANIMATIONS_ENABLED']}\n"
            env_content += f"HA_RESPONSE_TEXT_ENABLED={settings['HA_RESPONSE_TEXT_ENABLED']}\n"

            env_content += "\n# === NETWORK ===\n"
            env_content += f"ANIMATION_PORT={settings['ANIMATION_PORT']}\n"
            
            env_content += "\n# === AUDIO FEEDBACK ===\n"
            env_content += f"HA_SOUND_FEEDBACK={settings['HA_SOUND_FEEDBACK']}\n"

            env_content += "\n# === WAKE WORD DETECTION ===\n"
            env_content += f"HA_WAKE_WORD_ENABLED={settings['HA_WAKE_WORD_ENABLED']}\n"
            env_content += f"HA_WAKE_WORD_MODELS={settings['HA_WAKE_WORD_MODELS']}\n"
            env_content += f"HA_WAKE_WORD_THRESHOLD={settings['HA_WAKE_WORD_THRESHOLD']}\n"
            env_content += f"HA_WAKE_WORD_VAD_THRESHOLD={settings['HA_WAKE_WORD_VAD_THRESHOLD']}\n"
            env_content += f"HA_WAKE_WORD_NOISE_SUPPRESSION={settings['HA_WAKE_WORD_NOISE_SUPPRESSION']}\n"
            
            env_content += "\n# === MEDIA PLAYER VOLUME MANAGEMENT ===\n"
            env_content += f"HA_MEDIA_PLAYER_ENTITIES={settings['HA_MEDIA_PLAYER_ENTITIES']}\n"
            env_content += f"HA_MEDIA_PLAYER_TARGET_VOLUME={settings['HA_MEDIA_PLAYER_TARGET_VOLUME']}\n"
            
            env_content += "\n# === DEBUG ===\n"
            env_content += f"DEBUG={settings['DEBUG']}\n"
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(env_path), exist_ok=True)
            
            # Write file
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
    
    async def _show_dialog(self, title, message, on_close=None):
        """Show dialog with message"""
        dialog = ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Text(message),
            actions=[
                ft.TextButton("OK", on_click=lambda _: self._close_dialog(dialog, on_close))
            ],
            modal=True
        )
        
        self.page.dialog = dialog
        dialog.open = True
        self.page.update()
    
    def _close_dialog(self, dialog, callback=None):
        """Close dialog and optionally call callback"""
        dialog.open = False
        self.page.update()
        if callback:
            callback()


def show_flet_settings(animation_server=None):
    """Show Flet-based settings dialog - main entry point"""
    try:
        app = FletSettingsApp(animation_server)
        # Use threading to avoid signal issues when called from tray menu
        import threading
        
        def run_flet():
            try:
                # Disable signal handling in Flet to avoid threading issues
                import signal
                original_signal = signal.signal
                
                def dummy_signal(*args, **kwargs):
                    # Just ignore signal setup attempts
                    pass
                
                # Temporarily replace signal handler during Flet startup
                signal.signal = dummy_signal
                
                try:
                    ft.app(target=app.main, view=ft.FLET_APP)
                finally:
                    # Restore original signal handler
                    signal.signal = original_signal
                    logger.info("Flet settings app closed")
                    
            except Exception as e:
                logger.error(f"Flet app error: {e}")
            finally:
                # Ensure cleanup
                logger.debug("Flet thread cleanup completed")
        
        # Run in separate daemon thread so it dies with main app
        thread = threading.Thread(target=run_flet, daemon=True)
        thread.start()
        
        logger.info("Flet settings started in daemon thread")
        
    except Exception as e:
        logger.error(f"Failed to show Flet settings: {e}")
        raise


def show_flet_settings_process(animation_server=None):
    """Alternative: Run Flet in separate process (more isolated)"""
    try:
        import subprocess
        import sys
        import os
        
        # Get path to this file
        script_path = os.path.abspath(__file__)
        
        # Run as separate process
        subprocess.Popen([sys.executable, script_path], 
                        creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)
        
        logger.info("Flet settings started in separate process")
        
    except Exception as e:
        logger.error(f"Failed to start Flet settings process: {e}")
        raise


if __name__ == "__main__":
    # Test the settings dialog
    show_flet_settings()