# ![blur](https://capsule-render.vercel.app/api?type=blur&height=300&color=gradient&text=GLaSSIST&strokeWidth=2&section=footer&reversal=true&fontAlign=50&stroke=E0E0E0&fontSize=55&textBg=false)

GLaSSIST turns a Windows or Linux computer into a desktop voice satellite for
[Home Assistant](https://www.home-assistant.io/voice_control/) — because clicking through six
dashboards to turn off a lamp gets old surprisingly fast. It listens through your microphone, sends
requests to Home Assistant Assist, plays spoken responses, and shows the conversation state in an
optional animated desktop overlay.

More than 100 ready-to-use wake-word models are included, from Alexa and Jarvis to GLaDOS, because
your computer deserves a name before you start talking to it.

GLaSSIST works with any conversation agent available through a Home Assistant Assist pipeline. That
includes local models such as Ollama as well as cloud-based agents powered by Claude, GPT, and other
providers supported by Home Assistant.

For the full local feature set, use the recommended **ESPHome Satellite** mode. Home Assistant
discovers GLaSSIST on your network and can use it for voice commands, timers, and conversation
follow-up. The legacy **WebSocket** mode connects from GLaSSIST with a Home Assistant address and
long-lived token; it supports remote addresses but has fewer satellite features.

## 🚀 Key Features

- **Home Assistant Assist** — local microphone capture and speaker playback, without dedicated hardware
- **Any Assist conversation agent** — local Ollama, cloud-based Claude or GPT, and whatever HA supports next
- **ESPHome Satellite mode** — timers and conversation follow-up instead of one command and awkward silence
- **Flexible activation** — wake word, configurable hotkey, or system tray
- **WebRTC VAD** — detects when you stop speaking without reacting to every fridge beep
- **Three.js overlay** — animated audio feedback and optional response text, because a static circle was too easy
- **Practical controls** — selectable audio devices, feedback sounds, pipelines, and media-player volume management

<div align="center">
  <img src="https://github.com/user-attachments/assets/23c012ed-11c0-4f3b-9eef-b9fa16071e13" alt="Alt text" width="300">
</div>

## For users

You need a microphone and a Home Assistant installation with Assist configured. ESPHome Satellite
mode also requires Home Assistant 2024.6 or newer and both devices on the same local network.

### Windows installer

Windows 10 or 11, 64-bit:

1. Download [`GLaSSIST-Setup.exe`](https://github.com/SmolinskiP/GLaSSIST/releases/latest/download/GLaSSIST-Setup.exe).
2. Run the installer and choose a connection mode.
3. Launch GLaSSIST and finish configuring audio, wake words, and the Assist pipeline in Settings.

The installer includes the application and its Python dependencies.

### Linux — Flatpak

Download `GLaSSIST.flatpak` from the
[latest release](https://github.com/SmolinskiP/GLaSSIST/releases), then run:

```bash
flatpak install --user GLaSSIST.flatpak
flatpak run io.github.SmolinskiP.GLaSSIST
```

Flatpak data locations:

- Configuration: `~/.var/app/io.github.SmolinskiP.GLaSSIST/config/glasssist/.env`
- Custom sounds: `~/.var/app/io.github.SmolinskiP.GLaSSIST/data/glasssist/sound/`

The global hotkey works on X11. On Wayland, use wake-word or tray activation.

### Linux — install script

The installer supports Debian/Ubuntu, Fedora/RHEL, Arch Linux, and openSUSE. Run it as a regular
user; it will request `sudo` only when installing system packages.

```bash
wget https://raw.githubusercontent.com/SmolinskiP/GLaSSIST/main/install-linux.sh
chmod +x install-linux.sh
./install-linux.sh
```

To uninstall:

```bash
wget https://raw.githubusercontent.com/SmolinskiP/GLaSSIST/main/uninstall-linux.sh
chmod +x uninstall-linux.sh
./uninstall-linux.sh
```

The uninstaller can remove the user service, desktop entry, and application directory. System
packages installed by the setup script remain managed by your distribution.

### First-time setup

Open **Settings** from the tray icon or start the application with `--settings`.

For **ESPHome Satellite** mode:

1. Select ESPHome Satellite and choose a device name.
2. Keep GLaSSIST and Home Assistant on the same network.
3. In Home Assistant, open **Settings → Devices & services** and add the discovered ESPHome device.

For legacy **WebSocket** mode:

1. Enter your Home Assistant address without `http://` or `https://`.
2. Create a long-lived access token in your Home Assistant profile and enter it in Settings.
3. Test the connection and select an Assist pipeline if you do not want the default.

### Using GLaSSIST

Start a voice interaction in any configured way:

- say a selected wake word;
- press the configured global hotkey;
- choose voice activation from the system-tray menu.

The overlay indicates when GLaSSIST is listening, processing, responding, or reporting an error.
Wake-word detection can be paused from the tray. Audio devices, wake-word models, sounds, visual
effects, and media-player volume reduction are configured in Settings.

### Wake-word models

GLaSSIST bundles more than 100 models from the
[Home Assistant Wake Words Collection](https://github.com/fwartner/home-assistant-wakewords-collection),
including Alexa, Jarvis, GLaDOS, Computer, Scarlett, and plenty of names your family will question.

Want your own wake word? [openWakeWord](https://github.com/dscripka/openWakeWord) provides two Google
Colab notebooks. Follow the [custom wake-word guide](docs/CUSTOM_WAKE_WORDS.md) to train, convert,
install, and test your model.

### Interactive prompts

In WebSocket mode, Home Assistant or another local application can send a spoken prompt to
GLaSSIST's HTTP endpoint and optionally wait for a voice response. The endpoint has no
authentication and should only be exposed on a trusted local network. See
[Interactive Prompts Setup](INTERACTIVE_PROMPTS_SETUP.md) for the request format, Home Assistant
configuration, and examples.

## For developers

### Requirements and source installation

- Windows 10/11 or a supported Linux desktop
- Python 3.11–3.13
- Home Assistant with Assist configured
- A working microphone and output device

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/SmolinskiP/GLaSSIST.git
cd GLaSSIST
python -m venv .venv
```

Activate it on Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Or on Linux:

```bash
source .venv/bin/activate
```

Install dependencies and create a local configuration file:

```bash
python -m pip install -r requirements.txt
cp .env.example .env
```

On PowerShell, use `Copy-Item .env.example .env` instead of `cp`. You can edit `.env` directly or
configure the application through its Settings window.

Run GLaSSIST:

```bash
python main.py
```

Open Settings automatically on startup:

```bash
python main.py --settings
```

### Configuration

The complete set of supported settings and defaults is documented in [`.env.example`](.env.example).
The application stores user configuration outside the installation directory for packaged builds;
use the Settings UI unless you specifically need to edit the environment file.

### Tests

Install the test dependencies and use the bundled test runner:

```bash
python -m pip install -r tests/requirements-test.txt
python tests/run_tests.py
```

Useful variants:

```bash
python tests/run_tests.py --unit-only
python tests/run_tests.py --integration-only
python tests/run_tests.py --coverage
python -m pytest tests/test_client.py -v
```

See [`tests/README.md`](tests/README.md) for the complete test-runner reference.

### Project structure

- `main.py` — application lifecycle, tray integration, activation, and component orchestration
- `client.py` — Home Assistant WebSocket API and Assist pipeline communication
- `satellite_protocol.py` — ESPHome voice-satellite protocol, timers, and conversation follow-up
- `audio.py`, `vad.py`, `wake_word_detector.py` — capture, speech detection, and wake words
- `animation_server.py`, `frontend/` — overlay state, audio data, and Three.js visualization
- `flet_settings.py` — the settings interface and configuration persistence
- `conversation_manager.py`, `prompt_server.py` — local interactive prompts in WebSocket mode

## 📈 Star History

[![Star History Chart](https://api.star-history.com/chart?repos=SmolinskiP/GLaSSIST&type=date&legend=bottom-right&sealed_token=801EqtcIdZUXFju0IV2Hvq9ukc0aMGv7tZXc-67bkWC_1tJwnC2Jg6CUg4h0DJUFympWdiSWcFMux_2y1tYFIV83ov4EQzhLfzTwDt7DxNHnxlX8E31T27_jXUybAqr0vG32Nj_8njCWXFx1QFYS7fDAjnCFbBq2quTvnE7rw2nh9gLOb8r083NI8iU-)](https://www.star-history.com/?repos=SmolinskiP%2FGLaSSIST&type=date&legend=bottom-right)

## 📄 License

GLaSSIST is available under the [MIT License](LICENSE).

## ☕ Support

If GLaSSIST helped you and you want to support its development:
[☕ Buy me a coffee](https://buymeacoffee.com/smolinskip)

---

*Made with ❤️ and occasional frustration by [Patryk Smoliński](https://github.com/SmolinskiP)*
