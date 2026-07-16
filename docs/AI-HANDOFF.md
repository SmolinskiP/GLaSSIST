# AI Handoff Notes — moving development from Windows to Linux

Written 2026-07-16 by Claude for Claude, at the end of a long session on the owner's
Windows machine. Read this first when picking up work in the new Linux environment —
the machine-local memory directory does not travel; this file replaces it.

## Who you're working with

- Owner: Patryk Smoliński (SmolinskiP), repo `SmolinskiP/GLaSSIST`, communicates in Polish.
- **Style: pragmatic, zero bureaucracy.** The superpowers plugin (spec/plan/approval
  gates) was uninstalled at their explicit request ("za dużo biurokracji"). Ask short
  focused questions when needed, outline briefly, then build. Don't reintroduce
  ceremony. Old specs/plans live in `docs/superpowers/` — reference only.
- Commits go straight to `main`. Commit messages in English, conventional-ish
  (`feat:`, `fix:`, `ci:`, `docs:` mixed with plain sentences — match recent history).

## State of the repo (as of fe3d9c5)

Two work streams landed this week:

### 1. Processing sound + configurable feedback sounds (v3.1.0, shipped)
- `ProcessingSoundLoop` in `utils.py` loops `sound/processing.wav` during the
  Processing state; wired in `main.py` (`on_audio_end` → start, after
  `receive_response` + all error paths → stop) and `satellite_protocol.py`.
- Config: `HA_PROCESSING_SOUND` (default false), `HA_SOUND_ACTIVATION` /
  `HA_SOUND_DEACTIVATION` / `HA_SOUND_PROCESSING` (filenames in `sound/`).
- Settings UI (`flet_settings.py`): three dropdowns + switch in the Audio tab.
- Two bundled processing sounds: generated pulse (`processing.wav`) and the owner's
  chime + 0.5s silence (`processing2.wav`). Leftover `sound/processing.mp3` on the
  old machine was untracked — irrelevant on Linux.
