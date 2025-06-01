#!/bin/bash

# GLaSSIST Linux Installer
# Comprehensive installation script for GLaSSIST Desktop

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# User context
CURRENT_USER=$(whoami)
USER_HOME=$(eval echo ~$CURRENT_USER)
INSTALL_DIR="$USER_HOME/GLaSSIST"

echo -e "${BLUE}🐧 GLaSSIST Linux Installer${NC}"
echo -e "${BLUE}===============================${NC}"
echo -e "Installing for user: ${GREEN}$CURRENT_USER${NC}"
echo -e "Install directory: ${GREEN}$INSTALL_DIR${NC}"
echo ""

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    echo -e "${RED}❌ Don't run this script as root!${NC}"
    echo -e "Run as regular user: ${YELLOW}./install-linux.sh${NC}"
    exit 1
fi

# Check if running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo -e "${RED}❌ This script is for Linux only${NC}"
    exit 1
fi

# Detect package manager and distribution
echo -e "${BLUE}📋 Detecting system...${NC}"
if command -v apt &> /dev/null; then
    PKG_MANAGER="apt"
    DISTRO="debian"
    echo -e "Detected: ${GREEN}Debian/Ubuntu${NC}"
elif command -v dnf &> /dev/null; then
    PKG_MANAGER="dnf"
    DISTRO="fedora"
    echo -e "Detected: ${GREEN}Fedora/RHEL${NC}"
elif command -v pacman &> /dev/null; then
    PKG_MANAGER="pacman"
    DISTRO="arch"
    echo -e "Detected: ${GREEN}Arch Linux${NC}"
elif command -v zypper &> /dev/null; then
    PKG_MANAGER="zypper"
    DISTRO="opensuse"
    echo -e "Detected: ${GREEN}openSUSE${NC}"
else
    echo -e "${RED}❌ Unsupported package manager${NC}"
    echo "Supported distributions: Ubuntu/Debian, Fedora/RHEL, Arch Linux, openSUSE"
    exit 1
fi

# Check for sudo privileges
echo -e "${BLUE}🔑 Checking sudo privileges...${NC}"
if ! sudo -n true 2>/dev/null; then
    echo -e "${YELLOW}⚠️  This script requires sudo privileges for system packages${NC}"
    echo "You may be prompted for your password..."
fi

# Install Git if not present
echo -e "${BLUE}📥 Checking Git installation...${NC}"
if ! command -v git &> /dev/null; then
    echo -e "${YELLOW}Installing Git...${NC}"
    case $PKG_MANAGER in
        "apt") sudo apt update && sudo apt install -y git ;;
        "dnf") sudo dnf install -y git ;;
        "pacman") sudo pacman -S --noconfirm git ;;
        "zypper") sudo zypper install -y git ;;
    esac
else
    echo -e "${GREEN}✅ Git already installed${NC}"
fi

# Install Python if not present
echo -e "${BLUE}🐍 Checking Python installation...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}Installing Python 3...${NC}"
    case $PKG_MANAGER in
        "apt") sudo apt install -y python3 python3-dev python3-pip python3-venv ;;
        "dnf") sudo dnf install -y python3 python3-devel python3-pip ;;
        "pacman") sudo pacman -S --noconfirm python python-pip ;;
        "zypper") sudo zypper install -y python3 python3-devel python3-pip ;;
    esac
else
    echo -e "${GREEN}✅ Python 3 already installed: $(python3 --version)${NC}"
fi

# Clone or update GLaSSIST repository
echo -e "${BLUE}📂 Setting up GLaSSIST repository...${NC}"
if [[ -d "$INSTALL_DIR" ]]; then
    echo -e "${YELLOW}Directory $INSTALL_DIR already exists${NC}"
    read -p "Do you want to update existing installation? (y/N): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cd "$INSTALL_DIR"
        git pull origin main
        echo -e "${GREEN}✅ Repository updated${NC}"
    else
        echo -e "${YELLOW}⚠️  Using existing installation${NC}"
        cd "$INSTALL_DIR"
    fi
else
    echo -e "${YELLOW}Cloning GLaSSIST repository...${NC}"
    cd "$USER_HOME"
    git clone https://github.com/SmolinskiP/GLaSSIST.git
    cd "$INSTALL_DIR"
    echo -e "${GREEN}✅ Repository cloned${NC}"
