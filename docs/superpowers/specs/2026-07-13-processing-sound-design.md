# Processing Sound + Configurable Feedback Sounds — Design

**Date:** 2026-07-13
**Status:** Approved by user

## Problem

While GLaSSIST is in the *Processing* state (orange orb — waiting for Home Assistant / LLM
agent to respond) the app is completely silent. With slow LLM-based conversation agents
this leaves the user unsure whether the command was picked up at all when they are not
looking at the screen (GitHub feature request). Additionally, activation / deactivation /
processing sounds are hardcoded to fixed filenames and cannot be swapped from the UI.

## Solution Overview

1. An optional, continuously looped **processing sound** that plays from the moment
   recording ends (state → `processing`) until the response / error arrives.
2. **Selectable sound files** for activation, deactivation and processing states via
   dropdowns in the Flet settings UI, listing all audio files in the `sound/` folder.

## Configuration (.env)

| Variable | Default | Meaning |
|---|---|---|
| `HA_SOUND_ACTIVATION` | `activation.wav` | Filename in `sound/` played on session start |
| `HA_SOUND_DEACTIVATION` | `deactivation.wav` | Filename in `sound/` played on session end |
| `HA_SOUND_PROCESSING` | `processing.wav` | Filename in `sound/` looped during processing |
| `HA_PROCESSING_SOUND` | `false` | Master switch for the processing loop (opt-in) |

Existing `HA_SOUND_FEEDBACK` keeps controlling activation/deactivation sounds; the
processing loop has its own independent switch.

## Components

### utils.py
- `play_feedback_sound(sound_name)` keeps its API (`"activation"` / `"deactivation"`),
  but resolves the actual filename from the env vars above instead of `{name}.wav`.
- New `ProcessingSoundLoop` class with `start()` / `stop()`:
  - `start()` is a no-op when `HA_PROCESSING_SOUND` is not truthy or the file is missing
    (warning logged for missing file).
  - Daemon thread loads the file once, then loops: `sd.play(...)` +
    `stop_event.wait(duration)` — so `stop()` interrupts within milliseconds via
    `stop_event.set()` + `sd.stop()`.
  - Honors the configured output device and resamples like `play_feedback_sound`.
  - `stop()` is idempotent; `start()` while already running is a no-op.

### main.py
- Start the loop in `on_audio_end` (where `change_state("processing")` happens).
- Stop the loop immediately after `receive_response()` returns, before TTS playback /
  error handling. Defensive `stop()` also in `except` and `finally` blocks so the loop
  can never outlive the session.

### satellite_protocol.py
- Same start/stop wiring around its processing phase.

### flet_settings.py (Audio tab, Activation card)
- Three dropdowns (*Activation sound*, *Deactivation sound*, *Processing sound*)
  listing `.wav/.mp3/.flac/.ogg` files found in `sound/`.
- Switch: *Play processing sound while waiting for response*.
- All four new variables saved to `.env`.
- Legacy tkinter dialog (`improved_settings_dialog.py`) intentionally untouched.

### Asset
- `sound/processing.wav`: programmatically generated (numpy) quiet "thinking pulse" —
  a soft low sine blip followed by silence, ~1.5–2 s total, designed to loop cleanly
  as a periodic tick.

### Docs / installers
- Update `.env.example`, `README.md`, `install-linux.sh`, `setup.iss`
  (and `setup_debug.iss`) with the new variables and defaults.

## Error Handling
- Missing/unreadable sound file → log warning, no loop, no crash.
- Loop thread is a daemon; app exit never blocks on it.
- Any exception inside the loop thread is caught and logged, loop terminates.

## Testing
- `tests/test_utils.py`: filename resolution from env (defaults + overrides),
  `ProcessingSoundLoop` start/stop with mocked sounddevice, disabled switch → no-op,
  missing file → no-op, idempotent stop.

## Out of Scope
- Volume slider for the processing sound (the bundled asset is simply quiet).
- Periodic-interval playback mode (looping file with embedded silence covers it).
- Changes to the legacy tkinter settings dialog.
