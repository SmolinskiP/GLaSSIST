## 🐧 GLaSSIST 3.5.0 — Linux Revolution

Linux goes from "technically supported" to a first-class citizen. GLaSSIST is now shipped as a **Flatpak** (#43) — one command, every dependency bundled, no more 900-line install script roulette — and the Linux desktop experience finally matches Windows: proper overlay, system tray, and rendering fixes across the board.

### 📦 Flatpak package
- **One-command install** on any distro — Ubuntu, Fedora, Arch, whatever:
  ```bash
  flatpak install --user GLaSSIST.flatpak
  flatpak run io.github.SmolinskiP.GLaSSIST
  ```
- `GLaSSIST.flatpak` is attached to this release and built automatically in CI for every future one.
- Everything bundled: WebKitGTK-ready GNOME 49 runtime, ffmpeg/libmpv, PortAudio, all Python dependencies (Python 3.13).
- Sandbox-aware paths: config lives in `~/.var/app/io.github.SmolinskiP.GLaSSIST/config/glasssist/.env`, custom sounds go to `~/.var/app/io.github.SmolinskiP.GLaSSIST/data/glasssist/sound/`.
- **Coming soon to Flathub!** 🚀 The manifest is ready and the store submission is underway — soon you'll install GLaSSIST straight from your software center and get automatic updates.

### 🖥️ Native Linux desktop experience
- **Animation overlay behaves like on Windows** — click-through (mouse events pass to windows below), skips the taskbar, stays on top, bottom-center placement. Pure GTK, works inside the sandbox, no `wmctrl`/`xdotool` required.
- **System tray is back on Linux** — via AppIndicator (StatusNotifier), including a sandbox-aware icon fix; previously the tray was disabled on Linux entirely.
- **WebKitGTK rendering fix** — the orb no longer freezes its last frame on screen after the session ends.
- **Wake word on Python 3.13** — automatic ONNX fallback when the TFLite runtime isn't available.

### ⚠️ Known limitations (Flatpak)
- Global hotkey works on X11 only — on Wayland use wake word activation.
- x86_64 builds only for now.

### 🪟 Windows
Nothing changes — all Linux work is platform-gated, the Windows build behaves exactly like 3.1.0.
