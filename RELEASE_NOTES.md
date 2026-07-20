## 🩹 GLaSSIST 3.5.2 — Flatpak wake word fix

A small patch release fixing wake word detection on the Flatpak build.

### 🐛 Fixes
- **Wake word detection now works out of the box on Flatpak** (#47). openWakeWord downloads its default models (`alexa`, `hey_mycroft`, `hey_jarvis`, `hey_rhasspy`, `timer`, `weather`) on first run — impossible inside the read-only Flatpak sandbox, so a fresh install with the default `alexa` configuration crashed on startup with `alexa_v0.1.onnx: File doesn't exist`. These models are now bundled in the package, so wake word detection works immediately after install.

### 🪟 Windows
Nothing changes — the fix is Flatpak-only, the Windows build behaves exactly like 3.5.x.
