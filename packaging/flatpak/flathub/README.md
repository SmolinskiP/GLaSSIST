# Flathub submission

This directory holds the Flathub variant of the manifest. It builds GLaSSIST
from a tagged GitHub release instead of the local working copy — that is the
only intended difference from `../io.github.SmolinskiP.GLaSSIST.yml`. When the
main manifest changes, port the change here too.

## Submitting (one-time)

1. Tag and publish the release the manifest points at (`tag:` in the
   `glasssist` module), and make sure `metainfo.xml` in that tag contains the
   matching `<release>` entry. Validate it first:
   `flatpak run org.freedesktop.appstream.cli validate packaging/flatpak/io.github.SmolinskiP.GLaSSIST.metainfo.xml`
2. Fork `https://github.com/flathub/flathub`, branch off `new-pr`.
3. Copy into the fork root: this manifest + `../python3-modules.json` +
   `flathub.json` (restricts the build to x86_64 — the python wheels are
   generated per-arch and flet-desktop has no aarch64 wheels anyway).
4. Open a PR against the `new-pr` branch of `flathub/flathub`. The bot builds
   it; a reviewer will ask about permissions (network, pulseaudio, dri and the
   StatusNotifierWatcher tray are all justified for a voice assistant).
5. After the merge a `flathub/io.github.SmolinskiP.GLaSSIST` repo is created
   with write access for you. Updates happen via PRs to that repo — the
   `x-checker-data` block lets flathubbot open version-bump PRs automatically
   when a new tag appears on GitHub.

## Per release

Bump `tag:` in the `glasssist` module of the Flathub repo copy (or merge the
bot's PR). Nothing else should need to change unless dependencies changed —
then also copy the regenerated `python3-modules.json`.
