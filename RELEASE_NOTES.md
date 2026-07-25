## ✨ GLaSSIST 3.6.0 — Conversation memory & update checks

### ✨ Features
- **Conversation history carries over between commands** (#48). Follow-ups like *"turn it off again"*
  now work instead of getting a *"which device?"* clarification. New `HA_CONVERSATION_TIMEOUT` setting
  (slider in Settings) controls how long context is kept — default **300 s**, `0` disables it. Only
  matters with an LLM conversation agent.
- **Automatic update checks.** On startup GLaSSIST checks GitHub for a newer release and shows a brief
  cyan *"Update available"* animation. Current version and a one-click **Update** link now sit in a bar
  at the top of Settings. Set `HA_UPDATE_CHECK=false` to disable it.

### 🖥️ Platforms
Cross-platform — Windows and Flatpak/Linux.
