# README and License Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the oversized and partly stale README with a concise user/developer guide and consolidate the duplicated MIT license into `LICENSE`.

**Architecture:** Keep `README.md` as the project landing page and route detailed configuration to existing focused documents. Preserve the existing banner and application screenshot, keep packaging behavior unchanged, and update Windows installer references before deleting the duplicate license file.

**Tech Stack:** GitHub-flavored Markdown, Python 3, Inno Setup, Flatpak packaging, PowerShell verification commands.

## Global Constraints

- Preserve the existing generated GLaSSIST banner and application image without replacing their URLs.
- Target approximately 180–230 README lines, prioritizing clarity over an exact line count.
- Present installation in this order: Windows installer, Linux Flatpak, Linux install script, Windows/Linux from source.
- Separate the landing page into **For users** and **For developers**.
- Link to `.env.example` and `INTERACTIVE_PROMPTS_SETUP.md` instead of duplicating their detailed content.
- Remove Troubleshooting, FAQ and Star History.
- Keep `LICENSE` as the only canonical MIT license file.
- Do not modify the historical plan reference to `LICENSE.txt` in `docs/superpowers/plans/2026-07-15-flatpak-packaging.md`.

---

### Task 1: Rewrite the project landing page

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: current installer artifact names, Flatpak application ID, `.env.example`, `INTERACTIVE_PROMPTS_SETUP.md`, and the verified application behavior documented in `docs/superpowers/specs/2026-07-20-readme-license-cleanup-design.md`.
- Produces: a concise repository landing page for users and developers with valid relative documentation links.

- [ ] **Step 1: Capture the visual assets that must remain**

Run:

```powershell
rg -n '<img|!\[' README.md
```

Expected: the capsule-render banner on line 1, the centered application image near the feature list, and the broken Star History image near the end.

- [ ] **Step 2: Replace README content with the approved structure**

Retain the exact banner and centered application image markup. Write the remaining content in clear English with these exact top-level sections and responsibilities:

```markdown
# [existing capsule-render banner]

[Two short paragraphs: GLaSSIST is a Windows/Linux desktop voice satellite for Home Assistant; it captures microphone audio, sends it through Home Assistant Assist, plays responses, and provides visual feedback. Explain that ESPHome Satellite is recommended for LAN/full features, while WebSocket is the legacy remote-capable/token mode.]

## 🚀 Key Features

- Home Assistant Assist voice pipeline with local microphone and speaker playback
- ESPHome Satellite mode with timers and conversation follow-up
- Wake-word, configurable hotkey and system-tray activation
- WebRTC voice activity detection and selectable audio devices
- Three.js visual overlay with optional response text
- Configurable pipelines, feedback sounds and media-player volume management

[existing centered application image]

## For users

### Windows installer
[requirements and latest-release GLaSSIST-Setup.exe link]

### Linux — Flatpak
[latest-release download, flatpak install/run commands, config/custom-sound paths, Wayland hotkey note]

### Linux — install script
[supported distribution families, one-line download/run command, uninstall link/command]

### First-time setup
[ESPHome Satellite recommended steps; WebSocket HA_HOST/HA_TOKEN alternative; point to Settings]

### Using GLaSSIST
[wake word, hotkey, tray activation, settings access]

### Interactive prompts
[one paragraph and relative link to INTERACTIVE_PROMPTS_SETUP.md; mention unauthenticated LAN HTTP endpoint]

## For developers

### Requirements and source installation
[Python and OS requirements, clone, venv, requirements install, copy .env.example, run commands]

### Configuration
[link to .env.example; explain settings UI and --settings]

### Tests
[install test requirements and primary test runner commands]

### Project structure
[one compact list covering main.py, client.py, satellite_protocol.py, audio.py/vad.py/wake_word_detector.py, animation_server.py/frontend, flet_settings.py]

## 📄 License
[link to LICENSE and identify MIT]

## ☕ Support
[retain Buy Me a Coffee link]
```

Do not retain exhaustive environment-variable tables, copied Interactive Prompts payloads, old fixed-bug notes, FAQ, Troubleshooting, Star History, or profanity. Keep the README focused on current behavior and direct users to detailed documents.

- [ ] **Step 3: Check the rewritten structure and size**

Run:

```powershell
(Get-Content README.md).Count
rg -n '^#{1,3} ' README.md
rg -n '<img|!\[' README.md
```

Expected: approximately 180–230 lines; headings follow the approved user/developer structure; the banner and application image remain; no Star History image remains.

- [ ] **Step 4: Verify the documentation links and removed sections**

