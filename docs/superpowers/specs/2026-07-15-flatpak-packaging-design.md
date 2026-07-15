# Flatpak Packaging for GLaSSIST — Design

**Date:** 2026-07-15
**Status:** Approved by user (discussion in session; issue #43)
**Distribution decision:** `.flatpak` bundle in GitHub Releases first, Flathub submission as step 2.
**Hotkey decision:** X11 hotkey support only inside sandbox; on Wayland wake word is the
activation method. GlobalShortcuts portal support is out of scope (future issue).

## Problem

Linux installation currently relies on `install-linux.sh` (~900 lines of distro-specific
handling: Python 3.11 compilation on Debian, WebKit2GTK, mpv, speexdsp, PyGObject builds).
It is the single largest source of support issues. Issue #43 (RheaAyase) requests Flatpak
distribution.

## Why Flatpak (not AppImage)

pywebview on Linux needs WebKit2GTK, which is painful to bundle in an AppImage but is
provided by the GNOME Flatpak runtime. Flatpak also gives auto-updates and Flathub
discoverability. AppImage is explicitly out of scope.

## Key Risk — verify FIRST (spike)

pywebview's GTK backend requires GTK3 + WebKit2GTK 4.x. Newer GNOME runtimes move to
GTK4 / WebKitGTK 6.0. The spike must confirm one of:
1. Current GNOME runtime still ships webkit2gtk-4.1 (GTK3), or
2. pywebview Qt backend works acceptably in the sandbox, or
3. WebKitGTK must be built as a manifest module (cost: build time, maintenance).

The spike outcome determines the runtime/backend choice for the manifest. No further
work until this is answered.

## Deliverables

### 1. Flatpak manifest (`packaging/flatpak/io.github.SmolinskiP.GLaSSIST.yml`)
- App ID: `io.github.SmolinskiP.GLaSSIST`
- Runtime: GNOME (version per spike outcome)
- Python deps via `flatpak-pip-generator` from `requirements.txt`, excluding
  Windows-only packages (`pythonnet`, `clr_loader`, `pyreadline3`)
- Native modules: `libmpv` (Flet), `portaudio` (PyAudio), ayatana-appindicator (tray)
- Bundled assets: `sound/`, `models/`, `frontend/`, `img/`
- Permissions:
  - `--share=network` (HA WebSocket, mDNS, ESPHome satellite port 6053)
  - `--socket=pulseaudio` (mic capture + playback)
  - `--socket=wayland --socket=fallback-x11 --socket=x11` (UI + pynput hotkey on X11)
  - `--talk-name=org.kde.StatusNotifierWatcher` (tray)

### 2. Desktop integration files
- `.desktop` file, AppStream metainfo XML, icon (from `img/`)

### 3. Code adjustments (minimal, Linux-path only)
- Config (`.env`) and user sound files resolved via XDG dirs when running in Flatpak
  (`platform_utils.py` is the natural home; detect via `FLATPAK_ID` env var)
- Autostart via XDG Background/Autostart portal instead of current mechanism
- Hotkey: use pynput path in sandbox; document Wayland limitation

### 4. CI
- GitHub Actions workflow building the `.flatpak` bundle with `flatpak-builder`
  on release tags; artifact attached to the GitHub Release

### 5. Documentation
- README section: Flatpak install instructions + sandbox limitations (hotkey on Wayland,
  custom sounds location)

## Out of Scope
- AppImage
- GlobalShortcuts portal (Wayland hotkey) — file as separate issue
- Flathub submission itself (step 2, after the bundle proves itself)
- Any Windows-side changes

## Testing / Verification
- Build bundle locally (or in CI) and install on:
  - X11 VM (checks: hotkey, tray, mic, animation window, settings save, TTS playback)
  - Wayland VM (same minus hotkey)
- Satellite mode: HA discovers GLaSSIST via mDNS, port 6053 reachable
- Wake word detection works with bundled ONNX models
- `.env` persistence across app restarts (XDG config)
