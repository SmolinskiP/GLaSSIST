# Flatpak Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship GLaSSIST as a `.flatpak` bundle built in CI and attached to GitHub Releases (Flathub submission is a later, separate effort).

**Architecture:** A Flatpak manifest under `packaging/flatpak/` bundles the Python app on the GNOME runtime (which provides GTK3/WebKit2GTK for pywebview). Python deps come from a generated pip-module JSON; native gaps (PortAudio, libmpv for Flet) are built as manifest modules. Small Linux-only code changes route `.env` and user sound files through XDG dirs when `FLATPAK_ID` is set. All Flatpak builds run in GitHub Actions — the dev machine is Windows.

**Tech Stack:** flatpak-builder, GNOME runtime, flatpak-pip-generator, GitHub Actions, pytest.

## Global Constraints

- App ID is exactly `io.github.SmolinskiP.GLaSSIST` everywhere (manifest, desktop file, metainfo, icon name).
- License: MIT (from `LICENSE.txt`).
- Runtime: `org.gnome.Platform//48` — **contingent on Task 1 spike outcome**.
- No behavior change outside the sandbox: every new code path is guarded by `FLATPAK_ID` env detection.
- Windows-only pip packages excluded from the Linux build: `pythonnet`, `clr_loader`, `pyreadline3`.
- Sandbox permissions (finish-args) are exactly: `--share=network`, `--share=ipc`, `--socket=x11`, `--socket=fallback-x11`, `--socket=wayland`, `--socket=pulseaudio`, `--device=dri`, `--talk-name=org.kde.StatusNotifierWatcher`.
- Dev machine is Windows: `flatpak-builder` never runs locally. The iteration loop is: edit → `git push` → trigger workflow (GitHub UI → Actions → workflow → "Run workflow") → read logs.
- Out of scope: AppImage, Wayland GlobalShortcuts portal, autostart portal (v1 documents a manual `~/.config/autostart` entry), Flathub submission, Windows changes.

---

### Task 1: Spike — verify WebKit2GTK 4.1 in the GNOME runtime

This task gates everything else. pywebview's GTK backend needs GTK3 + WebKit2GTK 4.x
(see `platform_utils.py:20-39`); newer GNOME runtimes are GTK4/WebKitGTK-6.0-first.

**Files:**
- Create: `.github/workflows/flatpak-spike.yml`
- Create: `packaging/flatpak/SPIKE-RESULTS.md`

**Interfaces:**
- Produces: the runtime decision consumed by Task 5 (manifest `runtime-version`, and whether a `webkitgtk` module must be added).

- [ ] **Step 1: Write the spike workflow**

```yaml
# .github/workflows/flatpak-spike.yml
name: Flatpak spike - runtime WebKit check
on: workflow_dispatch

jobs:
  check-runtime:
    runs-on: ubuntu-latest
    steps:
      - name: Install flatpak
        run: sudo apt-get update && sudo apt-get install -y flatpak
      - name: Add flathub remote
        run: flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
      - name: Install GNOME runtime
        run: flatpak install --user -y flathub org.gnome.Platform//48
      - name: Check GTK3 + WebKit2GTK availability
        run: |
          flatpak run --command=sh org.gnome.Platform//48 -c '
            echo "=== webkit libs ==="
            ls /usr/lib/x86_64-linux-gnu/ | grep -i webkit || echo "(none)"
            echo "=== girepository typelibs ==="
            ls /usr/lib/x86_64-linux-gnu/girepository-1.0/ | grep -i -E "webkit|^Gtk" || echo "(none)"
            echo "=== python checks ==="
            python3 --version
            python3 -c "import gi; gi.require_version(\"Gtk\",\"3.0\"); print(\"GTK3: OK\")" || echo "GTK3: MISSING"
            python3 -c "import gi; gi.require_version(\"WebKit2\",\"4.1\"); print(\"WebKit2-4.1: OK\")" || echo "WebKit2-4.1: MISSING"
          '
```

- [ ] **Step 2: Commit and push**

```bash
git add .github/workflows/flatpak-spike.yml
git commit -m "ci: add flatpak runtime spike workflow"
git push
```

- [ ] **Step 3: Run the workflow and read the log**

