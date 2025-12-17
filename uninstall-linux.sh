#!/bin/bash

# GLaSSIST Linux Uninstaller

set -euo pipefail

INSTALL_DIR="${HOME}/GLaSSIST"
DESKTOP_FILE="${HOME}/.local/share/applications/glassist.desktop"
SERVICE_FILE="${HOME}/.config/systemd/user/glassist.service"

prompt_confirm() {
    local prompt_text="$1"
    read -r -p "$prompt_text [y/N]: " response
    [[ "$response" =~ ^[Yy]$ ]]
}

echo "🐧 GLaSSIST Linux Uninstaller"
echo "=============================="

if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "This script is intended for Linux systems only."
    exit 1
fi

if [[ $EUID -eq 0 ]]; then
    echo "Do not run this script as root. Use your regular user account."
    exit 1
fi

if [[ -f "$SERVICE_FILE" ]]; then
    echo "Stopping user service..."
    systemctl --user stop glassist.service 2>/dev/null || true
    systemctl --user disable glassist.service 2>/dev/null || true
    rm -f "$SERVICE_FILE"
    systemctl --user daemon-reload 2>/dev/null || true
    echo "Removed systemd user service."
else
    echo "No systemd user service detected."
fi

if [[ -f "$DESKTOP_FILE" ]]; then
    echo "Removing desktop entry..."
    rm -f "$DESKTOP_FILE"
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    fi
    echo "Desktop entry removed."
else
    echo "No desktop entry found."
fi

if [[ -d "$INSTALL_DIR" ]]; then
    echo "Found installation directory at $INSTALL_DIR"
    if prompt_confirm "Do you want to delete the installation directory (including virtual env)?"; then
        rm -rf "$INSTALL_DIR"
        echo "Installation directory removed."
    else
        echo "Kept installation directory."
    fi
else
    echo "Installation directory not found at $INSTALL_DIR."
fi

echo "Cleanup complete. You can remove leftover Python packages manually if desired."