fi

# Install system dependencies
echo -e "${BLUE}📦 Installing system dependencies...${NC}"
# Install system dependencies
echo -e "${BLUE}📦 Installing system dependencies...${NC}"
case $PKG_MANAGER in
    "apt")
        sudo apt update
        
        # Install base dependencies
        sudo apt install -y \
            python3-dev python3-pip python3-venv python3-wheel \
            build-essential pkg-config cmake \
            git curl
        
        # Install audio dependencies
        sudo apt install -y \
            libasound2-dev portaudio19-dev \
            libpulse-dev libspeex-dev
        
        # Install GTK/WebKit dependencies
        sudo apt install -y \
            libgirepository1.0-dev gobject-introspection \
            libglib2.0-dev libglib2.0-dev-bin \
            libcairo2-dev libxt-dev libffi-dev \
            python3-gi python3-gi-cairo \
            gir1.2-gtk-3.0 gir1.2-webkit2-4.0 \
            gir1.2-glib-2.0
        
        # Try to install AppIndicator (different names on different Ubuntu versions)
        echo -e "${YELLOW}Installing system tray support...${NC}"
        sudo apt install -y gir1.2-ayatanaappindicator3-0.1 2>/dev/null || \
        sudo apt install -y gir1.2-ayatanaappindicator-0.1 2>/dev/null || \
        sudo apt install -y gir1.2-appindicator3-0.1 2>/dev/null || \
        sudo apt install -y libayatana-appindicator3-1 2>/dev/null || \
        sudo apt install -y libappindicator3-1 2>/dev/null || \
        echo -e "${YELLOW}⚠️  System tray packages not found (app will work without tray icon)${NC}"
        
        # Install window management tools
        sudo apt install -y wmctrl xdotool
        ;;
    "dnf")
        sudo dnf install -y \
            python3-devel python3-pip \
            alsa-lib-devel portaudio-devel \
            python3-gobject python3-gobject-devel \
            gtk3-devel webkit2gtk3-devel \
            gobject-introspection-devel \
            wmctrl xdotool \
            pulseaudio-libs-devel speex-devel \
            gcc gcc-c++ pkgconfig
        ;;
    "pacman")
        sudo pacman -S --noconfirm \
            python python-pip \
            alsa-lib portaudio \
            python-gobject gtk3 webkit2gtk \
            gobject-introspection \
            wmctrl xdotool \
            pulseaudio speex \
            base-devel pkgconf
        ;;
    "zypper")
        sudo zypper install -y \
            python3-devel python3-pip \
            alsa-devel portaudio-devel \
            python3-gobject typelib-1_0-Gtk-3_0 \
            gtk3-devel webkit2gtk3-devel \
            gobject-introspection-devel \
            wmctrl xdotool \
            pulseaudio-devel speex-devel \
            gcc gcc-c++ pkg-config
        ;;
esac

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to install system dependencies${NC}"
    exit 1
fi

echo -e "${GREEN}✅ System dependencies installed${NC}"

# Create virtual environment
echo -e "${BLUE}🐍 Setting up Python virtual environment...${NC}"
if [ -d "venv" ]; then
    echo -e "${YELLOW}Virtual environment already exists${NC}"
    read -p "Do you want to recreate it? (y/N): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf venv
        python3 -m venv venv
        echo -e "${GREEN}✅ Virtual environment recreated${NC}"
    fi
else
    python3 -m venv venv
    echo -e "${GREEN}✅ Virtual environment created${NC}"
fi

# Activate virtual environment
echo -e "${BLUE}🔄 Activating virtual environment...${NC}"
source venv/bin/activate

# Upgrade pip
echo -e "${BLUE}⬆️  Upgrading pip...${NC}"
pip install --upgrade pip setuptools wheel

# Install Python dependencies
echo -e "${BLUE}📚 Installing Python dependencies...${NC}"
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo -e "${YELLOW}⚠️  requirements.txt not found, installing basic dependencies...${NC}"
    pip install pyaudio webrtcvad pywebview pystray keyboard python-dotenv requests sounddevice soundfile numpy Pillow tkinter
fi

# Install Linux-specific packages
echo -e "${BLUE}🐧 Installing Linux-specific packages...${NC}"