Trigger: GitHub → Actions → "Flatpak spike - runtime WebKit check" → Run workflow.
Expected log output: the `python checks` section prints `GTK3: OK` / `GTK3: MISSING`
and `WebKit2-4.1: OK` / `WebKit2-4.1: MISSING`.

If `org.gnome.Platform//48` fails to install, retry the workflow after changing the
version to `47` in both places, and use that version everywhere `48` appears in this plan.

- [ ] **Step 4: Record the decision**

Write `packaging/flatpak/SPIKE-RESULTS.md` with the actual log lines and one of:

| Result | Decision |
|---|---|
| GTK3 OK + WebKit2-4.1 OK | Proceed with `org.gnome.Platform//48`, no extra module. |
| GTK3 OK, WebKit2-4.1 MISSING | Add a `webkitgtk-4.1` module to the Task 5 manifest (build from source: https://webkitgtk.org/releases/ — long build, note it). |
| GTK3 MISSING | STOP. Discuss with the project owner: options are pywebview Qt backend (add PyQt to requirements) or an older runtime. Do not proceed to Task 5 without a decision. |

```bash
git add packaging/flatpak/SPIKE-RESULTS.md
git commit -m "docs: record flatpak runtime spike results"
git push
```

---

### Task 2: XDG config path for `.env` under Flatpak

Inside the sandbox `/app` is read-only, so the current behavior — `.env` next to the
source files (`flet_settings.py:1998-2012`) and `load_dotenv()` from CWD (`utils.py:16`)
— cannot work. Route both through one helper.

**Files:**
- Modify: `platform_utils.py` (add functions at the end)
- Modify: `utils.py:16` (dotenv load)
- Modify: `flet_settings.py` (`_save_env_file`, top imports)
- Test: `tests/test_platform_utils.py` (new file)

**Interfaces:**
- Produces: `platform_utils.is_flatpak() -> bool`, `platform_utils.get_config_dir() -> Path`,
  `platform_utils.get_env_file_path() -> Path`. Task 3 consumes `is_flatpak()`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_platform_utils.py
"""Tests for platform_utils module."""
import os
from pathlib import Path
from unittest.mock import patch

import platform_utils


class TestFlatpakPaths:
    def test_is_flatpak_false_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            assert platform_utils.is_flatpak() is False

    def test_is_flatpak_true_when_id_set(self):
        with patch.dict(os.environ, {"FLATPAK_ID": "io.github.SmolinskiP.GLaSSIST"}):
            assert platform_utils.is_flatpak() is True

    def test_config_dir_outside_flatpak_is_app_dir(self):
        with patch.dict(os.environ, {}, clear=True):
            expected = Path(platform_utils.__file__).parent
            assert platform_utils.get_config_dir() == expected

    def test_config_dir_in_flatpak_uses_xdg(self, tmp_path):
        env = {"FLATPAK_ID": "x", "XDG_CONFIG_HOME": str(tmp_path)}
        with patch.dict(os.environ, env):
            result = platform_utils.get_config_dir()
            assert result == tmp_path / "glasssist"
            assert result.is_dir()

    def test_env_file_path_in_flatpak(self, tmp_path):
        env = {"FLATPAK_ID": "x", "XDG_CONFIG_HOME": str(tmp_path)}
        with patch.dict(os.environ, env):
            expected = tmp_path / "glasssist" / ".env"
            assert platform_utils.get_env_file_path() == expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_platform_utils.py -v`
Expected: FAIL with `AttributeError: module 'platform_utils' has no attribute 'is_flatpak'`

- [ ] **Step 3: Implement the helpers**

Append to `platform_utils.py`:

```python
def is_flatpak():
    """Return True when running inside a Flatpak sandbox."""
    return bool(os.environ.get('FLATPAK_ID'))

def get_config_dir():
    """
    Directory holding the .env file. App directory normally;
    XDG config dir inside Flatpak (where /app is read-only).
    """
    if is_flatpak():
        base = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        path = Path(base) / 'glasssist'
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path(__file__).parent

def get_env_file_path():
    """Full path to the .env file."""
    return get_config_dir() / '.env'
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_platform_utils.py -v`
Expected: 5 passed

- [ ] **Step 5: Route dotenv loading through the helper**

In `utils.py`, replace line 16 `load_dotenv()` with:

```python
import platform_utils
load_dotenv(platform_utils.get_env_file_path())
```

(`platform_utils` imports only stdlib, so no circular import.)

- [ ] **Step 6: Route settings save through the helper**

In `flet_settings.py`, add `import platform_utils` next to the existing `import utils`,
and in `_save_env_file` replace the whole `possible_paths` block:

```python
            # Find .env file location
            possible_paths = [
                os.path.join(os.path.dirname(__file__), '.env'),
                os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),
                '.env'
            ]
            
            env_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    env_path = path
                    break
                    
            if not env_path:
                env_path = possible_paths[0]
