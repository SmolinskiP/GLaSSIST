"""
Cross-platform utility functions for GLaSSIST.
"""
import os
import sys
import platform
import subprocess
import logging
import threading
from pathlib import Path

logger = logging.getLogger('haassist')

def check_linux_dependencies():
    """Check if all required Linux dependencies are available."""
    if platform.system() != "Linux":
        return True
    
    missing = []
    
    # Check GTK/WebKit for webview
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        gi.require_version('WebKit2', '4.0')
        from gi.repository import Gtk, WebKit2
    except ImportError:
        missing.append("python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.0")
    except ValueError:
        missing.append("gtk3-devel, webkit2gtk3-devel")
    
    # Check audio
    try:
        import pyaudio
        # Quick test
        audio = pyaudio.PyAudio()
        audio.terminate()
    except ImportError:
        missing.append("python3-pyaudio, portaudio19-dev")
    except Exception:
        logger.warning("Audio system may not work properly")
    
    if missing:
        print("❌ Missing Linux dependencies:")
        for dep in missing:
            print(f"   • {dep}")
        print("\nInstall with:")
        print("sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.0 python3-pyaudio portaudio19-dev")
        print("or run: ./install-linux.sh")
        return False
    
    return True

def get_icon_path():
    """Get appropriate icon path for current platform."""
    base_path = Path(__file__).parent / 'img'
    
    if platform.system() == "Windows":
        ico_path = base_path / 'icon.ico'
        if ico_path.exists():
            return str(ico_path)
    
    # Linux/macOS prefer PNG
    png_path = base_path / 'icon.png'
    if png_path.exists():
        return str(png_path)
    
    # Fallback to ICO if PNG doesn't exist
    ico_path = base_path / 'icon.ico'
    if ico_path.exists():
        return str(ico_path)
    
    return None

def hide_window_from_taskbar(window_title="GLaSSIST"):
    """Hide window from taskbar - cross-platform implementation."""
    if platform.system() == "Windows":
        return _hide_from_taskbar_windows(window_title)
    elif platform.system() == "Linux":
        return _hide_from_taskbar_linux(window_title)
    else:
        logger.info("Taskbar hiding not implemented for this platform")
        return False

