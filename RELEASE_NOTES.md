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
