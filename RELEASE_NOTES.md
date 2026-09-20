## 🏠 GLaSSIST 3.7.0 — Multiple rooms, one assistant

### ✨ New feature

- **Rooms: connect multiple microphone/speaker pairs to one GLaSSIST instance.**
  Configure each pair in **Settings → Rooms**. Each room appears as a separate ESPHome
  device in Home Assistant, where you can assign its area and preferred voice assistant.
  Replies play through the speaker paired with the microphone that triggered the command.
  Implements #51 (thanks @ReiberAndras for the suggestion).
  - Each microphone has its own wake word detection. One conversation runs at a time;
    the first detection selects the room, and follow-up conversation stays in that room.
  - The voice hotkey uses the first room in the list. Tray pause/resume controls wake
    word detection in all rooms.
  - **Experimental and disabled by default.** Requires ESPHome mode and local wake word
    detection. Restart after changing room settings. Room timers, announcements and FFT
    visualization are not supported in this first version.

### 🐛 Bug fixes

- **Settings no longer need to download Flet on Windows.** The desktop client and its
  resources are bundled with the application, avoiding the download-related SSL failure
  reported in #54. Builds now check that the client is included.
- **More reliable settings saves.** Validation and save errors use visible dialogs,
  and settings are written atomically so a failed write does not overwrite the previous
  configuration. ESPHome mode no longer requires WebSocket credentials to save.
- **Corrected audio device names.** Repaired garbled Windows device names while preserving
  correctly encoded accented and non-Latin characters.
- **Bounded log files.** Repeated logger initialization no longer recreates handlers.
  File logging uses a rotating 2 MB log with up to three backups when `DEBUG=true`.
- **Protected room conversations during playback.** The hotkey waits until the current
  reply and echo cooldown finish, while automatic follow-up conversation remains available.
- **Fixed room speaker validation.** Automatic output settings no longer require 16 kHz
  support just to start room mode.
- **Consistent release versions.** Application, installer and Flatpak metadata are updated
  to 3.7.0. Build checks reject mismatched versions, and manual Flatpak release builds
  check out the requested release tag.

## 🩹 GLaSSIST 3.6.1 — Input audio delay fix

### 🐛 Fixes
- **Voice input is no longer delayed.** The mic buffer wasn't flushed before recording, so
  GLaSSIST replayed 1–2 s of stale audio — picking up speech from *before* you triggered it and
  cutting off the end of your command. It now starts recording at the live edge. Most noticeable
  on Linux. Fixes #49 (thanks @RheaAyase for the detailed diagnosis).

### 🔧 Debug
- Added greppable `⏱️ TIMING` logs (beep → connected → pipeline-ready → record-start) to measure
  activation latency from user-submitted logs.
