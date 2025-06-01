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
    
    # KDE jako bonus (bo czemu nie)
    if 'kde' in desktop or 'plasma' in desktop:
        return 'kde', session
    
    # Fallback detection przez procesy
    try:
        ps_output = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        processes = ps_output.stdout.lower()
        
        if 'gnome-shell' in processes:
            return 'gnome', session
        elif 'xfce4-panel' in processes:
            return 'xfce', session
        elif 'plasmashell' in processes:
            return 'kde', session
            
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
    """Zarządza system tray na różnych środowiskach Linux"""
    
    def __init__(self, app_instance):
        self.app = app_instance
        self.desktop_env, self.session_type = detect_linux_desktop_environment()
        self.tray = None
        
        logger.info(f"Detected: {self.desktop_env} on {self.session_type}")
    
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
        else:
            return self._create_generic_tray()
    
    def _create_gnome_tray(self):
        """GNOME-specific tray (AppIndicator)"""
        try:
            # Spróbuj różne wersje AppIndicator
            indicator = None
            
            # Najpierw Ayatana (nowszy)
            try:
                import gi
                gi.require_version('AyatanaAppIndicator3', '0.1')
                from gi.repository import AyatanaAppIndicator3 as AppIndicator3
                from gi.repository import Gtk
                
                indicator = AppIndicator3.Indicator.new(
                    "glassist-desktop",
                    "audio-input-microphone",
                    AppIndicator3.IndicatorCategory.APPLICATION_STATUS
                )
                logger.info("Using AyatanaAppIndicator3")
                
            except (ImportError, ValueError):
                # Fallback do starego AppIndicator
                try:
                    import gi
                    gi.require_version('AppIndicator3', '0.1')
                    from gi.repository import AppIndicator3
                    from gi.repository import Gtk
                    
                    indicator = AppIndicator3.Indicator.new(
                        "glassist-desktop",
                        "audio-input-microphone",
                        AppIndicator3.IndicatorCategory.APPLICATION_STATUS
                    )
                    logger.info("Using legacy AppIndicator3")
                    
                except (ImportError, ValueError):
                    logger.warning("No AppIndicator available for GNOME")
                    return None
            
            if indicator:
                return self._setup_appindicator_menu(indicator, Gtk)
                
        except Exception as e:
            logger.error(f"Failed to create GNOME tray: {e}")
            return None
    
    def _create_xfce_tray(self):
        """XFCE-specific tray (pystray works better here)"""
        try:
            # XFCE ma lepsze wsparcie dla standardowego system tray
            return self._create_pystray_icon()
            
        except Exception as e:
            logger.error(f"Failed to create XFCE tray: {e}")
            return None
    
    def _create_generic_tray(self):
        """Generic fallback tray"""
        return self._create_pystray_icon()
    
    def _try_wayland_tray(self):
        """Try to create tray on Wayland (limited support)"""
        logger.warning("Wayland tray support is experimental")
        
        # Na Waylandzie próbuj tylko AppIndicator
        if self.desktop_env == 'gnome':
            return self._create_gnome_tray()
        else:
            logger.info("No Wayland tray support for this environment")
            return None
    
    def _setup_appindicator_menu(self, indicator, Gtk):
        """Setup menu for AppIndicator"""
        try:
            # Set icon
            icon_path = get_icon_path()
            if icon_path and os.path.exists(icon_path):
                indicator.set_icon(icon_path)
            
            indicator.set_status(indicator.IndicatorStatus.ACTIVE)
            indicator.set_label("GLaSSIST", "GLaSSIST")
            
            # Create menu
            menu = Gtk.Menu()
            
            # Activate item
            activate_item = Gtk.MenuItem(label="🎤 Activate Voice (Ctrl+Shift+H)")
            activate_item.connect("activate", self._on_activate_clicked)
            menu.append(activate_item)
            
            # Separator
            separator = Gtk.SeparatorMenuItem()
            menu.append(separator)
            
            # Wake word status
            wake_status_item = Gtk.MenuItem(label="🎯 Wake Word Status")
            wake_status_item.connect("activate", self._on_wake_status_clicked)
            menu.append(wake_status_item)
            
            # Test connection
            test_item = Gtk.MenuItem(label="🔄 Test Connection")
            test_item.connect("activate", self._on_test_clicked)
            menu.append(test_item)
            
            # Settings
            settings_item = Gtk.MenuItem(label="⚙️ Settings")
            settings_item.connect("activate", self._on_settings_clicked)
            menu.append(settings_item)
            
            # Separator
            separator2 = Gtk.SeparatorMenuItem()
            menu.append(separator2)
            
            # Quit
            quit_item = Gtk.MenuItem(label="❌ Quit GLaSSIST")
            quit_item.connect("activate", self._on_quit_clicked)
            menu.append(quit_item)
            
            menu.show_all()
            indicator.set_menu(menu)
            
            logger.info("✅ AppIndicator menu created successfully")
            return indicator
            
        except Exception as e:
            logger.error(f"Failed to setup AppIndicator menu: {e}")
            return None
    
    def _create_pystray_icon(self):
        """Create standard pystray icon"""
        try:
            import pystray
            from PIL import Image
            
            # Load icon
            icon_path = get_icon_path()
            if icon_path and os.path.exists(icon_path):
                try:
                    image = Image.open(icon_path)
                except Exception:
                    image = self._create_fallback_icon()
            else:
                image = self._create_fallback_icon()
            
            # Create menu
            menu = pystray.Menu(
                pystray.MenuItem('🎤 Activate Voice', self._on_activate_clicked),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem('🎯 Wake Word Status', self._on_wake_status_clicked),
                pystray.MenuItem('🔄 Test Connection', self._on_test_clicked),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem('⚙️ Settings', self._on_settings_clicked),
                pystray.MenuItem('❌ Quit', self._on_quit_clicked)
            )
            
            tray = pystray.Icon(
                "GLaSSIST",
                image,
                "GLaSSIST Desktop Voice Assistant",
                menu
            )
            
            logger.info("✅ Pystray icon created successfully")
            return tray
            
        except Exception as e:
            logger.error(f"Failed to create pystray icon: {e}")
            return None
    
    def _create_fallback_icon(self):
        """Create simple fallback icon"""
        from PIL import Image, ImageDraw
        
        image = Image.new('RGB', (64, 64), color='black')
        draw = ImageDraw.Draw(image)
        draw.ellipse([8, 8, 56, 56], fill='#4fc3f7', outline='white', width=2)
        draw.ellipse([24, 24, 40, 40], fill='white')
        return image
    
    # Event handlers
    def _on_activate_clicked(self, *args):
        self.app.trigger_voice_command()
    
    def _on_wake_status_clicked(self, *args):
        self.app._show_wake_word_status()
    
    def _on_test_clicked(self, *args):
        self.app._quick_connection_test()
    
    def _on_settings_clicked(self, *args):
        self.app.open_settings()
    
    def _on_quit_clicked(self, *args):
        self.app.quit_application()
    
    def start_tray(self):
        """Start the appropriate tray implementation"""
        if not self.tray:
            self.tray = self.create_tray_icon()
        
        if not self.tray:
            logger.warning("⚠️ System tray not available - using hotkey only")
            return False
        
        # Start tray in thread
        def tray_thread():
            try:
                if hasattr(self.tray, 'run'):
                    # pystray
                    self.tray.run()
                else:
                    # AppIndicator - już działa po utworzeniu
                    pass
            except Exception as e:
                logger.error(f"Tray thread error: {e}")
        
        if hasattr(self.tray, 'run'):
            threading.Thread(target=tray_thread, daemon=True).start()
        
        logger.info("✅ System tray started")
        return True
    
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
