# 🎤 GLaSSIST

Desktop voice application for Home Assistant with visual animations and VAD (Voice Activity Detection). Because who has time to click through interfaces when you can just talk to your computer like it's a broken microphone?

## 🚀 Key Features

- **Voice activation** - Hotkey or click to activate
- **WebRTC VAD** - Smart speech detection (doesn't react to every fridge beep)
- **Visual animations** - Three.js with shaders and FFT audio analysis (because a simple circle is not enough)
- **Tray integration** - Lives in system tray like a proper application
- **Pipeline selection** - Choose your preferred assistant pipeline
- **Transparent window** - Doesn't block your desktop (finally, someone thought about it)

## 📋 Requirements

- **Home Assistant** with Assist enabled
- **Python 3.8+** 
- **Windows** 
- **Access token** for HA (long-lived access token)

## 🛠️ Installation

### 1. Clone repository
```bash
git clone https://github.com/SmolinskiP/GLaSSIST.git
cd GLaSSIST
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configuration
Create `.env` file:
```env
# === CONNECTION ===
HA_HOST=your-homeassistant.local:8123
HA_TOKEN=your_long_lived_access_token_here

# === ACTIVATION ===
HA_HOTKEY=ctrl+shift+h

# === AUDIO ===
HA_VAD_MODE=3
HA_SILENCE_THRESHOLD_SEC=0.8
HA_SOUND_FEEDBACK=true

# === OPTIONAL ===
HA_PIPELINE_ID=your_pipeline_id
DEBUG=false
```

**Pro tip:** Use the "Settings" button in the app instead of manually creating the file. This isn't 1995, we have GUIs.

### 4. Run
```bash
python main.py
```

## ⚙️ Home Assistant Configuration

### Access Token
1. Go to `Profile` → `Long-Lived Access Tokens`
2. Click `Create Token`
3. Copy token to `.env`

Without this, the app will be as useful as a calculator without batteries.

### Pipelines (optional)
The app automatically fetches available pipelines. If you have more than one, select it in settings.

## 🎯 Usage

### Voice activation
- **Hotkey**: `Ctrl+Shift+H` (default)
- **Click**: Click on animation when hidden
- **Tray menu**: Right click on tray icon

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

## 🔧 Project Structure

```
├── main.py                      # Main application file
├── client.py                    # WebSocket client for HA
├── audio.py                     # Audio management and VAD
├── vad.py                       # Voice Activity Detection
├── animation_server.py          # WebSocket server for animations
├── improved_settings_dialog.py  # Settings GUI
├── utils.py                     # Utility functions
├── frontend/
│   └── index.html              # Three.js interface
├── sound/                      # Sound files
├── img/                        # Icons
└── requirements.txt            # Python dependencies
```

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

### Interface
- `HA_HOTKEY` - Activation hotkey
- `HA_SOUND_FEEDBACK` - Activation sounds (true/false)
- `ANIMATION_PORT` - Animation server port (8765)
- `DEBUG` - Debug mode (true/false)

## 🐛 Troubleshooting

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
- Enable `DEBUG=true`
- Check console logs
- Restart application (classic IT solution)

## 📚 FAQ

**Q: Does it work on Linux/Mac?**  
A: Windows only for now. No plans for other platforms.

**Q: Can I change the animation?**  
A: Yes, edit `frontend/index.html`. Shaders are in GLSL, so you need to know what you're doing.

**Q: Why WebRTC VAD?**  
A: Because it works better than homemade algorithms. Tested by Google, so probably good.

**Q: App uses too much CPU?**  
A: Disable debug mode and lower `HA_SAMPLE_RATE` to 8000. Or buy a better computer.

## 🛣️ TODO

- [ ] **Wake word activation** - Activation by custom keyword
- [ ] **Custom wake words** - Ability to train your own wake words

## 📄 License

MIT License. Do whatever you want, just don't blame me when something doesn't work.

## 🍺 Support

If the app helped you and you want to buy me a coffee:
[☕ Buy me a coffee](https://buymeacoffee.com/smolinskip)

---

*Made with ❤️ and occasional frustration by [Patryk Smoliński](https://github.com/SmolinskiP)*