```

with:

```python
            env_path = str(platform_utils.get_env_file_path())
```

- [ ] **Step 7: Run the full utils/settings-adjacent tests**

Run: `python -m pytest tests/test_platform_utils.py tests/test_utils.py -v`
Expected: all `test_platform_utils` pass; `test_utils` shows the same 7 pre-existing
failures as before this task (stale pygame tests) and no new ones.

- [ ] **Step 8: Commit**

```bash
git add platform_utils.py utils.py flet_settings.py tests/test_platform_utils.py
git commit -m "feat: resolve .env via XDG config dir inside Flatpak"
```

---

### Task 3: User sound directory under Flatpak

Bundled sounds live in read-only `/app`; users must be able to drop custom files
somewhere writable. Inside Flatpak that is `$XDG_DATA_HOME/glasssist/sound`.

**Files:**
- Modify: `platform_utils.py` (one function)
- Modify: `utils.py` (`get_sound_file_path`)
- Modify: `flet_settings.py` (`_list_sound_files`)
- Test: `tests/test_platform_utils.py`, `tests/test_utils.py`

**Interfaces:**
- Consumes: `platform_utils.is_flatpak()` from Task 2.
- Produces: `platform_utils.get_user_sound_dir() -> Path | None` (None outside Flatpak).
  `utils.get_sound_file_path(sound_name)` now prefers the user dir when the file exists there.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_platform_utils.py` inside `TestFlatpakPaths`:

```python
    def test_user_sound_dir_none_outside_flatpak(self):
        with patch.dict(os.environ, {}, clear=True):
            assert platform_utils.get_user_sound_dir() is None

    def test_user_sound_dir_in_flatpak(self, tmp_path):
        env = {"FLATPAK_ID": "x", "XDG_DATA_HOME": str(tmp_path)}
        with patch.dict(os.environ, env):
            result = platform_utils.get_user_sound_dir()
            assert result == tmp_path / "glasssist" / "sound"
            assert result.is_dir()
```

Append to `tests/test_utils.py` inside `TestSoundConfiguration`:

```python
    def test_get_sound_file_path_prefers_user_dir(self, tmp_path):
        """Inside Flatpak, a file in the XDG user sound dir wins over bundled."""
        user_sound_dir = tmp_path / "glasssist" / "sound"
        user_sound_dir.mkdir(parents=True)
        user_file = user_sound_dir / "custom.wav"
        user_file.write_bytes(b"RIFF")

        env = {"FLATPAK_ID": "x", "XDG_DATA_HOME": str(tmp_path),
               "HA_SOUND_ACTIVATION": "custom.wav"}
        with patch.dict(os.environ, env):
            assert utils.get_sound_file_path("activation") == str(user_file)

    def test_get_sound_file_path_falls_back_to_bundled(self, tmp_path):
        """Inside Flatpak, a file absent from the user dir resolves to bundled dir."""
        env = {"FLATPAK_ID": "x", "XDG_DATA_HOME": str(tmp_path)}
        with patch.dict(os.environ, env):
            path = utils.get_sound_file_path("activation")
            assert path == os.path.join(utils.get_sound_dir(), "activation.wav")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_platform_utils.py tests/test_utils.py -k "user_dir or falls_back_to_bundled or user_sound_dir" -v`
Expected: 4 FAIL (`AttributeError: ... 'get_user_sound_dir'`)

- [ ] **Step 3: Implement**

Append to `platform_utils.py`:

```python
def get_user_sound_dir():
    """
    Writable directory for user-provided sound files inside Flatpak.
    Returns None outside the sandbox (users edit the app's sound/ folder directly).
    """
    if not is_flatpak():
        return None
    base = os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
    path = Path(base) / 'glasssist' / 'sound'
    path.mkdir(parents=True, exist_ok=True)
    return path
```

