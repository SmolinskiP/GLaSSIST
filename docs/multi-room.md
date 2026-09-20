# Multiple rooms (experimental)

Configure everything in **Settings → Rooms**. No separate configuration file or
manual editing is required. Single-device mode remains the default.

## Setup

1. Open **Settings → Rooms** and turn on **Use multiple rooms**. This selects
   ESPHome mode and enables local wake word detection.
2. Click **Add room**, enter a room name and select its microphone and speaker
   from the device lists. Repeat for each room. **Refresh devices** updates the
   lists without opening a microphone for recording.
3. The first room handles the voice hotkey. Use **Use for hotkey** to move a room
   to the top. Connection ports are assigned automatically; change them under
   **Advanced** only if necessary. Each room needs a distinct microphone and port.
4. Choose your wake word in the **Wake Word** tab, click **Save Settings**, and
   restart GLaSSIST.
5. Add the discovered room devices through Home Assistant's ESPHome integration.
   If discovery is unavailable, add the computer's IP and each room's connection
   port (shown under **Advanced**) manually. Assign each device its area and
   preferred voice assistant in Home Assistant.

See [HA area assignment](https://www.home-assistant.io/voice_control/assign_areas_floors/).

Renaming a room preserves its Home Assistant device identity. Removing and
recreating a room creates a new identity. Existing configurations from the earlier
file-based preview are imported into the form and saved with the other settings;
the original file is not deleted.

## Behavior and limits

- Every microphone has its own capture stream and wake model. The first detection
  reserves the conversation; other rooms wait while it is processing or speaking.
  This does not select the acoustically nearest microphone.
- Replies go to the speaker assigned to the source room. A short cooldown reduces
  retriggers; this is not acoustic echo cancellation.
- Tray pause/resume controls wake detection in all rooms. An active conversation
  can finish, and explicit hotkey activation remains available.
- Room mode does not use the shared activation/processing sounds, FFT visualization,
  timers or announcements pushed from Home Assistant in this first version.
- Microphones must support 16 kHz mono capture. Outputs must support the TTS sample
  rate or the output sample rate selected in Advanced settings.
- Device indices can change when reconnecting hardware. Refresh and verify device
  selections in Settings after hardware changes. Unavailable saved devices stay
  visible instead of silently switching to another device.
- Invalid configurations or device startup failures stop room startup. A microphone
  read failure stops room mode; correct the problem and restart the application.
- A stuck conversation closes its connection after 180 seconds so HA can reconnect.

## Return to one microphone

Turn off **Use multiple rooms**, save, and restart. The room list is retained for
later use. Your single-device microphone and speaker settings remain available in
**Audio & VAD**; select your preferred connection mode in **Connection**.

## Hardware acceptance check

With two microphone/speaker pairs, trigger each room separately and verify its
speaker and a room-relative command. Then let both microphones hear one wake word:
HA should receive only one run. Check follow-up conversation, long TTS responses,
HA disconnect/reconnect and shutdown. Automated tests do not replace this check.
