# 🎤 GLaSSIST

![gla](https://github.com/user-attachments/assets/23c012ed-11c0-4f3b-9eef-b9fa16071e13)

Desktop voice application for Home Assistant with visual animations and VAD (Voice Activity Detection). Because who has time to click through interfaces when you can just talk to your computer like it's a broken microphone?

## 🚀 Key Features

- **Voice activation** - Hotkey or click to activate
- **Wake word detection** - Over 100 pre-trained models (alexa, jarvis, glados etc.)
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

### Voice activation
- **Hotkey**: `Ctrl+Shift+H` (default)
- **Wake word**: Say "Alexa" or other configured wake words
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
├── models/                     # OpenWakeWord model files
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

### Wake Word Detection
- `HA_WAKE_WORD_ENABLED` - Enable wake word detection (true/false)
- `HA_WAKE_WORD_MODELS` - Comma-separated list of wake word models
- `HA_WAKE_WORD_THRESHOLD` - Detection sensitivity (0.0-1.0)
- `HA_WAKE_WORD_VAD_THRESHOLD` - Voice activity threshold (0.0-1.0)

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

## 📄 License

MIT License. Do whatever you want, just don't blame me when something doesn't work.

## 🍺 Support

If the app helped you and you want to buy me a coffee:
[☕ Buy me a coffee](https://buymeacoffee.com/smolinskip)

---

*Made with ❤️ and occasional frustration by [Patryk Smoliński](https://github.com/SmolinskiP)*