In `utils.py`, replace the body of `get_sound_file_path` (keep the docstring):

```python
    default = DEFAULT_SOUND_FILES.get(sound_name, f"{sound_name}.wav")
    filename = get_env(f'HA_SOUND_{sound_name.upper()}', default)
    if not filename:
        filename = default
    user_dir = platform_utils.get_user_sound_dir()
    if user_dir is not None:
        user_path = os.path.join(str(user_dir), filename)
        if os.path.exists(user_path):
            return user_path
    return os.path.join(get_sound_dir(), filename)
```

In `flet_settings.py`, replace `_list_sound_files`:

```python
    def _list_sound_files(self):
        """List audio files from the bundled and (in Flatpak) user 'sound' folders"""
        files = set()
        dirs = [utils.get_sound_dir()]
        user_dir = platform_utils.get_user_sound_dir()
        if user_dir is not None:
            dirs.append(str(user_dir))
        for d in dirs:
            try:
                files.update(
                    f for f in os.listdir(d)
                    if f.lower().endswith(('.wav', '.mp3', '.flac', '.ogg'))
                )
            except OSError:
                pass
        return sorted(files)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_platform_utils.py tests/test_utils.py -v`
Expected: all new tests pass; only the 7 pre-existing stale failures remain.

- [ ] **Step 5: Commit**

```bash
git add platform_utils.py utils.py flet_settings.py tests/test_platform_utils.py tests/test_utils.py
git commit -m "feat: support user sound dir via XDG data dir inside Flatpak"
```

---

### Task 4: Desktop file, AppStream metainfo, launcher script

**Files:**
- Create: `packaging/flatpak/io.github.SmolinskiP.GLaSSIST.desktop`
- Create: `packaging/flatpak/io.github.SmolinskiP.GLaSSIST.metainfo.xml`
- Create: `packaging/flatpak/glasssist.sh`

**Interfaces:**
- Produces: the three files installed by the Task 5 manifest at the exact paths above.

- [ ] **Step 1: Desktop file**

```ini
# packaging/flatpak/io.github.SmolinskiP.GLaSSIST.desktop
[Desktop Entry]
Name=GLaSSIST
Comment=Desktop voice assistant for Home Assistant
Exec=glasssist
Icon=io.github.SmolinskiP.GLaSSIST
Terminal=false
Type=Application
Categories=Utility;AudioVideo;
Keywords=home assistant;voice;assistant;wake word;
StartupNotify=false
```

- [ ] **Step 2: AppStream metainfo**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- packaging/flatpak/io.github.SmolinskiP.GLaSSIST.metainfo.xml -->
<component type="desktop-application">
  <id>io.github.SmolinskiP.GLaSSIST</id>
  <metadata_license>CC0-1.0</metadata_license>
  <project_license>MIT</project_license>
  <name>GLaSSIST</name>
  <summary>Desktop voice assistant for Home Assistant</summary>
  <description>
    <p>
      GLaSSIST is a desktop voice assistant that connects to Home Assistant.
      It supports wake word activation, voice commands with visual feedback,
      TTS responses, and an ESPHome satellite mode with timers and
      conversation follow-up.
    </p>
  </description>
  <launchable type="desktop-id">io.github.SmolinskiP.GLaSSIST.desktop</launchable>
  <url type="homepage">https://github.com/SmolinskiP/GLaSSIST</url>
  <url type="bugtracker">https://github.com/SmolinskiP/GLaSSIST/issues</url>
  <developer id="io.github.smolinskip">
    <name>Patryk Smoliński</name>
  </developer>
  <content_rating type="oars-1.1"/>
  <releases>
    <release version="3.1.0" date="2026-07-15"/>
  </releases>