# For Ubuntu/Debian, skip pip compilation hell and use only system packages
if command -v apt &> /dev/null; then
    echo -e "${YELLOW}Using system packages only (no compilation)...${NC}"
    
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    SITE_PACKAGES="$PWD/venv/lib/python$PYTHON_VERSION/site-packages"
    
    # Create .pth file to include system packages
    cat > "$SITE_PACKAGES/system-packages.pth" << EOF
/usr/lib/python3/dist-packages
/usr/lib/python$PYTHON_VERSION/dist-packages
/usr/local/lib/python$PYTHON_VERSION/dist-packages
EOF
    
    echo -e "${GREEN}✅ System packages configured for virtual environment${NC}"
    
    # Test system packages
    echo -e "${YELLOW}Testing GTK/Cairo availability...${NC}"
    if python3 -c "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk, GLib; print('✅ GTK works')" 2>/dev/null; then
        echo -e "${GREEN}✅ GTK system packages working${NC}"
    else
        echo -e "${RED}❌ GTK system packages test failed${NC}"
        echo -e "${YELLOW}Attempting emergency pip install...${NC}"
        
        # Last resort: try pip with --no-build-isolation
        pip install --no-build-isolation --no-cache-dir pycairo || echo -e "${YELLOW}pycairo pip failed${NC}"
        pip install --no-build-isolation --no-cache-dir PyGObject || echo -e "${YELLOW}PyGObject pip failed${NC}"
    fi
    
else
    # Non-Debian systems
    echo -e "${YELLOW}Installing via pip (may require compilation)...${NC}"
    pip install --no-cache-dir PyGObject pycairo || {
        echo -e "${RED}❌ PyGObject/pycairo installation failed${NC}"
        exit 1
    }
fi

# Install optional packages
echo -e "${BLUE}🎤 Installing optional enhancements...${NC}"

# Try to install speexdsp with different names
echo -e "${YELLOW}Attempting to install noise suppression support...${NC}"
if pip install speexdsp 2>/dev/null; then
    echo -e "${GREEN}✅ speexdsp installed${NC}"
elif pip install speexdsp-python 2>/dev/null; then
    echo -e "${GREEN}✅ speexdsp-python installed${NC}"
else
    echo -e "${YELLOW}⚠️  Noise suppression not available (speexdsp packages not found)${NC}"
    echo -e "${YELLOW}    This is optional - wake word detection will work without it${NC}"
fi

# Install additional audio processing libraries
pip install librosa 2>/dev/null || echo -e "${YELLOW}⚠️  librosa not installed (optional)${NC}"

# Set up configuration
echo -e "${BLUE}⚙️  Setting up configuration...${NC}"

# Check if .env already exists
if [ -f ".env" ]; then
    echo -e "${GREEN}✅ Configuration file (.env) already exists${NC}"
    read -p "Do you want to reconfigure Home Assistant connection? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Keeping existing configuration${NC}"
        SKIP_CONFIG=true
    fi
fi

if [ "$SKIP_CONFIG" != "true" ]; then
    echo ""
    echo -e "${BLUE}🏠 Home Assistant Configuration${NC}"
    echo -e "${BLUE}===============================${NC}"
    echo ""
    
    # Get HA Host
    echo -e "${YELLOW}Enter your Home Assistant server address${NC}"
    echo -e "Examples:"
    echo -e "  • homeassistant.local:8123"
    echo -e "  • 192.168.1.100:8123"
    echo -e "  • my-ha.duckdns.org:8123"
    echo ""
    read -p "Home Assistant Host: " HA_HOST
    
    # Validate host format
    while [[ -z "$HA_HOST" ]]; do
        echo -e "${RED}❌ Host cannot be empty!${NC}"
        read -p "Home Assistant Host: " HA_HOST
    done
    
    echo ""
    
    # Get HA Token
    echo -e "${YELLOW}Enter your Home Assistant Long-Lived Access Token${NC}"
    echo -e "To create one:"
    echo -e "  1. Go to ${BLUE}http://$HA_HOST/profile${NC}"
    echo -e "  2. Scroll down to 'Long-Lived Access Tokens'"
    echo -e "  3. Click 'Create Token'"
    echo -e "  4. Give it a name (e.g., 'GLaSSIST')"
    echo -e "  5. Copy the generated token"
    echo ""
    read -s -p "Access Token: " HA_TOKEN
    echo ""
    
    # Validate token
    while [[ -z "$HA_TOKEN" ]]; do
        echo -e "${RED}❌ Token cannot be empty!${NC}"
        read -s -p "Access Token: " HA_TOKEN
        echo ""
    done
    
    # Create .env file with defaults
    echo -e "${BLUE}💾 Creating configuration file with defaults...${NC}"
    
    cat > .env << EOF
