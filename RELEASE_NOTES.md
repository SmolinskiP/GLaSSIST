## 🔊 Processing Sound & Configurable Feedback Sounds

While waiting for the assistant's response (orange "Processing" state), GLaSSIST can now loop an optional "thinking" sound — great for slow LLM-based agents when you're not looking at the screen (#XX).

### What's new
- **Processing sound loop** — plays from the end of recording until the response arrives, in both hotkey/WebSocket and ESPHome satellite mode. Opt-in via `HA_PROCESSING_SOUND=true` (default: off).
- **Selectable sound files** — pick activation, deactivation and processing sounds in **Settings → Audio**. Drop your own `.wav/.mp3/.flac/.ogg` files into the `sound/` folder and they'll show up in the dropdowns.
- **Two bundled processing sounds** — a subtle generated pulse (`processing.wav`) and a UI chime (`processing2.wav`).

### New config options
```
HA_PROCESSING_SOUND=false
HA_SOUND_ACTIVATION=activation.wav
HA_SOUND_DEACTIVATION=deactivation.wav
HA_SOUND_PROCESSING=processing.wav
```