</component>
```

- [ ] **Step 3: Launcher script**

```sh
#!/bin/sh
# packaging/flatpak/glasssist.sh
cd /app/share/glasssist
exec python3 main.py "$@"
```

- [ ] **Step 4: Check the icon size** (manifest installs it under a sized dir)

Run in PowerShell:
```powershell
Add-Type -AssemblyName System.Drawing; $i=[System.Drawing.Image]::FromFile("e:\GLaSSIST\img\icon.png"); "$($i.Width)x$($i.Height)"; $i.Dispose()
```
Note the output (e.g. `256x256`). If it is not square or smaller than 128, flag to the
project owner. Use the actual size in the Task 5 manifest icon install path.

- [ ] **Step 5: Commit**

```bash
git add packaging/flatpak/
git commit -m "feat: add flatpak desktop entry, metainfo and launcher"
```

---

### Task 5: Linux requirements file, pip modules generation, and the manifest

**Files:**
- Create: `packaging/flatpak/requirements-linux.txt`
- Create: `.github/workflows/flatpak-pipgen.yml`
- Create: `packaging/flatpak/python3-modules.json` (generated by the workflow, committed by you)
- Create: `packaging/flatpak/io.github.SmolinskiP.GLaSSIST.yml`

**Interfaces:**
- Consumes: Task 1 runtime decision, Task 4 files.
- Produces: a manifest the Task 6 build workflow consumes at
  `packaging/flatpak/io.github.SmolinskiP.GLaSSIST.yml`.

- [ ] **Step 1: Linux requirements**

Copy `requirements.txt` to `packaging/flatpak/requirements-linux.txt` and delete these
lines: `clr_loader==0.2.7.post0`, `pyreadline3==3.5.4`, `pythonnet==3.0.5`. Keep the
`sys_platform == "linux"` markers as-is. Remove the commented `#speexdsp` line.

- [ ] **Step 2: Pip generator workflow**

```yaml
# .github/workflows/flatpak-pipgen.yml
name: Flatpak pip modules generation
on: workflow_dispatch

jobs:
  pipgen:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install requirements-parser
        run: pip install requirements-parser
      - name: Fetch flatpak-pip-generator
        run: curl -Lo flatpak-pip-generator https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/master/pip/flatpak-pip-generator
      - name: Generate module JSON
        run: python3 flatpak-pip-generator --requirements-file=packaging/flatpak/requirements-linux.txt --output python3-modules
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: python3-modules
          path: python3-modules.json
```

- [ ] **Step 3: Commit, push, run, download**

```bash
git add packaging/flatpak/requirements-linux.txt .github/workflows/flatpak-pipgen.yml
git commit -m "ci: add flatpak pip module generation workflow"
git push
```

Trigger the workflow in the GitHub UI, download the `python3-modules` artifact, and save
the JSON as `packaging/flatpak/python3-modules.json`. Commit it:

```bash
git add packaging/flatpak/python3-modules.json
git commit -m "feat: add generated flatpak pip modules"
```

- [ ] **Step 4: Compute the PortAudio source checksum**

Run in PowerShell:
```powershell
Invoke-WebRequest -Uri "https://files.portaudio.com/archives/pa_stable_v190700_20210406.tgz" -OutFile "$env:TEMP\pa.tgz"; (Get-FileHash "$env:TEMP\pa.tgz" -Algorithm SHA256).Hash.ToLower()
```
Paste the output into the `sha256:` field of the `portaudio` module in Step 6.

- [ ] **Step 5: Compute the mpv and libass source checksums**

mpv provides libmpv for Flet. Check https://github.com/mpv-player/mpv/releases and
https://github.com/libass/libass/releases for the latest stable tags, then:

```powershell
Invoke-WebRequest -Uri "https://github.com/libass/libass/releases/download/0.17.3/libass-0.17.3.tar.xz" -OutFile "$env:TEMP\libass.tar.xz"; (Get-FileHash "$env:TEMP\libass.tar.xz" -Algorithm SHA256).Hash.ToLower()
Invoke-WebRequest -Uri "https://github.com/mpv-player/mpv/archive/refs/tags/v0.38.0.tar.gz" -OutFile "$env:TEMP\mpv.tar.gz"; (Get-FileHash "$env:TEMP\mpv.tar.gz" -Algorithm SHA256).Hash.ToLower()
```
Adjust the version numbers to the ones you selected; paste the hashes into Step 6.

- [ ] **Step 6: Write the manifest**