# Home Assistant Assist Settings
# Generated by GLaSSIST Linux installer

# === CONNECTION ===
HA_HOST=$HA_HOST
HA_TOKEN=$HA_TOKEN
# HA_PIPELINE_ID=

# === ACTIVATION ===
HA_HOTKEY=ctrl+shift+h

# === AUDIO ===
HA_SAMPLE_RATE=16000
HA_CHANNELS=1
HA_FRAME_DURATION_MS=30
HA_PADDING_MS=300

# === VOICE DETECTION (VAD) ===
HA_VAD_MODE=3
HA_SILENCE_THRESHOLD_SEC=0.8

# === WAKE WORD DETECTION ===
HA_WAKE_WORD_ENABLED=true
HA_WAKE_WORD_MODELS=alexa
HA_WAKE_WORD_THRESHOLD=0.5
HA_WAKE_WORD_VAD_THRESHOLD=0.3
HA_WAKE_WORD_NOISE_SUPPRESSION=true

# === NETWORK ===
ANIMATION_PORT=8765

# === AUDIO FEEDBACK ===
HA_SOUND_FEEDBACK=true

# === DEBUG ===
DEBUG=false
EOF
    
    echo -e "${GREEN}✅ Configuration file created with defaults:${NC}"
    echo -e "  • Hotkey: ${YELLOW}ctrl+shift+h${NC}"
    echo -e "  • Wake word: ${YELLOW}enabled (alexa)${NC}"
    echo -e "  • Pipeline: ${YELLOW}default${NC}"
    echo -e "  • Use Settings in app to customize later${NC}"
    
    # Test connection
    echo ""
    echo -e "${BLUE}🔍 Testing Home Assistant connection...${NC}"
    
    # Quick connection test
    if command -v curl &> /dev/null; then
        echo -e "${YELLOW}Testing connection to $HA_HOST...${NC}"
        
        # Determine protocol
        if [[ "$HA_HOST" == *"localhost"* ]] || [[ "$HA_HOST" == *"127.0.0.1"* ]] || [[ "$HA_HOST" == *"192.168."* ]] || [[ "$HA_HOST" == *"10."* ]] || [[ "$HA_HOST" == *"172."* ]]; then
            PROTOCOL="http"
        else
            PROTOCOL="https"
        fi
        
        # Test basic connectivity
        if curl -s --connect-timeout 10 -H "Authorization: Bearer $HA_TOKEN" "$PROTOCOL://$HA_HOST/api/" > /dev/null 2>&1; then
            echo -e "${GREEN}✅ Connection successful!${NC}"
        else
            echo -e "${YELLOW}⚠️  Connection test failed - please verify your settings${NC}"
            echo -e "You can test manually at: ${BLUE}$PROTOCOL://$HA_HOST${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  curl not available for connection testing${NC}"
    fi
    
else
    echo -e "${YELLOW}⚠️  Skipping configuration - using existing .env file${NC}"
fi

# Create icon for Linux if needed
echo -e "${BLUE}🖼️  Setting up application icon...${NC}"
if [ ! -f "img/icon.png" ] && [ -f "img/icon.ico" ]; then
    echo -e "${YELLOW}Converting ICO to PNG for Linux...${NC}"
    # Try to convert using ImageMagick or Python
    if command -v convert &> /dev/null; then
        convert img/icon.ico img/icon.png 2>/dev/null || echo -e "${YELLOW}⚠️  Icon conversion failed${NC}"
    else
        python3 -c "
from PIL import Image
try:
    img = Image.open('img/icon.ico')
    img.save('img/icon.png', 'PNG')
    print('✅ Icon converted successfully')
except Exception as e:
    print(f'⚠️  Icon conversion failed: {e}')
" 2>/dev/null
    fi
fi

