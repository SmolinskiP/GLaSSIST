# 🎤 GLaSSIST

<div align="center">
  <img src="https://github.com/user-attachments/assets/23c012ed-11c0-4f3b-9eef-b9fa16071e13" alt="Alt text" width="300">
</div>

Desktop voice application for Home Assistant with visual animations and VAD (Voice Activity Detection). Because who has time to click through interfaces when you can just talk to your computer like it's a broken microphone?

## 🚀 Key Features

- **Voice activation** - Hotkey or click to activate
- **Wake word detection** - Over 100 pre-trained models (alexa, jarvis, glados etc.)
- **WebRTC VAD** - Smart speech detection (doesn't react to every fridge beep)
- **Visual animations** - Three.js with shaders and FFT audio analysis (because a simple circle is not enough)
- **Response text display** - Visually show assistant responses on screen
- **Modern Flet UI** - Beautiful, responsive settings interface (no more Tkinter!)
- **Tray integration** - Lives in system tray like a proper application
- **Pause wake word** - Quickly pause or resume detection from tray
- **Pipeline selection** - Choose your preferred assistant pipeline
- **Microphone selection** - Pick specific microphone or use automatic detection
- **Transparent window** - Doesn't block your desktop (finally, someone thought about it)
- **Animation toggle** - Disable visual effects to save CPU/memory resources
- **Cross-platform** - Windows and Linux support with native feel
- **Thread-safe** - No more hanging settings dialogs or crashes
- **Debug logging** - File logging when debug mode is enabled
- **Interactive Prompts API** - Home Assistant can ask questions and get voice responses
- **HTTP API Server** - External applications can trigger voice prompts via REST API
- **Media Player Volume Management** - Automatic volume control during voice interactions

## 📋 Requirements

### For .exe Installation (Recommended)
- **Home Assistant** with Assist enabled
- **Windows 10/11** (64-bit)
- **Microphone** (obviously)
- **Long-lived access token** for HA

### For Python Installation (Advanced users)
- **Home Assistant** with Assist enabled
- **Python 3.11** (recommended) or **Python 3.12** (Linux: ONNX only)
  - Python 3.8-3.10 also supported with some limitations
  - Python 3.13+ not supported due to dependency incompatibilities
- **Windows 10/11** or **Linux** (Ubuntu, Debian, Fedora, Arch)
- **Microphone**
- **Long-lived access token** for HA
- **Flet 0.21+** (for modern settings UI)

## 🛠️ Installation

### Option 1: Windows Installer (Easy)
1. **Download** [GLaSSIST-Setup.exe](https://github.com/SmolinskiP/GLaSSIST/releases/latest/download/GLaSSIST-Setup.exe) from releases
2. **Run installer** and follow setup wizard
3. **Enter your HA details** during installation
4. **Launch** and start talking to your smart home

No Python knowledge required. Everything is bundled and configured automatically.

### Option 2: Linux (Beta)
```bash
wget https://raw.githubusercontent.com/SmolinskiP/GLaSSIST/main/install-linux.sh && chmod +x install-linux.sh && ./install-linux.sh
```

## 🧹 Uninstall (Linux)
1. Download the uninstall script:
   ```bash
   wget https://raw.githubusercontent.com/SmolinskiP/GLaSSIST/main/uninstall-linux.sh
   chmod +x uninstall-linux.sh
   ```
2. Run it as a regular user in the terminal:
   ```bash
   ./uninstall-linux.sh
   ```
3. The script stops the systemd user service (if enabled), removes the desktop entry, and
   asks whether to delete the `~/GLaSSIST` directory. System packages installed by the
   installer remain; remove them with your package manager if you don't need them.

### Option 3: From Source (For developers)

### 1. Clone repository
```bash
git clone https://github.com/SmolinskiP/GLaSSIST.git
cd GLaSSIST
```

### 2. Install dependencies
```bash
pip install -r requirements.txt

# For modern settings UI (Flet-based)
pip install flet>=0.21.0
```

### 3. Configuration
Create `.env` file:
```env
# === CONNECTION ===
HA_HOST=your-homeassistant.local:8123
HA_TOKEN=your_long_lived_access_token_here

# === WAKE WORD ===
HA_WAKE_WORD_ENABLED=true
HA_WAKE_WORD_MODELS=alexa,hey_jarvis
HA_WAKE_WORD_THRESHOLD=0.5

# === ACTIVATION ===
HA_HOTKEY=ctrl+shift+h

# === AUDIO ===
HA_VAD_MODE=3
HA_SILENCE_THRESHOLD_SEC=0.8
HA_SOUND_FEEDBACK=true

# === VISUAL ===
HA_RESPONSE_TEXT_ENABLED=true

# === OPTIONAL ===
HA_PIPELINE_ID=your_pipeline_id
DEBUG=false
```

**Pro tip:** Use the modern "Settings" interface in the app instead of manually creating the file. Features beautiful Flet-based UI with real-time validation and auto-complete. This isn't 1995, we have proper GUIs now.

### 4. Run
```bash
# Run application normally
python main.py

# Or open settings directly
python main.py --settings
```

**Command line options:**
- `--settings` - Opens settings window without starting the full application (useful for quick configuration)
- `--help` - Shows all available command line options

**Pro tip:** Use the installer unless you want to modify the code. It's way fucking easier.

## ⚙️ Home Assistant Configuration

### Access Token
1. Go to `Profile` → `Long-Lived Access Tokens`
2. Click `Create Token`
3. Copy token to `.env`

Without this, the app will be as useful as a calculator without batteries.

### Pipelines (optional)
The app automatically fetches available pipelines. If you have more than one, select it in settings.

## 🔄 Interactive Prompts Integration

GLaSSIST v2.0 introduces **Interactive Prompts** - allowing Home Assistant to ask questions and receive voice responses. Perfect for confirmations, choices, and interactive automations.

### HTTP API Server

GLaSSIST runs an HTTP server (default port `8766`) that accepts prompt requests:

**Endpoint**: `POST http://YOUR_GLASSIST_IP:8766/prompt`

**Request format**:
```json
{
  "message": "Question to ask the user",
  "context": "Context for the assistant to understand the situation",
  "timeout": 15,
  "wait_for_response": true
}
```

**Response**: `{"status": "accepted", "message": "Prompt will be processed"}`

### Home Assistant Integration

Add this to your `configuration.yaml`:

```yaml
rest_command:
  glassist_prompt:
    url: "http://YOUR_GLASSIST_IP:8766/prompt"
    method: POST
    headers:
      Content-Type: "application/json"
    payload: |
      {
        "message": "{{ message }}",
        "context": "{{ context }}",
        "timeout": {{ timeout | default(15) }},
        "wait_for_response": {{ wait_for_response | default(true) | lower }},
        "use_ai_message": {{ use_ai_message | default(false) | lower }}
      }

automation:
  - alias: "Ask before turning on lights"
    trigger:
      - platform: state
        entity_id: light.living_room_light
        to: "on"
    action:
      - service: rest_command.glassist_prompt
        data:
          message: "Turn on the living room lights?"
          context: "User wants to control living room lighting"
          timeout: 15,
          wait_for_response: false
```

### Manual Testing

Test the API directly with curl:

```bash
curl -X POST http://192.168.1.100:8766/prompt \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Turn on the lights in the living room?",
    "context": "You ask user if they want to turn on lights in living room",
    "timeout": 15,
    "wait_for_response": true
  }'
```

Or via Home Assistant Developer Tools:
- **Service**: `rest_command.glassist_prompt`
- **Service Data**:
```yaml
message: "Turn on the lights in the living room?"
context: "You ask user if they want to turn on lights in living room" 
timeout: 15
wait_for_response: true
```

### How It Works

1. **HA sends prompt** → GLaSSIST receives HTTP request
2. **GLaSSIST asks user** → Plays TTS question
3. **User responds via voice**
4. **GLaSSIST processes response** → Uses context to understand what user is responding to
5. **Action executed** → Based on user's voice response (yes/no/specific action)

### Use Cases

- **Confirmation dialogs**: "Turn on bedroom lights?" → User: "Yes"
- **Security prompts**: "Someone at the door. Turn on porch light?" → User: "Yes please"  
- **Energy management**: "High electricity usage detected. Turn off unnecessary devices?" → User: "Turn off the TV"
- **Schedule conflicts**: "Meeting in 10 minutes. Should I dim the lights?" → User: "Yes, set to 30%"


### 📖 Complete Setup Guide

For detailed configuration with advanced examples, automations, and use cases, see:  
**[📋 INTERACTIVE_PROMPTS_SETUP.md](INTERACTIVE_PROMPTS_SETUP.md)**

### Security Notes

- **Local network only** - The API server binds to all interfaces for LAN access
- **No authentication** - Intended for trusted local network use only  
- **Firewall considerations** - Port 8766 needs to be accessible from HA server

## 🤖 Wake Word Models
GLaSSIST includes over **100 pre-trained wake word models** converted to ONNX format for Windows compatibility. Models are sourced from the [Home Assistant Wakewords Collection](https://github.com/fwartner/home-assistant-wakewords-collection/tree/main) and optimized for desktop use.

Available wake words include:
- **Standard**: `Alexa`, `Hey Jarvis`, `Hey Mycroft`
- **Creative**: `Computer`, `Scarlett`, `Glados`, `Mr. Anderson`, `Scooby`

### Custom Wake Word Training

Want to create your own wake words? Thanks to the brilliant work by [dscripka/openWakeWord](https://github.com/dscripka/openWakeWord), you can train custom models using Google Colab.

#### Training Options

**Basic Training (Recommended for beginners):**
[🔗 Google Colab - Basic Training](https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb?usp=sharing)

**Advanced Training (For experienced users):**
[🔗 Google Colab - Advanced Training](https://colab.research.google.com/drive/1yyFH-fpguX2BTAW8wSQxTrJnJTM-0QAd?usp=sharing)

#### Model Conversion for Windows

After training your model in Colab (which outputs `.tflite` format), you need to convert it to ONNX for Windows compatibility:

```bash
# Install conversion tools
pip install tf2onnx tensorflow

# Convert TFLite to ONNX (one command)
python -m tf2onnx.convert --tflite your_model.tflite --output your_model.onnx
```

Once converted, place your `your_model.onnx` file in the `models/` directory and add the model name (without extension) to your wake word configuration.

**Pro tip:** Test your custom model thoroughly before relying on it. Custom models can be finicky as fuck and might not work as well as the pre-trained ones.

## 🎯 Usage

### Command Line Options
```bash
python main.py              # Run application normally
python main.py --settings   # Open settings only (quick configuration)
python main.py --help       # Show all command line options
```

### Voice activation
- **Hotkey**: `Ctrl+Shift+H` (default)
- **Wake word**: Say "Alexa" or other configured wake words
- **Tray menu**: Right click on tray icon
- **Settings shortcut**: Run with `--settings` flag

### Application states
- **🔵 Listening** - Listening to your speech
- **🟠 Processing** - Processing in HA
- **🟣 Responding** - Playing response
- **🔴 Error** - Something fucked up
- **🟢 Success** - All good

### Sounds
The app plays sounds from `sound/` directory:
- `activation.wav` - Recording start
- `deactivation.wav` - Session end

## 🎛️ Configuration Parameters

### Connection
- `HA_HOST` - HA server address
- `HA_TOKEN` - Access token
- `HA_PIPELINE_ID` - Pipeline ID (optional)

### Audio and VAD
- `HA_VAD_MODE` - VAD sensitivity (0-3, 3=most sensitive)
- `HA_SILENCE_THRESHOLD_SEC` - Silence time to end recording
- `HA_SAMPLE_RATE` - Sample rate (8000/16000/32000)
- `HA_FRAME_DURATION_MS` - VAD frame length (10/20/30ms)

### Wake Word Detection
- `HA_WAKE_WORD_ENABLED` - Enable wake word detection (true/false)
- `HA_WAKE_WORD_MODELS` - Comma-separated list of wake word models
- `HA_WAKE_WORD_THRESHOLD` - Detection sensitivity (0.0-1.0)
- `HA_WAKE_WORD_VAD_THRESHOLD` - Voice activity threshold (0.0-1.0)

### Interface & Controls
- `HA_HOTKEY` - Activation hotkey (ctrl+shift+h, ctrl+alt+h, alt+space, etc.)
- `HA_SOUND_FEEDBACK` - Activation sounds (true/false)
- `HA_RESPONSE_TEXT_ENABLED` - Show assistant responses as text overlay (true/false)
- `HA_ANIMATIONS_ENABLED` - Enable visual animations with Three.js (true/false)
- `ANIMATION_PORT` - Animation server port (default: 8765)

### Device Selection
- `HA_MICROPHONE_INDEX` - Specific microphone ID (-1 for automatic)
- `HA_OUTPUT_DEVICE_INDEX` - Specific output device ID (-1 for automatic)
- `HA_OUTPUT_SAMPLE_RATE` - Output sample rate for playback (-1 for automatic)


### Debug & Logging
- `DEBUG` - Debug mode with detailed file logging (true/false)

## 🐛 Troubleshooting

### Python version incompatibility (Linux)
**Error**: `ERROR: Could not find a version that satisfies the requirement tflite-runtime`

**Cause**: You're using Python 3.12 or 3.13, which don't have tflite-runtime packages available.

**Solutions**:
1. **Install Python 3.11** (recommended):
   ```bash
   # For Ubuntu 22.04 and older (has Python 3.11 in repos):
   sudo apt install python3.11 python3.11-venv python3.11-dev

   # For Ubuntu 24.04+, Linux Mint 22+ (needs deadsnakes PPA):
   sudo add-apt-repository ppa:deadsnakes/ppa -y
   sudo apt update
   sudo apt install python3.11 python3.11-venv python3.11-dev

   # For Debian 13 (Trixie) - compiled from source:
   # The installer will do this automatically (takes 5-10 minutes)

   # For Fedora/RHEL:
   sudo dnf install python3.11 python3.11-devel

   # The installer will do all of this automatically
   ```

2. **Use Python 3.12** with ONNX-only mode:
   - The installer will automatically skip tflite-runtime
   - Wake word detection will use ONNX models (slightly slower but works)

3. **Check your Python version**:
   ```bash
   python3 --version
   ```

**Note**: Python 3.13+ is not supported due to multiple dependency incompatibilities (tflite-runtime, numpy versions). Use Python 3.11 for best results.

### "Cannot connect to Home Assistant"
- Check `HA_HOST` and `HA_TOKEN`
- Make sure HA is accessible
- Verify Assist is enabled

### "No microphone found"
- Check if microphone is connected
- Restart application
- Check microphone permissions

### "Pipeline not found"
- Remove `HA_PIPELINE_ID` from `.env` (will use default)
- Check available pipelines in settings

### Application hangs
- Enable `DEBUG=true` in settings
- Check console logs or log files in `logs/` directory
- Close and restart application (classic IT solution that actually works)

### Thread-related crashes (legacy)
- **Fixed in v1.3+** - Replaced problematic Tkinter with modern Flet UI
- All threading issues resolved with proper async/await patterns

### Interactive Prompts not working
- Verify port 8766 is accessible from Home Assistant server
- Test API directly with curl command
- Check GLaSSIST logs for HTTP server startup messages
- Make sure conversation manager is enabled in GLaSSIST

### Context not clearing between conversations
- **Fixed in v2.0** - Conversation context properly cleaned after each interaction
- If issues persist, restart GLaSSIST application

## 📚 FAQ

**Q: What Python version should I use?**
A: Python 3.11 is recommended for full compatibility. Python 3.12 works but uses ONNX-only mode. Python 3.13+ is not supported due to dependency issues (tflite-runtime, numpy). For Linux, install Python 3.11 for best results.

**Q: Does it work on Linux/Mac?**
A: Linux support added in v1.1.0 (beta). Use the install script. Mac support not planned.

**Q: Can I change the animation?**  
A: Yes, edit `frontend/index.html`. Shaders are in GLSL, so you need to know what you're doing.

**Q: Why Flet instead of Tkinter?**  
A: Tkinter had threading issues that caused hangs and crashes. Flet provides modern UI, proper async support, and cross-platform consistency. Plus it looks way better.

**Q: Can I use the old Tkinter settings?**  
A: Legacy support exists in `improved_settings_dialog.py` but it's not recommended. Flet version is more stable and feature-rich.

**Q: Why WebRTC VAD?**  
A: Because it works better than homemade algorithms. Tested by Google, so probably good.

**Q: Settings window is too big/small?**  
A: Flet UI is responsive and auto-maximizes. Use Escape key to close or resize the window.

**Q: App uses too much CPU/memory?**  
A: Disable animations in Settings > Advanced > Interface & Performance. This removes Three.js rendering and WebSocket server while keeping full voice functionality.

**Q: How do I set up interactive prompts?**  
A: Add the rest_command to your HA configuration.yaml, restart HA, then test with Developer Tools or curl. Interactive prompts are enabled by default in GLaSSIST v2.0.

**Q: Can external apps use the API?**  
A: Yes! Any application that can make HTTP POST requests can trigger GLaSSIST prompts. Perfect for integration with other home automation systems, scripts, or custom applications.

**Q: What's the difference between regular wake word and interactive prompts?**  
A: Regular wake word is user-initiated ("Hey Jarvis, turn on lights"). Interactive prompts are system-initiated (HA asks "Turn on lights?" and waits for voice response).

**Q: How does media player volume management work?**  
A: GLaSSIST automatically saves current volume levels, reduces them to a target level during voice interactions, then restores the original levels afterward. This ensures GLaSSIST is clearly audible without permanently changing your media volumes.

**Q: Can I use wait_for_response: false for announcements?**  
A: Yes! Set wait_for_response to false for TTS-only announcements that don't need user input. Perfect for notifications, status updates, and confirmations.

## 📄 License

MIT License. Do whatever you want, just don't blame me when something doesn't work.

## ☕ Support

If the app helped you and you want to buy me a coffee:
[☕ Buy me a coffee](https://buymeacoffee.com/smolinskip)

---

*Made with ❤️ and occasional frustration by [Patryk Smoliński](https://github.com/SmolinskiP)*