Run:

```powershell
Test-Path .env.example
Test-Path INTERACTIVE_PROMPTS_SETUP.md
Test-Path LICENSE
rg -n 'Troubleshooting|FAQ|Star History|api\.star-history\.com' README.md
```

Expected: all three `Test-Path` calls output `True`; `rg` returns no matches.

- [ ] **Step 5: Review the README diff**

Run:

```powershell
git diff --check -- README.md
git diff --stat -- README.md
git diff -- README.md
```

Expected: no whitespace errors; the diff preserves the two approved visuals and replaces stale/repeated material with the approved structure.

### Task 2: Consolidate the MIT license

**Files:**
- Modify: `setup.iss`
- Modify: `setup_debug.iss`
- Delete: `LICENSE.txt`
- Preserve: `LICENSE`

**Interfaces:**
- Consumes: the canonical MIT text in `LICENSE`.
- Produces: both Windows installer variants display `LICENSE`, with no active build dependency on `LICENSE.txt`.

- [ ] **Step 1: Reconfirm that the two license files are identical**

Run:

```powershell
Get-FileHash LICENSE, LICENSE.txt -Algorithm SHA256
```

Expected: both files have the same SHA-256 hash.

- [ ] **Step 2: Update both Inno Setup scripts**

Change only the `LicenseFile` values:

```ini
LicenseFile=E:\GLaSSIST\LICENSE
```

in `setup.iss`, and:

```ini
LicenseFile=I:\GLaSSIST\LICENSE
```

in `setup_debug.iss`. Preserve each script's existing drive and absolute project path.

- [ ] **Step 3: Delete the duplicate file**

Delete `LICENSE.txt` after both installer references point to `LICENSE`.

- [ ] **Step 4: Verify license references**

Run:

```powershell
rg -n -i --hidden --glob '!.git/**' 'LICENSE\.txt|LicenseFile=' .
```

Expected: both `LicenseFile` entries point to `LICENSE`; the only remaining `LICENSE.txt` references are historical documentation in the 2026-07-15 Flatpak plan and this implementation plan.

- [ ] **Step 5: Review the license diff**

Run:

```powershell
git diff --check -- setup.iss setup_debug.iss LICENSE.txt
git diff -- setup.iss setup_debug.iss LICENSE.txt
```

Expected: two one-line reference changes and deletion of one byte-identical duplicate file; no change to `LICENSE`.

### Task 3: Final documentation and repository verification

**Files:**
- Verify: `README.md`
- Verify: `setup.iss`
- Verify: `setup_debug.iss`
- Verify: `LICENSE`

**Interfaces:**
- Consumes: completed README rewrite and installer reference changes.
- Produces: evidence that the landing page, links, images and canonical license are internally consistent.

- [ ] **Step 1: Verify tracked-file state and unrelated work**

Run:

```powershell
git status --short
```

Expected: only the intended README/license/installer/plan changes plus the user's pre-existing untracked `AGENTS.md`; do not stage or modify unrelated files.

- [ ] **Step 2: Verify README-relative targets and packaging identifiers**

Run:

```powershell
rg -n 'GLaSSIST-Setup\.exe|GLaSSIST\.flatpak|io\.github\.SmolinskiP\.GLaSSIST|\.env\.example|INTERACTIVE_PROMPTS_SETUP\.md|LICENSE' README.md
rg -n 'OutputBaseFilename=GLaSSIST-Setup' setup.iss setup_debug.iss
rg -n '<id>io\.github\.SmolinskiP\.GLaSSIST</id>' packaging/flatpak/io.github.SmolinskiP.GLaSSIST.metainfo.xml
```

Expected: README names match the Windows and Flatpak packaging sources, and all relative documentation targets use their real repository names.

- [ ] **Step 3: Run documentation-adjacent validation**

Run:

```powershell
python -m pytest tests/test_platform_utils.py tests/test_utils.py -v
```

Expected: tests pass. These tests cover configuration paths and platform behavior referenced by the new installation notes.

- [ ] **Step 4: Perform final diff checks**

Run:

```powershell
git diff --check
git diff --stat
git status --short
```

Expected: no whitespace errors; changes are limited to the approved documentation and license consolidation scope.

- [ ] **Step 5: Commit the implementation**

Run:

```powershell
git add README.md setup.iss setup_debug.iss LICENSE.txt docs/superpowers/plans/2026-07-20-readme-license-cleanup.md
git commit -m "docs: streamline README and consolidate license"
```

Expected: commit succeeds without staging the user's untracked `AGENTS.md`.