# Create desktop entry
echo -e "${BLUE}🖥️  Creating desktop entry...${NC}"
mkdir -p "$USER_HOME/.local/share/applications"
cat > "$USER_HOME/.local/share/applications/glassist.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=GLaSSIST
Comment=Voice Assistant for Home Assistant
Exec=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/main.py
Icon=$INSTALL_DIR/img/icon.png
Path=$INSTALL_DIR
Terminal=false
Categories=Utility;Audio;AudioVideo;
StartupNotify=true
EOF

chmod +x "$USER_HOME/.local/share/applications/glassist.desktop"
echo -e "${GREEN}✅ Desktop entry created${NC}"

# Create launch script
echo -e "${BLUE}📜 Creating launch script...${NC}"
cat > "$INSTALL_DIR/glassist.sh" << EOF
#!/bin/bash
cd "$INSTALL_DIR"
source venv/bin/activate
python main.py
EOF

chmod +x "$INSTALL_DIR/glassist.sh"
echo -e "${GREEN}✅ Launch script created${NC}"

# Download wake word models
echo ""
echo -e "${BLUE}🎤 Downloading wake word models...${NC}"
if python3 -c "import openwakeword" 2>/dev/null; then
    echo -e "${YELLOW}Downloading default openWakeWord models (this may take a few minutes)...${NC}"
    
    python3 -c "
import openwakeword
try:
    print('📥 Downloading models...')
    openwakeword.utils.download_models()
    print('✅ Wake word models downloaded successfully!')
    
    # List available models
    import os
    models_dir = os.path.join(os.path.dirname(openwakeword.__file__), 'resources')
    if os.path.exists(models_dir):
        models = [f for f in os.listdir(models_dir) if f.endswith('.onnx')]
        if models:
            print(f'📋 Available models: {len(models)}')
            for model in models[:10]:  # Show first 10
                print(f'   • {model.replace(\".onnx\", \"\")}')
            if len(models) > 10:
                print(f'   ... and {len(models) - 10} more')
        else:
            print('⚠️  No models found in resources directory')
    else:
        print('⚠️  Models directory not found')
        
except Exception as e:
    print(f'❌ Failed to download models: {e}')
    print('💡 You can download them later from the app settings')
" || echo -e "${YELLOW}⚠️  Model download failed (you can try later from app settings)${NC}"
    
else
    echo -e "${YELLOW}⚠️  openWakeWord not installed - skipping model download${NC}"
fi

# Fix NumPy compatibility for openWakeWord
echo ""
echo -e "${BLUE}🔧 Fixing NumPy compatibility...${NC}"
echo -e "${YELLOW}Downgrading NumPy for openWakeWord compatibility...${NC}"
pip install "numpy<2.0" --force-reinstall || echo -e "${YELLOW}⚠️  NumPy downgrade failed (may cause wake word issues)${NC}"

# Install TensorFlow Lite runtime for Linux
echo -e "${YELLOW}Installing TensorFlow Lite runtime for wake word models...${NC}"
pip install tflite-runtime || echo -e "${YELLOW}⚠️  TFLite runtime installation failed (ONNX models will be used)${NC}"

# === WINDOW MANAGEMENT TOOLS ===
echo -e "${BLUE}🪟 Installing window management tools...${NC}"
case $PKG_MANAGER in
    "apt") 
        sudo apt install -y wmctrl xdotool xprop xwininfo xdpyinfo x11-utils

        echo -e "${YELLOW}Installing system tray support...${NC}"
        sudo apt install -y gir1.2-ayatanaappindicator3-0.1 2>/dev/null || \
        sudo apt install -y gir1.2-appindicator3-0.1 2>/dev/null || \
        echo -e "${YELLOW}⚠️  System tray packages not found${NC}"
        ;;
    "dnf") 
        sudo dnf install -y wmctrl xdotool xprop xwininfo xdpyinfo
        sudo dnf install -y libappindicator-gtk3 2>/dev/null || true
        ;;
    "pacman") 
        sudo pacman -S --noconfirm wmctrl xdotool xorg-xprop xorg-xwininfo xorg-xdpyinfo
        sudo pacman -S --noconfirm libappindicator-gtk3 2>/dev/null || true
        ;;
    "zypper") 
        sudo zypper install -y wmctrl xdotool xprop xwininfo xdpyinfo
        sudo zypper install -y libappindicator3-1 2>/dev/null || true
        ;;
esac

