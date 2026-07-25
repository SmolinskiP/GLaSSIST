## 🩹 GLaSSIST 3.6.1 — Input audio delay fix

### 🐛 Fixes
- **Voice input is no longer delayed.** The mic buffer wasn't flushed before recording, so
  GLaSSIST replayed 1–2 s of stale audio — picking up speech from *before* you triggered it and
  cutting off the end of your command. It now starts recording at the live edge. Most noticeable
  on Linux. Fixes #49 (thanks @RheaAyase for the detailed diagnosis).

### 🔧 Debug
- Added greppable `⏱️ TIMING` logs (beep → connected → pipeline-ready → record-start) to measure
  activation latency from user-submitted logs.