```yaml
# packaging/flatpak/io.github.SmolinskiP.GLaSSIST.yml
app-id: io.github.SmolinskiP.GLaSSIST
runtime: org.gnome.Platform
runtime-version: '48'
sdk: org.gnome.Sdk
command: glasssist

finish-args:
  - --share=network
  - --share=ipc
  - --socket=x11
  - --socket=fallback-x11
  - --socket=wayland
  - --socket=pulseaudio
  - --device=dri
  - --talk-name=org.kde.StatusNotifierWatcher

add-extensions:
  org.freedesktop.Platform.ffmpeg-full:
    version: '24.08'
    directory: lib/ffmpeg
    add-ld-path: .

cleanup-commands:
  - mkdir -p /app/lib/ffmpeg

modules:
  - name: portaudio
    buildsystem: autotools
    sources:
      - type: archive
        url: https://files.portaudio.com/archives/pa_stable_v190700_20210406.tgz
        sha256: PASTE_FROM_TASK5_STEP4

  - name: libass
    buildsystem: autotools
    sources:
      - type: archive
        url: https://github.com/libass/libass/releases/download/0.17.3/libass-0.17.3.tar.xz
        sha256: PASTE_FROM_TASK5_STEP5

  - name: libmpv
    buildsystem: meson
    config-opts:
      - -Dlibmpv=true
      - -Dcplayer=false
      - -Dmanpage-build=disabled
    sources:
      - type: archive
        url: https://github.com/mpv-player/mpv/archive/refs/tags/v0.38.0.tar.gz
        sha256: PASTE_FROM_TASK5_STEP5

  - shared-modules/libappindicator/libappindicator-gtk3-12.10.json

  - python3-modules.json

  - name: glasssist
    buildsystem: simple
    build-commands:
      - mkdir -p /app/share/glasssist
      - cp *.py /app/share/glasssist/
      - cp -r frontend sound models img /app/share/glasssist/
      - cp .env.example /app/share/glasssist/
      - install -Dm755 packaging/flatpak/glasssist.sh /app/bin/glasssist
      - install -Dm644 packaging/flatpak/io.github.SmolinskiP.GLaSSIST.desktop /app/share/applications/io.github.SmolinskiP.GLaSSIST.desktop
      - install -Dm644 packaging/flatpak/io.github.SmolinskiP.GLaSSIST.metainfo.xml /app/share/metainfo/io.github.SmolinskiP.GLaSSIST.metainfo.xml
      - install -Dm644 img/icon.png /app/share/icons/hicolor/256x256/apps/io.github.SmolinskiP.GLaSSIST.png
    sources:
      - type: dir
        path: ../..
```

The `shared-modules` reference requires Flathub's shared-modules repo as a git
submodule (this is the standard Flathub pattern for AppIndicator, which pystray
needs for the tray icon):

```bash
git submodule add https://github.com/flathub/shared-modules.git packaging/flatpak/shared-modules
```

and the module line above is then relative to the manifest:
`shared-modules/libappindicator/libappindicator-gtk3-12.10.json` (verify the exact
JSON filename inside the submodule — it has changed between revisions).