- Release notes draft in `RELEASE_NOTES.md` (untracked on the Windows machine — if
  missing, the release was published; the feature request was issue **#42**).

### 2. Flatpak packaging (issue #43, infrastructure DONE, smoke test PENDING)

Everything lives in `packaging/flatpak/` + two workflows:

- **Manifest** `io.github.SmolinskiP.GLaSSIST.yml`: GNOME 48 runtime (spike confirmed
  it ships GTK3 + WebKit2GTK 4.1, which pywebview needs — results in
  `packaging/flatpak/SPIKE-RESULTS.md`). Native modules built from source: portaudio,
  libass, ffmpeg 6.1.2, mpv 0.36 (libmpv only, for Flet; 0.36 deliberately — 0.37+
  hard-requires libplacebo). Python deps via `python3-modules.json` (54 binary wheels)
  plus manual modules: PyAudio (sdist, no Linux wheels) and openwakeword
  (`--no-deps` — it declares tflite-runtime on Linux which has no py3.12 wheels;
  the app uses the ONNX framework, see merged PR #41).
- **`flatpak-pipgen.yml`**: regenerates `python3-modules.json` when
  `requirements-linux.txt` changes. Chain: `pip-compile` (full transitive lock on
  linux/py3.12) → `req2flatpak --target-platforms 312-x86_64`. The workflow COMMITS
  results back to main (that pattern existed because the Windows session had no `gh`
  and no way to read Actions logs — see "old-machine workarounds" below).
  `flet-desktop-light==0.28.3` is pinned explicitly (it's a `flet[desktop]` extra,
  pip-compile won't pull it from `flet` alone).
- **`flatpak.yml`**: builds `GLaSSIST.flatpak`. Triggers: manual dispatch; push to
  main touching `packaging/flatpak/**` or the workflow itself (iteration loop —
  REMOVE this path trigger once stable); `release: published` → attaches the bundle
  to the release. Gotcha that bit us: `tags:` + `paths:` in one push trigger are
  ANDed by GitHub — that's why release uses the `release` event.
- **First build passed end-to-end** (run 29474966813). Bundle is an Actions artifact.
- **Code changes for the sandbox** (all guarded by `FLATPAK_ID`, tested in
  `tests/test_platform_utils.py` + `tests/test_utils.py`): `.env` resolved via
  `platform_utils.get_env_file_path()` (XDG config dir in Flatpak), user sound files
  via `get_user_sound_dir()` (XDG data dir, merged into settings dropdowns).

**NEXT STEP: smoke test the bundle on Linux** — now trivial since you ARE on Linux:
```bash
flatpak install --user GLaSSIST.flatpak   # artifact from the Actions run, or rebuild
flatpak run io.github.SmolinskiP.GLaSSIST
```
Checklist: app starts; animation window renders (WebKit); settings dialog opens
(Flet needs libmpv — watch for that); settings SAVE persists to
`~/.var/app/io.github.SmolinskiP.GLaSSIST/config/glasssist/.env`; mic capture; TTS
playback; wake word (bundled ONNX models); satellite mode port 6053 + mDNS.

**Known v1 limitations (documented in README):**
- Tray: NO AppIndicator module in the manifest yet — pystray falls back to GTK
  StatusIcon (works on X11/XFCE, absent on KDE/GNOME-Wayland). Iteration 2 = build
  the ayatana stack (libdbusmenu + ayatana-ido + libayatana-indicator +
  libayatana-appindicator, cmake, WITH introspection — the flathub shared-modules
  libappindicator JSON disables introspection, useless for pystray, don't reuse it).
- Global hotkey: X11 only. Wayland needs the GlobalShortcuts portal — separate issue.
- Autostart: manual `~/.config/autostart` entry; Background portal is a follow-up.
- x86_64 only (`--target-platforms 312-x86_64`).
- After smoke test passes: reply on **issue #43** (draft at the end of
  `docs/superpowers/plans/2026-07-15-flatpak-packaging.md`), then think about Flathub
  (step 2 — requires a repo in the Flathub org; owner reluctantly OK with that
  since it's how Flathub works, but GitHub-Releases bundle comes first).

## Old-machine workarounds you can now DROP

On Windows there was no `gh` CLI and no GitHub token, so: workflows were triggered by
self-referencing `push.paths`, results read via public REST API (job/step conclusions),
and logs smuggled out by committing `pipgen.log` to the repo. On Linux: if `gh` is
available (check `gh auth status`), use it — trigger with `gh workflow run`, read logs
with `gh run view --log`. Then simplify: remove the pipgen log-commit hack and the
temporary push triggers. Also `flatpak-builder` can now run LOCALLY, which beats the
whole CI round-trip for manifest iteration.

## Open threads beyond Flatpak

- **Issue #31 (premature TTS audio cutoff, Piper)** — root cause analysis done, no fix
  applied (couldn't reproduce on owner's machine). Timeline: PR #26 (Jan 20) fixed
  exactly this with an OutputStream callback + 0.5s drain; commit `0d64540` (Jan 22,
  audioread introduction) reverted playback to bare `sd.play()+sd.wait()`; issue filed
  Mar 9. Mechanism: `sd.wait()` returns when the Python buffer is consumed, device
  buffer tail (100–500ms, worst on Bluetooth) gets cut; Piper ends files flush with
  the last word. Second suspect in the same commit: audioread MP3 decode dropping the
  final frame. Agreed non-invasive plan: (1) ask reporter — does HA-side playback cut
  too? which output device/BT? does the downloaded tts_proxy file contain the last
  word? (a ready-to-paste comment was drafted in the session, owner may have posted
  it); (2) DEBUG-level diagnostics: decode path used, decoded duration, RMS of last
  300ms, wall-clock vs expected; (3) opt-in `HA_TTS_TAIL_PADDING_MS` (default 0).
- **Stale test suite**: 107 of ~180 tests fail on main — old pygame mocks (code moved
  to sounddevice long ago), missing pytest-asyncio, API drift in animation_server
  tests. The new tests (platform_utils, sound config, processing loop) are green.
  Cleaning this up would make CI actually usable — candidate task.
- **`get_env` precedence gotcha**: `utils.get_env` reads the `.env` FILE first
  (`_read_from_env_file`), os.environ is only a fallback. Tests patching os.environ
  must mock `utils._read_from_env_file` (see `TestSoundConfiguration` for the
  pattern) or the developer's real .env leaks in.
- **`linux-voice-assistant/`** nested repo (clone of mricharz's fork, wake-word/WAV
  tools) sat inside the Windows working copy, untracked. Won't exist on Linux unless
  the owner copies it. If they mention it — that's what it was.
- `.env` is gitignored — the owner needs to reconfigure on the Linux box (or copy it);
  settings dialog or `.env.example` are the starting points.

## Dev quickstart on Linux

- Run: `python main.py` (deps: `install-linux.sh` for native bits or work inside the
  Flatpak). Tests: `python -m pytest tests/test_utils.py tests/test_platform_utils.py`
  (full `tests/` is the stale-failure minefield described above).
- The Flet settings UI needs libmpv on Linux; pywebview needs WebKit2GTK 4.x (GTK3).