echo -e "${GREEN}✅ Window management tools installed${NC}"

echo -e "${BLUE}🖥️  Testing desktop environment...${NC}"
echo -e "Desktop: ${YELLOW}${XDG_CURRENT_DESKTOP:-Unknown}${NC}"
echo -e "Session: ${YELLOW}${XDG_SESSION_TYPE:-Unknown}${NC}"

if [ "$XDG_SESSION_TYPE" = "wayland" ]; then
    echo -e "${YELLOW}⚠️  Wayland detected - some features may be limited${NC}"
    echo -e "${BLUE}💡 Consider using X11 session for full functionality${NC}"
fi

# Optional: System service setup
echo ""
echo -e "${BLUE}🔧 System Integration Options${NC}"
echo -e "${BLUE}============================${NC}"

read -p "Do you want to set up GLaSSIST as a systemd user service (auto-start)? (y/N): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}🚀 Setting up systemd user service...${NC}"
    
    mkdir -p "$USER_HOME/.config/systemd/user"
    cat > "$USER_HOME/.config/systemd/user/glassist.service" << EOF
[Unit]
Description=GLaSSIST Desktop Voice Assistant
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/main.py
Restart=always
RestartSec=5
Environment=DISPLAY=:0
Environment=XDG_RUNTIME_DIR=/run/user/%i

[Install]
WantedBy=default.target
EOF

    # Enable and start service
    systemctl --user daemon-reload
    systemctl --user enable glassist.service
    
    echo -e "${GREEN}✅ Systemd service created and enabled${NC}"
    echo -e "Service commands:"
    echo -e "  Start:   ${YELLOW}systemctl --user start glassist${NC}"
    echo -e "  Stop:    ${YELLOW}systemctl --user stop glassist${NC}"
    echo -e "  Status:  ${YELLOW}systemctl --user status glassist${NC}"
    echo -e "  Logs:    ${YELLOW}journalctl --user -u glassist -f${NC}"
    
    read -p "Do you want to start the service now? (y/N): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        systemctl --user start glassist.service
        echo -e "${GREEN}✅ GLaSSIST service started${NC}"
    fi
fi

# Test installation
echo ""
echo -e "${BLUE}🧪 Testing installation...${NC}"
source venv/bin/activate
python3 -c "
import sys
try:
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('WebKit2', '4.0')
    print('✅ GTK/WebKit2 - OK')
except Exception as e:
    print(f'❌ GTK/WebKit2 - FAILED: {e}')

try:
    import pyaudio
    print('✅ PyAudio - OK')
except Exception as e:
    print(f'❌ PyAudio - FAILED: {e}')

try:
    import webview
    print('✅ PyWebView - OK')
except Exception as e:
    print(f'❌ PyWebView - FAILED: {e}')

try:
    import pystray
    print('✅ Pystray - OK')
except Exception as e:
    print(f'❌ Pystray - FAILED: {e}')
"

# Installation complete
echo ""
echo -e "${GREEN}🎉 Installation Complete!${NC}"
echo -e "${GREEN}=========================${NC}"
echo ""
echo -e "${BLUE}📁 Installation directory:${NC} $INSTALL_DIR"
echo -e "${BLUE}📝 Configuration file:${NC} $INSTALL_DIR/.env"
echo ""
echo -e "${YELLOW}📋 Next steps:${NC}"
echo -e "1. Edit configuration: ${YELLOW}nano $INSTALL_DIR/.env${NC}"
echo -e "2. Add your Home Assistant details (HA_HOST, HA_TOKEN)"
echo -e "3. Run GLaSSIST:"
echo -e "   • Desktop: Search for 'GLaSSIST' in applications"
echo -e "   • Terminal: ${YELLOW}cd $INSTALL_DIR && ./glassist.sh${NC}"
echo -e "   • Direct: ${YELLOW}$INSTALL_DIR/venv/bin/python $INSTALL_DIR/main.py${NC}"
echo ""
echo -e "${BLUE}🔧 Useful commands:${NC}"
echo -e "Update: ${YELLOW}cd $INSTALL_DIR && git pull${NC}"
echo -e "Logs: ${YELLOW}journalctl --user -u glassist -f${NC} (if using systemd)"
echo ""
echo -e "${GREEN}Enjoy your voice assistant! 🎤${NC}"