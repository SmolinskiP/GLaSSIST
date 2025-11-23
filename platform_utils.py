"""
Cross-platform utility functions for GLaSSIST.
"""
import os
import sys
import platform
import subprocess
import logging
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
                    WS_EX_LAYERED = 0x00080000
                    WS_EX_TRANSPARENT = 0x00000020

                    current_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                    new_style = (current_style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_TRANSPARENT
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
        import locale
        system_encoding = locale.getpreferredencoding()
        
        if platform.system() == "Windows":
            # On Windows, use CREATE_NO_WINDOW to avoid console pop-ups
            subprocess.run(['explorer', str(path)], 
                          creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
                          encoding=system_encoding)
        elif platform.system() == "Darwin":  # macOS
            subprocess.run(['open', str(path)], encoding=system_encoding)
        else:  # Linux
            subprocess.run(['xdg-open', str(path)], encoding=system_encoding)
        return True
    except UnicodeEncodeError as e:
        logger.error(f"Unicode error opening path {path}: {e}")
        return False
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
        logger.info("Noise suppression not available (install: pip install speexdsp-ns)")
        return False