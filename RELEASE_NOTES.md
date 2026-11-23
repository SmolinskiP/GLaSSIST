## 🏗️ GLaSSIST 3.10.1 — Installer built by GitHub

### 🏗️ Windows installer built by GitHub

- **`GLaSSIST-Setup.exe` is now built by GitHub Actions** straight from the source code in this repository, not on my PC. Anyone can open the [Windows build workflow](https://github.com/SmolinskiP/GLaSSIST/actions/workflows/windows.yml), see exactly what went into the installer, and compare its SHA-256 (printed in the build log) with the file you downloaded. This release is also the first test of this pipeline.
- **The executable has proper version info** (product name and version in file properties).
- Code signing is not there yet. I'm working on free signing for open source projects, which should also help with false antivirus alerts like [#70](https://github.com/SmolinskiP/GLaSSIST/issues/70).

### 🐛 Bug fixes

- **`HA_UPDATE_CHECK=false` turns off all GitHub requests.** The Settings window used to check for updates and load the changelog anyway. Both are skipped now when the update check is disabled.

### 🔧 Other

- README has new **Code signing policy** and **Privacy** sections.

## 🧠 GLaSSIST 3.10.0 — Clear AI errors and wake word detection clips

### ✨ New features

- **AI-service errors in plain language (ESPHome).** When the conversation agent fails (for example Gemini's `503 Service Unavailable`, a used-up quota or a refused API key), Home Assistant used to show and read out the raw English error with the provider's JSON. GLaSSIST now shows a short sentence in your interface language, such as "The AI service (Google Generative AI) is overloaded right now. Try again in a few seconds." On Windows it is also spoken with an installed voice of that language, on your selected speaker, and the hotkey or wake word can cut it off. Without a matching voice (or on Linux) Home Assistant's own audio plays as before. Recognises errors from Google Generative AI, OpenAI, Anthropic, Ollama and OpenRouter; normal answers are never touched. Contributed in [#60](https://github.com/SmolinskiP/GLaSSIST/pull/60) (thanks [@gustavomorozi](https://github.com/gustavomorozi)!).
- **Save a clip of every wake word detection.** Turn on **Settings → Wake Word → Save a 3-second audio clip of every detection** and each detection keeps the ~3 seconds of audio that triggered it. Delete the clips where you really said the word; the rest are the sounds that fool the model, ready for retraining a custom wake word (see [glassist-wakeword-trainer](https://github.com/gustavomorozi/glassist-wakeword-trainer)). **Off by default**, clips stay on your computer, at most 300 per model. Open them with **Wake Word → Model Management → Open Detection Clips Folder**; the Windows uninstaller removes them. Works in room mode too. Contributed in [#58](https://github.com/SmolinskiP/GLaSSIST/pull/58) (thanks [@gustavomorozi](https://github.com/gustavomorozi)!).

### 🐛 Bug fixes

- **ESPHome discovery no longer advertises `127.0.0.1`.** When the PC had a LAN address but no default gateway (for example right after boot), GLaSSIST announced itself as `127.0.0.1` and Home Assistant tried to connect to itself, leaving GLaSSIST on "Connecting...". It now finds the address through the route to your Home Assistant, never guesses between VPN, Hyper-V/WSL or VirtualBox adapters, and retries every 30 seconds until the network is up. Reported and first fixed in [#59](https://github.com/SmolinskiP/GLaSSIST/pull/59) (thanks [@gustavomorozi](https://github.com/gustavomorozi)!).

## 🎙️ GLaSSIST 3.9.0 — Faster replies, cancel anytime

### ✨ New features

- **Press the hotkey again to cancel.** The activation hotkey now works as a toggle: press it while GLaSSIST is listening, thinking or speaking and the interaction stops. Works in WebSocket, ESPHome and room mode, so one Stream Deck button can start and cancel. Implements [#61](https://github.com/SmolinskiP/GLaSSIST/issues/61).
- **Streamed TTS in ESPHome mode.** With a Home Assistant pipeline that streams speech (HA 2025.7+), the reply starts playing as soon as the first audio arrives instead of after the whole answer is synthesized. Turn it off in **Settings → Audio & VAD → Play streamed replies as they arrive**. Contributed in [#69](https://github.com/SmolinskiP/GLaSSIST/pull/69) (thanks [@omermuslu](https://github.com/omermuslu)!). Part of [#66](https://github.com/SmolinskiP/GLaSSIST/issues/66).
- **Interrupt a reply with the wake word (ESPHome).** Enable **Settings → Wake Word → Let the wake word interrupt replies** and saying the wake word while GLaSSIST talks stops the reply and starts a new command. Off by default — it works best with a microphone that cancels speaker echo. Part of [#66](https://github.com/SmolinskiP/GLaSSIST/issues/66).
- **Processing sound after speech is recognized (ESPHome).** Choose when the processing sound starts: when you stop speaking (as before) or only once Home Assistant recognized your words, so background noise doesn't trigger it. **Settings → Audio & VAD → Processing sound starts**. Implements [#68](https://github.com/SmolinskiP/GLaSSIST/issues/68).

### 🐛 Bug fixes

- **ESPHome mode starts with animations disabled.** Fixes [#65](https://github.com/SmolinskiP/GLaSSIST/issues/65).
- **TTS plays again in WebSocket mode on Linux.** Relative `/api/tts_proxy/…` URLs were treated as local files. Fixes [#63](https://github.com/SmolinskiP/GLaSSIST/issues/63).
- **GLaSSIST no longer blocks Windows shutdown.** The WebView2 teardown error is handled. Fixes [#64](https://github.com/SmolinskiP/GLaSSIST/issues/64).
- **`ANIMATION_PORT` is respected** by both the animation server and the overlay. Fixes [#62](https://github.com/SmolinskiP/GLaSSIST/issues/62).
- **Updating no longer resets your configuration.** The Windows installer used to write a fresh `.env` on every install in ESPHome mode, wiping microphone, hotkey and wake word settings. It now keeps an existing `.env` (and skips the setup pages), and writes it to the folder you actually installed to.
- **Saving settings keeps entries added by hand.** Keys the Settings window doesn't show (for example `HA_PROMPT_SERVER_PORT`, `HA_AI_AGENT_ID`, `WINDOW_WIDTH`) used to disappear after saving. They are now kept in an `OTHER` section.
- **Recording works with any sample rate setting.** At 22 050, 44 100 or 48 000 Hz, or with a stereo microphone, voice detection never heard speech and GLaSSIST waited forever. Unsupported values now fall back to 16 kHz, which Home Assistant speech-to-text expects, and stereo input is mixed to mono. The Settings list only offers 8 000 and 16 000 Hz. In ESPHome mode the microphone always records 16 kHz mono, the format the ESPHome voice protocol sends to Home Assistant.
- **Media players are no longer left quiet.** If Home Assistant was unreachable when restoring volumes, the original levels were lost and the next interaction saved the lowered volume as the "original". GLaSSIST now keeps the original levels until they are restored.
- **The overlay works without internet.** When Three.js couldn't be loaded (e.g. autostart before the network is up), the whole overlay stopped and showed no statuses. Texts and status messages now work anyway; only the ring animation is skipped.
- **Cancelling streamed TTS is immediate**, even if Home Assistant stops sending audio mid-reply. Previously it could wait up to 2 minutes and block other rooms.
- **A failed TTS stream no longer swallows the reply.** If streaming fails early, GLaSSIST plays the final audio from Home Assistant instead of staying silent.

### 🔧 Other

- More tests for cancelling, streaming, settings saves and media ducking.

## 🔉 GLaSSIST 3.8.1 — Media player ducking in ESPHome mode

### ✨ New features

- **Media players are lowered in ESPHome mode too.** Volume management (**Settings → Media Players**) used to work only in WebSocket mode. ESPHome satellite and room conversations now lower the selected media players while GLaSSIST listens and speaks, and restore them afterwards. In ESPHome mode this needs the Home Assistant address and access token (**Connection → WebSocket Settings**).
- **Changelog tab.** Settings now show the latest release notes straight from GitHub, with the installed version marked.
- **About & Help.** The About tab is renamed to make the issue tracker and contact details easier to find.

## 🌍 GLaSSIST 3.8.0 — Interface translations

### ✨ New features

- **GLaSSIST speaks your language.** The Settings window, tray menu and on-screen status messages can now be translated. Pick the language in **Settings → Advanced → Interface & Performance → Language** and restart GLaSSIST. English stays the default, and any text without a translation is shown in English. Contributed in [#56](https://github.com/SmolinskiP/GLaSSIST/pull/56) (thanks [@gustavomorozi](https://github.com/gustavomorozi)!).
  - **Português (Brasil)** — by [@gustavomorozi](https://github.com/gustavomorozi).
  - **Polski** — new in this release.
  - Want your language? Copy `locales/pl.json` to `locales/<code>.json`, translate the values and add the code to `LANGUAGES` in `i18n.py`. Pull requests welcome.
- **Help is one click away.** The About tab now links straight to [GitHub issues](https://github.com/SmolinskiP/GLaSSIST/issues) and to my email, so reporting a problem or sharing an idea is easy.

### 🐛 Bug fixes

- Room settings, the window title and the version status are now included in translations.
- Translations are bundled with the Flatpak build.

## 🩹 GLaSSIST 3.7.1 — Complete TTS playback on Windows

### 🐛 Bug fixes

- **The end of TTS replies and announcements is no longer cut off on Windows.** Without ffmpeg, MP3s from Home Assistant were decoded by a fallback that misjudges the length of variable-bitrate files and dropped the last ~0.5 s. GLaSSIST now bundles a decoder that reads the file to the end. Fixes [#55](https://github.com/SmolinskiP/GLaSSIST/issues/55) (thanks [@p2pmonitor](https://github.com/p2pmonitor) for the precise diagnosis).
- **Microphones are found even without a default input device.** Previously every microphone was skipped and startup reported "No microphone found".
- **Audio devices are always released on shutdown**, even when closing the stream fails.
- **Faster failure for an invalid pipeline.** A rejected pipeline (for example a deleted `HA_PIPELINE_ID`) is reported immediately instead of after a 15 s timeout.
- **Wake word reload keeps noise suppression off by default**, matching the setting used at startup.
- **Correct microphone level readings** for loud input (no more overflow).
- **Disconnected animation clients are dropped** from broadcasts.

### 🔧 Other

- **Rooms are marked as beta** in Settings.
- **Test suite repaired**: all tests run and pass again, isolated from the local `.env`.

## 🏠 GLaSSIST 3.7.0 — Multiple rooms, one assistant

### ✨ New feature

- **Rooms: connect multiple microphone/speaker pairs to one GLaSSIST instance.** Configure each pair in **Settings → Rooms**. Each room appears as a separate ESPHome device in Home Assistant, where you can assign its area and preferred voice assistant. Replies play through the speaker paired with the microphone that triggered the command. Implements [#51](https://github.com/SmolinskiP/GLaSSIST/issues/51) (thanks [@ReiberAndras](https://github.com/ReiberAndras) for the suggestion).
  - Each microphone has its own wake word detection. One conversation runs at a time; the first detection selects the room, and follow-up conversation stays in that room.
  - The voice hotkey uses the first room in the list. Tray pause/resume controls wake word detection in all rooms.
  - **Experimental and disabled by default.** Requires ESPHome mode and local wake word detection. Restart after changing room settings. Room timers, announcements and FFT visualization are not supported in this first version.

### 🐛 Bug fixes

- **Settings no longer need to download Flet on Windows.** The desktop client and its resources are bundled with the application, avoiding the download-related SSL failure reported in [#54](https://github.com/SmolinskiP/GLaSSIST/issues/54). Builds now check that the client is included. Thanks [@Schaefchen89](https://github.com/Schaefchen89) for identifying the cause and sharing the workaround.
- **More reliable settings saves.** Validation and save errors use visible dialogs, and settings are written atomically so a failed write does not overwrite the previous configuration. ESPHome mode no longer requires WebSocket credentials to save.
- **Corrected audio device names.** Repaired garbled Windows device names while preserving correctly encoded accented and non-Latin characters.
- **Bounded log files.** Repeated logger initialization no longer recreates handlers. File logging uses a rotating 2 MB log with up to three backups when `DEBUG=true`.
- **Protected room conversations during playback.** The hotkey waits until the current reply and echo cooldown finish, while automatic follow-up conversation remains available.
- **Fixed room speaker validation.** Automatic output settings no longer require 16 kHz support just to start room mode.
- **Consistent release versions.** Application, installer and Flatpak metadata are updated to 3.7.0. Build checks reject mismatched versions, and manual Flatpak release builds check out the requested release tag. Addresses the version mismatch reported in [#53](https://github.com/SmolinskiP/GLaSSIST/issues/53) (thanks [@hamsando](https://github.com/hamsando) for checking the packaged version).

## 🩹 GLaSSIST 3.6.1 — Input audio delay fix

### 🐛 Fixes
- **Voice input is no longer delayed.** The mic buffer wasn't flushed before recording, so GLaSSIST replayed 1–2 s of stale audio — picking up speech from *before* you triggered it and cutting off the end of your command. It now starts recording at the live edge. Most noticeable on Linux. Fixes [#49](https://github.com/SmolinskiP/GLaSSIST/issues/49) (thanks [@RheaAyase](https://github.com/RheaAyase) for the detailed diagnosis).

### 🔧 Debug
- Added greppable `⏱️ TIMING` logs (beep → connected → pipeline-ready → record-start) to measure activation latency from user-submitted logs.
