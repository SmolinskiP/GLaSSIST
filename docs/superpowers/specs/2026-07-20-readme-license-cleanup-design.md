# README and license cleanup design

## Goal

Make the repository landing page useful to both application users and
contributors without duplicating detailed documentation. Keep the existing
visual identity, accurately describe the current application, and retain one
canonical MIT license file.

## Verified product description

GLaSSIST is a Windows and Linux desktop voice satellite for Home Assistant. It
captures microphone audio, detects the end of speech with WebRTC VAD, sends
voice interactions through Home Assistant, plays TTS responses, and presents
visual feedback in a desktop overlay.

The application supports two connection modes:

- ESPHome Satellite is the recommended local-network mode. Home Assistant
  discovers the application as a voice satellite, and this mode supports
  timers and conversation follow-up.
- WebSocket is the legacy client mode. GLaSSIST connects to Home Assistant with
  a server address and long-lived token. It can work through remote Home
  Assistant addresses but does not provide the complete satellite feature set.

Verified user-facing capabilities include wake-word, keyboard-shortcut and
system-tray activation; selectable Assist pipelines and audio devices; local
TTS playback; configurable response text and Three.js animation; temporary
Home Assistant media-player volume adjustment; and a local HTTP endpoint for
interactive prompts.

## README structure

The rewritten README will target approximately 180–230 lines and use this
order:

1. Preserve the existing generated GLaSSIST banner.
2. Add a short, factual introduction explaining the application's purpose and
   the two connection modes.
3. Reduce Key Features to roughly six high-value capabilities.
4. Preserve the existing application image in approximately its current
   position, immediately after the feature overview.
5. Add a **For users** section containing:
   - Windows installer installation;
   - Linux Flatpak installation;
   - Linux installation-script method;
   - concise initial Home Assistant configuration;
   - basic activation and usage information.
6. Add a **For developers** section containing:
   - source-install requirements for Windows and Linux;
   - cloning, dependency installation and application startup;
   - the main test commands;
   - links to `.env.example` and relevant detailed documentation;
   - a compact map of the main modules.
7. Keep only a short Interactive Prompts summary and link to
   `INTERACTIVE_PROMPTS_SETUP.md` for setup examples and API details.
8. Finish with License and Support.

## Content removal and consolidation

- Remove the Troubleshooting and FAQ sections. Useful setup facts that are not
  obvious will be retained next to the relevant installation method.
- Remove Star History. It is not necessary to install or understand the
  project, and the current external chart uses the wrong repository casing.
- Remove the exhaustive environment-variable listing and link to
  `.env.example` instead.
- Remove duplicated Interactive Prompts examples and link to
  `INTERACTIVE_PROMPTS_SETUP.md` instead.
- Remove historical claims, resolved-problem notes, repeated marketing copy,
  and stale dependency guidance.
- Preserve the current banner and application image. No image or GIF asset will
  be replaced or redesigned.

## Installation presentation

Requirements and installation will be combined rather than presented as two
large, repetitive sections. The user-facing methods will be shown in this
order:

1. Windows installer (`GLaSSIST-Setup.exe`).
2. Linux Flatpak (`GLaSSIST.flatpak`).
3. Linux installation script (`install-linux.sh`).
4. Windows or Linux from source, under **For developers**.

Each method will list only its own prerequisites and commands. Flatpak-specific
configuration paths and the Wayland hotkey limitation will remain alongside
the Flatpak instructions.

## License consolidation

`LICENSE` and `LICENSE.txt` currently have identical SHA-256 hashes and contain
the same MIT text. The canonical file will be `LICENSE`.

Implementation will:

- update `setup.iss` and `setup_debug.iss` so `LicenseFile` points to
  `LICENSE`;
- remove `LICENSE.txt`;
- leave the historical reference in
  `docs/superpowers/plans/2026-07-15-flatpak-packaging.md` unchanged because it
  records the state and assumptions of an earlier packaging plan;
- link the README License section to `LICENSE`.

## Verification

After editing:

- search the active repository files for remaining `LICENSE.txt` references,
  allowing only the documented historical plan reference;
- verify every relative README link resolves to an existing file;
- verify installation commands and artifact names against the current
  installer and Flatpak packaging files;
- confirm the two preserved images remain in the README;
- review the rendered Markdown structure and run the relevant lightweight test
  or validation commands if documentation-adjacent packaging files require it.