Notes for the implementer:
- Replace the three `PASTE_FROM_...` values with the hashes you computed.
- Replace `256x256` in the icon install path with the actual size from Task 4 Step 4.
- If the Task 1 spike said WebKit2-4.1 is missing, add a `webkitgtk` module (source:
  https://webkitgtk.org/releases/, cmake buildsystem, `-DPORT=GTK -DUSE_GTK4=OFF`)
  before `python3-modules.json` — and expect a multi-hour CI build.
- mpv 0.38 needs libplacebo; if the CI build fails on a missing `libplacebo`, add a
  module for it (meson, source https://code.videolan.org/videolan/libplacebo) before
  `libmpv`. This is expected iteration, not a plan failure.

- [ ] **Step 7: Commit**

```bash
git add packaging/flatpak/io.github.SmolinskiP.GLaSSIST.yml
git commit -m "feat: add flatpak manifest"
git push
```

---

### Task 6: CI build workflow producing the .flatpak bundle

**Files:**
- Create: `.github/workflows/flatpak.yml`

**Interfaces:**
- Consumes: the Task 5 manifest path.
- Produces: `GLaSSIST.flatpak` artifact on every manual run; attached to the GitHub
  Release on `v*` tags.

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/flatpak.yml
name: Flatpak build
on:
  workflow_dispatch:
  push:
    tags: ['v*']

jobs:
  flatpak:
    runs-on: ubuntu-latest
    container:
      image: ghcr.io/flathub-infra/flatpak-github-actions:gnome-48
      options: --privileged
    steps:
      - uses: actions/checkout@v4
      - uses: flatpak/flatpak-github-actions/flatpak-builder@v6
        with:
          bundle: GLaSSIST.flatpak
          manifest-path: packaging/flatpak/io.github.SmolinskiP.GLaSSIST.yml
          cache-key: flatpak-builder-${{ hashFiles('packaging/flatpak/**') }}
      - name: Attach bundle to release
        if: startsWith(github.ref, 'refs/tags/')
        uses: softprops/action-gh-release@v2
        with:
          files: GLaSSIST.flatpak
```

If the container image tag `gnome-48` does not exist, check
https://github.com/flatpak/flatpak-github-actions#readme for the current image
naming and adjust (this action has renamed images/orgs before).

- [ ] **Step 2: Commit, push, run**

```bash
git add .github/workflows/flatpak.yml
git commit -m "ci: add flatpak bundle build workflow"
git push
```

Trigger via GitHub UI. **Expect iteration here** — native module build failures
(libplacebo, meson options) are resolved by editing the manifest and re-running.
Done when the workflow uploads a `GLaSSIST.flatpak` artifact.

- [ ] **Step 3: Smoke-test the bundle on a Linux machine/VM**

On any Linux box with flatpak (X11 session for full coverage):

```bash
flatpak install --user GLaSSIST.flatpak
flatpak run io.github.SmolinskiP.GLaSSIST
```

Checklist (record results in the PR description):
- [ ] App starts, tray icon appears
- [ ] Settings dialog opens and saving writes `~/.var/app/io.github.SmolinskiP.GLaSSIST/config/glasssist/.env`
- [ ] Microphone capture works (listening state reacts to speech)
- [ ] TTS playback audible
- [ ] Animation window renders (WebKit)
- [ ] Satellite mode: port 6053 reachable from HA, mDNS discovery works
- [ ] Wake word detection triggers with bundled models
- [ ] On Wayland: everything above except the global hotkey

---

### Task 7: Documentation and issue #43 follow-up

**Files:**
- Modify: `README.md` (Linux install section)
- Modify: `docs/superpowers/specs/2026-07-15-flatpak-packaging-design.md` (autostart note)

**Interfaces:**
- Consumes: working bundle from Task 6.

- [ ] **Step 1: README section**

Add under the Linux installation section of `README.md`:

```markdown
### Flatpak (recommended for Linux)

Download `GLaSSIST.flatpak` from the [latest release](https://github.com/SmolinskiP/GLaSSIST/releases), then:

    flatpak install --user GLaSSIST.flatpak
    flatpak run io.github.SmolinskiP.GLaSSIST

Notes:
- Configuration lives in `~/.var/app/io.github.SmolinskiP.GLaSSIST/config/glasssist/.env`
- Custom sounds go to `~/.var/app/io.github.SmolinskiP.GLaSSIST/data/glasssist/sound/`
- The global hotkey works on X11 only; on Wayland use wake word activation
- Autostart: create `~/.config/autostart/io.github.SmolinskiP.GLaSSIST.desktop` with
  `Exec=flatpak run io.github.SmolinskiP.GLaSSIST`
```

- [ ] **Step 2: Amend the spec** — in the design doc, change the autostart bullet under
"Code adjustments" to: "Autostart: v1 documents a manual `~/.config/autostart` entry;
Background portal integration is a follow-up issue." (matches what was built).

- [ ] **Step 3: Commit**

```bash
git add README.md docs/superpowers/specs/2026-07-15-flatpak-packaging-design.md
git commit -m "docs: flatpak installation instructions"
git push
```

- [ ] **Step 4: Reply on issue #43** (owner posts; draft below)

> GLaSSIST is now available as a Flatpak bundle — grab `GLaSSIST.flatpak` from the
> latest release and `flatpak install --user GLaSSIST.flatpak`. Config lives under
> `~/.var/app/io.github.SmolinskiP.GLaSSIST/`. Known limitation: the global hotkey
> works on X11 only (Wayland needs the GlobalShortcuts portal — tracked separately);
> wake word activation works everywhere. Flathub submission is planned as a next step.
> Feedback very welcome!