def _hide_from_taskbar_windows(window_title):
    """Windows-specific taskbar hiding using ctypes."""
    try:
        import ctypes
        from ctypes import wintypes
        
        user32 = ctypes.windll.user32
        screen_width = user32.GetSystemMetrics(0)
        screen_height = user32.GetSystemMetrics(1)
        window_width = 500
        window_height = 500
        pos_x = (screen_width - window_width) // 2
        pos_y = screen_height - window_height + 50

        found_windows = []
        
        def enum_windows_proc(hwnd, lParam):
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                window_text = ctypes.create_unicode_buffer(512)
                ctypes.windll.user32.GetWindowTextW(hwnd, window_text, 512)
                class_name = ctypes.create_unicode_buffer(512)
                ctypes.windll.user32.GetClassNameW(hwnd, class_name, 512)
                
                if window_text.value == window_title and "WindowsForms10" in class_name.value:
                    found_windows.append((hwnd, window_text.value, class_name.value))
                    
                    GWL_EXSTYLE = -20
                    WS_EX_TOOLWINDOW = 0x00000080
                    WS_EX_APPWINDOW = 0x00040000
                    
                    current_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                    new_style = (current_style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
                    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
                    
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
                    
                    logger.info(f"Window hidden from taskbar: '{window_text.value}'")
            
            return True
        
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        ctypes.windll.user32.EnumWindows(EnumWindowsProc(enum_windows_proc), 0)
        
        return len(found_windows) > 0
        
    except Exception as e:
        logger.error(f"Windows taskbar hiding failed: {e}")
        return False

def _hide_from_taskbar_linux(window_title):
    """Linux-specific taskbar hiding using wmctrl or xdotool."""
    try:
        # Try wmctrl first
        result = subprocess.run(
            ['wmctrl', '-r', window_title, '-b', 'add,skip_taskbar'], 
            capture_output=True, 
            check=True
        )
        logger.info("Window hidden from taskbar (wmctrl)")
        return True
        
    except (subprocess.CalledProcessError, FileNotFoundError):
        try:
            # Fallback to xdotool
            result = subprocess.run(
                ['xdotool', 'search', '--name', window_title], 
                capture_output=True, 
                text=True, 
                check=True
            )
            
            if result.stdout.strip():
                window_ids = result.stdout.strip().split('\n')
                for window_id in window_ids:
                    subprocess.run(['xdotool', 'set_window', '--class', 'skip_taskbar', window_id])
                logger.info("Window hidden from taskbar (xdotool)")
                return True
                
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("Neither wmctrl nor xdotool available - window will appear in taskbar")
            logger.info("Install with: sudo apt install wmctrl xdotool")
    
    return False

def open_file_manager(path):
    """Open file manager at specified path - cross-platform."""
    try:
        if platform.system() == "Windows":
            subprocess.run(['explorer', str(path)])
        elif platform.system() == "Darwin":  # macOS
            subprocess.run(['open', str(path)])
        else:  # Linux
            subprocess.run(['xdg-open', str(path)])
        return True
    except Exception as e:
        logger.error(f"Failed to open file manager: {e}")
        return False

def check_wake_word_noise_suppression():
    """Check if noise suppression is available for wake word detection."""
    if platform.system() == "Windows":
        # Disabled on Windows due to compatibility issues
        return False
    
    try:
        import speexdsp_ns
        return True
    except ImportError:
        logger.info("Noise suppression not available (install: pip install speexdsp-python)")
        return False
    
def detect_linux_desktop_environment():
    """Detect Linux desktop environment with confidence"""
    desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
    session = os.environ.get('XDG_SESSION_TYPE', 'unknown')
    
    # GNOME detection
    if 'gnome' in desktop or 'ubuntu' in desktop:
        return 'gnome', session
    
    # XFCE detection  
    if 'xfce' in desktop:
        return 'xfce', session
    
    # KDE detection
    if 'kde' in desktop or 'plasma' in desktop:
        return 'kde', session
    
    # Cinnamon
    if 'cinnamon' in desktop:
        return 'cinnamon', session
    
    # MATE
    if 'mate' in desktop:
        return 'mate', session
    
    # Fallback detection przez procesy
    try:
        ps_output = subprocess.run(['ps', 'aux'], capture_output=True, text=True, timeout=5)
        processes = ps_output.stdout.lower()
        
        if 'gnome-shell' in processes:
            return 'gnome', session
        elif 'xfce4-panel' in processes:
            return 'xfce', session
        elif 'plasmashell' in processes:
            return 'kde', session
        elif 'cinnamon' in processes:
            return 'cinnamon', session
        elif 'mate-panel' in processes:
            return 'mate', session
            
    except Exception:
        pass
    
    return 'unknown', session

def check_linux_capabilities():
    """Check what actually works on this Linux system"""
    capabilities = {
        'wmctrl': subprocess.run(['which', 'wmctrl'], capture_output=True).returncode == 0,
        'xdotool': subprocess.run(['which', 'xdotool'], capture_output=True).returncode == 0,
        'xprop': subprocess.run(['which', 'xprop'], capture_output=True).returncode == 0,
        'xwininfo': subprocess.run(['which', 'xwininfo'], capture_output=True).returncode == 0,
    }
    
    logger.info(f"Linux capabilities: {capabilities}")
    return capabilities

class LinuxTrayManager:
    """FIXED: Zarządza system tray na różnych środowiskach Linux bez konfliktów GTK"""
    
    def __init__(self, app_instance):
        self.app = app_instance
        self.desktop_env, self.session_type = detect_linux_desktop_environment()
        self.tray = None
        self.indicator = None
        self._gtk_initialized = False
        self._setup_complete = False
        self._main_context_owned = False
        
        logger.info(f"LinuxTrayManager: {self.desktop_env} on {self.session_type}")
    
    def _check_gtk_main_context(self):
        """Check if GTK main context is already owned"""
        try:
            import gi
            gi.require_version('GLib', '2.0')
            from gi.repository import GLib
            
            main_context = GLib.MainContext.default()
            is_owned = main_context.is_owner()
            
            logger.debug(f"GTK main context owned: {is_owned}")
            return is_owned
            
        except Exception as e:
            logger.debug(f"GTK context check failed: {e}")
            return False
    
    def _can_use_appindicator(self):
        """Check if AppIndicator is available"""
        try:
            import gi
            
            # Try AyatanaAppIndicator first (newer)
            try:
                gi.require_version('AyatanaAppIndicator3', '0.1')
                from gi.repository import AyatanaAppIndicator3
                logger.debug("AyatanaAppIndicator3 available")
                return 'ayatana'
            except (ImportError, ValueError):
                pass
            
            # Try legacy AppIndicator
            try:
                gi.require_version('AppIndicator3', '0.1') 
                from gi.repository import AppIndicator3
                logger.debug("AppIndicator3 available")
                return 'legacy'
            except (ImportError, ValueError):
                pass
                
            return None
            
        except Exception as e:
            logger.debug(f"AppIndicator check failed: {e}")
            return None
    
    def create_tray_icon(self):
        """Create appropriate tray icon for detected environment"""
        
        if self.session_type == 'wayland':
            logger.warning("Wayland detected - tray support limited")
            return self._try_wayland_tray()
        
        # X11 implementations
        if self.desktop_env == 'gnome':
            return self._create_gnome_tray()
        elif self.desktop_env == 'xfce':
            return self._create_xfce_tray()
        elif self.desktop_env == 'kde':
            return self._create_kde_tray()
        else:
            return self._create_generic_tray()
    
    def _create_gnome_tray(self):
        """FIXED: GNOME tray without GTK main loop conflicts"""
        appindicator_type = self._can_use_appindicator()
        
        if not appindicator_type:
            logger.warning("No AppIndicator available for GNOME")
            return self._create_pystray_fallback()
        
        try:
            import gi
            from gi.repository import Gtk, GLib
            
            # Import appropriate AppIndicator
            if appindicator_type == 'ayatana':
                gi.require_version('AyatanaAppIndicator3', '0.1')
                from gi.repository import AyatanaAppIndicator3 as AppIndicator3
                logger.info("Using AyatanaAppIndicator3")
            else:
                gi.require_version('AppIndicator3', '0.1')
                from gi.repository import AppIndicator3
                logger.info("Using legacy AppIndicator3")
            
            # Check if we can safely create indicator
            if self._check_gtk_main_context():
                logger.info("GTK main context already owned - creating deferred tray")
                return self._create_deferred_appindicator(AppIndicator3, Gtk)
            
            # Create indicator immediately
            self.indicator = AppIndicator3.Indicator.new(
                "glassist-desktop",
                "audio-input-microphone-symbolic",
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS
            )
            
            # Set icon
            icon_path = get_icon_path()
            if icon_path and os.path.exists(icon_path):
                self.indicator.set_icon_full(icon_path, "GLaSSIST")
            else:
                # Use system icon as fallback
                self.indicator.set_icon_theme_path("/usr/share/icons/")
                self.indicator.set_icon_full("audio-input-microphone-symbolic", "GLaSSIST")
            
            self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            self.indicator.set_label("GLaSSIST", "GLaSSIST Desktop Voice Assistant")
            
            # Create menu without GLib.idle_add
            menu = self._create_gtk_menu(Gtk)
            self.indicator.set_menu(menu)
            
            logger.info("✅ AppIndicator created successfully")
            return self.indicator
            
        except Exception as e:
            logger.error(f"Failed to create GNOME tray: {e}")
            return self._create_pystray_fallback()
    
    def _create_deferred_appindicator(self, AppIndicator3, Gtk):
        """Create AppIndicator after webview starts GTK main loop"""
        logger.info("Creating deferred AppIndicator")
        
        def setup_deferred():
            """Setup indicator after GTK is ready"""
            retries = 10
            
            for attempt in range(retries):
                try:
                    time.sleep(0.5)  # Wait for GTK to stabilize
                    
                    # Create indicator
                    self.indicator = AppIndicator3.Indicator.new(
                        "glassist-desktop",
                        "audio-input-microphone-symbolic",
                        AppIndicator3.IndicatorCategory.APPLICATION_STATUS
                    )
                    
                    # Set properties
                    icon_path = get_icon_path()
                    if icon_path and os.path.exists(icon_path):
                        self.indicator.set_icon_full(icon_path, "GLaSSIST")
                    
                    self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
                    self.indicator.set_label("GLaSSIST", "GLaSSIST")
                    
                    # Create menu
                    menu = self._create_gtk_menu(Gtk)
                    self.indicator.set_menu(menu)
                    
                    self._setup_complete = True
                    logger.info("✅ Deferred AppIndicator created successfully")
                    break
                    
                except Exception as e:
                    logger.debug(f"Deferred setup attempt {attempt + 1} failed: {e}")
                    if attempt == retries - 1:
                        logger.error("Failed to create deferred AppIndicator")
        
        # Start setup in thread
        threading.Thread(target=setup_deferred, daemon=True).start()
        return "deferred"
    
    def _create_xfce_tray(self):
        """XFCE-specific tray - usually better with pystray"""
        logger.info("XFCE detected - using pystray for better compatibility")
        return self._create_pystray_fallback()
    
    def _create_kde_tray(self):
        """KDE-specific tray"""
        logger.info("KDE detected - trying AppIndicator first")
        
        appindicator_type = self._can_use_appindicator()
        if appindicator_type:
            return self._create_gnome_tray()  # Same logic works for KDE
        else:
            return self._create_pystray_fallback()
    
    def _create_generic_tray(self):
        """Generic fallback tray"""
        logger.info("Generic Linux environment - using pystray")
        return self._create_pystray_fallback()
    
    def _try_wayland_tray(self):
        """Try to create tray on Wayland (very limited support)"""
        logger.warning("Wayland tray support is experimental")
        
        # Only try AppIndicator on Wayland
        if self.desktop_env == 'gnome':
            appindicator_type = self._can_use_appindicator()
            if appindicator_type:
                logger.info("Trying AppIndicator on Wayland")
                return self._create_gnome_tray()
        
        logger.info("No Wayland tray support available")
        return None
    
    def _create_pystray_fallback(self):
        """Create standard pystray icon as fallback"""
        try:
            import pystray
            from PIL import Image
            
            logger.info("Creating pystray fallback icon")
            
            # Load icon
            icon_path = get_icon_path()
            if icon_path and os.path.exists(icon_path):
                try:
                    image = Image.open(icon_path)
                    # Resize if needed
                    if image.size != (64, 64):
                        image = image.resize((64, 64), Image.Resampling.LANCZOS)
                except Exception as e:
                    logger.warning(f"Icon load failed: {e}")
                    image = self._create_fallback_icon()
            else:
                image = self._create_fallback_icon()
            
            # Create menu
            menu = pystray.Menu(
                pystray.MenuItem('🎤 Activate Voice (Ctrl+Shift+H)', self._on_activate_clicked),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem('🎯 Wake Word Status', self._on_wake_status_clicked),
                pystray.MenuItem('🔄 Restart Wake Word', self._on_restart_wake_word_clicked),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem('🔄 Test Connection', self._on_test_clicked),
                pystray.MenuItem('⚙️ Settings', self._on_settings_clicked),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem('❌ Quit GLaSSIST', self._on_quit_clicked)
            )
            
            tray = pystray.Icon(
                "GLaSSIST",
                image,
                "GLaSSIST Desktop Voice Assistant",
                menu
            )
            
            logger.info("✅ Pystray fallback icon created")
            return tray
            
        except ImportError:
            logger.error("pystray not available - no system tray")
            return None
        except Exception as e:
            logger.error(f"Failed to create pystray icon: {e}")
            return None
    
    def _create_gtk_menu(self, Gtk):
        """Create GTK menu for AppIndicator"""
        menu = Gtk.Menu()
        
        # Activate voice
        activate_item = Gtk.MenuItem(label="🎤 Activate Voice (Ctrl+Shift+H)")
        activate_item.connect("activate", self._on_activate_clicked)
        menu.append(activate_item)
        
        # Separator
        separator1 = Gtk.SeparatorMenuItem()
        menu.append(separator1)
        
        # Wake word status
        wake_status_item = Gtk.MenuItem(label="🎯 Wake Word Status")
        wake_status_item.connect("activate", self._on_wake_status_clicked)
        menu.append(wake_status_item)
        
        # Restart wake word
        restart_wake_item = Gtk.MenuItem(label="🔄 Restart Wake Word")
        restart_wake_item.connect("activate", self._on_restart_wake_word_clicked)
        menu.append(restart_wake_item)
        
        # Separator
        separator2 = Gtk.SeparatorMenuItem()
        menu.append(separator2)
        
        # Test connection
        test_item = Gtk.MenuItem(label="🔄 Test Connection")
        test_item.connect("activate", self._on_test_clicked)
        menu.append(test_item)
        
        # Settings
        settings_item = Gtk.MenuItem(label="⚙️ Settings")
        settings_item.connect("activate", self._on_settings_clicked)
        menu.append(settings_item)
        
        # Separator
        separator3 = Gtk.SeparatorMenuItem()
        menu.append(separator3)
        
        # Quit
        quit_item = Gtk.MenuItem(label="❌ Quit GLaSSIST")
        quit_item.connect("activate", self._on_quit_clicked)
        menu.append(quit_item)
        
        menu.show_all()
        return menu
    
    def _create_fallback_icon(self):
        """Create simple fallback icon"""
        from PIL import Image, ImageDraw
        
        image = Image.new('RGBA', (64, 64), color=(0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # Draw microphone-like icon
        draw.ellipse([16, 12, 48, 40], fill='#4fc3f7', outline='white', width=2)
        draw.rectangle([28, 40, 36, 52], fill='#4fc3f7')
        draw.rectangle([20, 52, 44, 56], fill='white', outline='#4fc3f7', width=1)
        
        return image
    
    # Event handlers - work with both GTK and pystray
    def _on_activate_clicked(self, *args):
        """Handle activate voice command"""
        try:
            self.app.trigger_voice_command()
        except Exception as e:
            logger.error(f"Activate voice failed: {e}")
    
    def _on_wake_status_clicked(self, *args):
        """Handle wake word status request"""
        try:
            self.app._show_wake_word_status()
        except Exception as e:
            logger.error(f"Wake word status failed: {e}")
    
    def _on_restart_wake_word_clicked(self, *args):
        """Handle wake word restart"""
        try:
            self.app._restart_wake_word()
        except Exception as e:
            logger.error(f"Wake word restart failed: {e}")
    
    def _on_test_clicked(self, *args):
        """Handle connection test"""
        try:
            self.app._quick_connection_test()
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
    
    def _on_settings_clicked(self, *args):
        """Handle settings dialog"""
        try:
            self.app.open_settings()
        except Exception as e:
            logger.error(f"Settings dialog failed: {e}")
    
    def _on_quit_clicked(self, *args):
        """Handle quit application"""
        try:
            self.app.quit_application()
        except Exception as e:
            logger.error(f"Quit application failed: {e}")
    
    def start_tray(self):
        """FIXED: Start tray without interfering with GTK main loop"""
        if self._setup_complete:
            logger.info("Tray already set up")
            return True
            
        if not self.tray:
            self.tray = self.create_tray_icon()
        
        if not self.tray:
            logger.warning("⚠️ System tray not available - using hotkey only")
            return False
        
        # Handle different tray types
        if self.tray == "deferred":
            logger.info("✅ Deferred tray setup initiated")
            return True
        elif hasattr(self.tray, 'run'):
            # This is pystray - start in thread
            def tray_thread():
                try:
                    logger.info("Starting pystray in thread")
                    self.tray.run()
                except Exception as e:
                    logger.error(f"Pystray thread error: {e}")
            
            threading.Thread(target=tray_thread, daemon=True).start()
            logger.info("✅ Pystray started in background thread")
            return True
        else:
            # This is AppIndicator - already integrated with GTK
            logger.info("✅ AppIndicator integrated with GTK main loop")
            return True
    
    def stop_tray(self):
        """Stop tray icon"""
        try:
            if hasattr(self.tray, 'stop'):
                self.tray.stop()
            elif self.indicator:
                self.indicator.set_status(self.indicator.IndicatorStatus.PASSIVE)
            
            logger.info("Tray icon stopped")
            
        except Exception as e:
            logger.error(f"Error stopping tray: {e}")
    
    def is_available(self):
        """Check if tray is available and working"""
        return self.tray is not None or self._setup_complete

class LinuxWindowManager:
    """Manages window behavior on Linux"""
    
    def __init__(self):
        self.capabilities = check_linux_capabilities()
        self.desktop_env, self.session_type = detect_linux_desktop_environment()
    
    def setup_window_behavior(self, window_title="GLaSSIST"):
        """Setup window for click-through and positioning"""
        
        if self.session_type == 'wayland':
            logger.warning("Wayland detected - limited window management")
            return self._setup_wayland_window(window_title)
        
        # X11 implementation
        return self._setup_x11_window(window_title)
    
    def _setup_x11_window(self, window_title):
        """Setup window behavior on X11"""
        
        # Poczekaj na okno
        window_id = self._wait_for_window(window_title, timeout=10)
        if not window_id:
            logger.error("❌ Window not found for setup")
            return False
        
        success = True
        
        # 1. Make click-through
        if not self._make_click_through(window_id):
            logger.warning("⚠️ Click-through setup failed")
            success = False
        
        # 2. Position window
        if not self._position_window(window_id):
            logger.warning("⚠️ Window positioning failed")
            success = False
        
        # 3. Set window properties
        if not self._set_window_properties(window_id):
            logger.warning("⚠️ Window properties setup failed")
            success = False
        
        return success
    
    def _wait_for_window(self, window_title, timeout=10):
        """Wait for window to appear and return its ID"""
        import time
        
        for attempt in range(timeout * 2):  # Check every 0.5s
            window_id = self._find_window_id(window_title)
            if window_id:
                logger.info(f"✅ Found window: {window_id}")
                return window_id
            
            time.sleep(0.5)
        
        return None
    
    def _find_window_id(self, window_title):
        """Find window ID by title"""
        
        # Try wmctrl first
        if self.capabilities['wmctrl']:
            try:
                result = subprocess.run(
                    ['wmctrl', '-l'], 
                    capture_output=True, 
                    text=True, 
                    check=True
                )
                
                for line in result.stdout.split('\n'):
                    if window_title.lower() in line.lower():
                        return line.split()[0]
                        
            except Exception as e:
                logger.debug(f"wmctrl failed: {e}")
        
        # Try xdotool
        if self.capabilities['xdotool']:
            try:
                result = subprocess.run(
                    ['xdotool', 'search', '--name', window_title], 
                    capture_output=True, 
                    text=True, 
                    check=True
                )
                
                window_ids = result.stdout.strip().split('\n')
                if window_ids and window_ids[0]:
                    return window_ids[0]
                    
            except Exception as e:
                logger.debug(f"xdotool search failed: {e}")
        
        return None
    
    def _make_click_through(self, window_id):
        """Make window click-through (input passthrough)"""
        
        if not self.capabilities['xprop']:
            logger.warning("xprop not available for click-through")
            return False
        
        try:
            # Method 1: Set input hints to false
            subprocess.run([
                'xprop', '-id', window_id, 
                '-f', 'WM_HINTS', '32c', 
                '-set', 'WM_HINTS', '0x00000000'  # No input
            ], check=False, capture_output=True)
            
            # Method 2: Set window to not accept focus
            subprocess.run([
                'xprop', '-id', window_id,
                '-f', '_NET_WM_STATE', '32a',
                '-set', '_NET_WM_STATE', '_NET_WM_STATE_ABOVE,_NET_WM_STATE_SKIP_TASKBAR'
            ], check=False, capture_output=True)
            
            # Method 3: XFCE specific - set as desktop type
            if self.desktop_env == 'xfce':
                subprocess.run([
                    'xprop', '-id', window_id,
                    '-f', '_NET_WM_WINDOW_TYPE', '32a',
                    '-set', '_NET_WM_WINDOW_TYPE', '_NET_WM_WINDOW_TYPE_DESKTOP'
                ], check=False, capture_output=True)
            
            logger.info("✅ Click-through properties set")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set click-through: {e}")
            return False
    
    def _position_window(self, window_id):
        """Position window at bottom center"""
        
        try:
            # Get screen dimensions
            screen_info = self._get_screen_dimensions()
            if not screen_info:
                return False
            
            screen_width, screen_height = screen_info
            
            # Calculate position
            window_width = 400
            window_height = 400
            x = (screen_width - window_width) // 2
            y = screen_height - window_height - 80  # 80px from bottom
            
            # Position using xdotool if available
            if self.capabilities['xdotool']:
                subprocess.run([
                    'xdotool', 'windowmove', window_id, str(x), str(y)
                ], check=True)
                
                subprocess.run([
                    'xdotool', 'windowsize', window_id, str(window_width), str(window_height)
                ], check=True)
                
                logger.info(f"✅ Window positioned at ({x}, {y})")
                return True
            
            # Fallback to wmctrl
            elif self.capabilities['wmctrl']:
                subprocess.run([
                    'wmctrl', '-i', '-r', window_id, 
                    '-e', f'0,{x},{y},{window_width},{window_height}'
                ], check=True)
                
                logger.info(f"✅ Window positioned with wmctrl")
                return True
            
        except Exception as e:
            logger.error(f"Failed to position window: {e}")
        
        return False
    
    def _get_screen_dimensions(self):
        """Get screen dimensions"""
        
        try:
            # Try xdpyinfo
            result = subprocess.run(
                ['xdpyinfo'], 
                capture_output=True, 
                text=True, 
                check=True
            )
            
            for line in result.stdout.split('\n'):
                if 'dimensions:' in line:
                    # Parse: "dimensions:    1920x1080 pixels (507x285 millimeters)"
                    dimensions = line.split(':')[1].strip().split()[0]
                    width, height = map(int, dimensions.split('x'))
                    return width, height
                    
        except Exception:
            pass
        
        try:
            # Fallback: try xrandr
            result = subprocess.run(
                ['xrandr'], 
                capture_output=True, 
                text=True, 
                check=True
            )
            
            for line in result.stdout.split('\n'):
                if ' connected primary ' in line or ' connected ' in line:
                    # Parse: "DP-1 connected primary 1920x1080+0+0"
                    parts = line.split()
                    for part in parts:
                        if 'x' in part and '+' in part:
                            resolution = part.split('+')[0]
                            width, height = map(int, resolution.split('x'))
                            return width, height
                            
        except Exception:
            pass
        
        # Last resort - assume common resolution
        logger.warning("Could not detect screen size, assuming 1920x1080")
        return 1920, 1080
    
    def _set_window_properties(self, window_id):
        """Set additional window properties"""
        
        if not self.capabilities['xprop']:
            return False
        
        try:
            # Always on top
            subprocess.run([
                'xprop', '-id', window_id,
                '-f', '_NET_WM_STATE', '32a',
                '-set', '_NET_WM_STATE', '_NET_WM_STATE_ABOVE'
            ], check=False, capture_output=True)
            
            # Skip taskbar
            subprocess.run([
                'xprop', '-id', window_id,
                '-f', '_NET_WM_STATE', '32a',
                '-set', '_NET_WM_STATE', '_NET_WM_STATE_ABOVE,_NET_WM_STATE_SKIP_TASKBAR,_NET_WM_STATE_SKIP_PAGER'
            ], check=False, capture_output=True)
            
            logger.info("✅ Window properties set")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set window properties: {e}")
            return False
    
    def _setup_wayland_window(self, window_title):
        """Limited Wayland window setup"""
        logger.warning("⚠️ Wayland: Limited window management capabilities")
        logger.info("💡 Consider using X11 session for full functionality")
        return False
