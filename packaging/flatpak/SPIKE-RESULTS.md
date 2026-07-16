# Flatpak Runtime Spike Results

**Date:** 2026-07-16
**Workflow run:** https://github.com/SmolinskiP/GLaSSIST/actions/runs/29470997304
**Runtime tested:** `org.gnome.Platform//48`

## Results

| Check | Result |
|---|---|
| `gi.require_version('Gtk','3.0')` | **OK** (job `gtk3` green) |
| `gi.require_version('WebKit2','4.1')` | **OK** (job `webkit41` green) |

## Decision

Proceed with `org.gnome.Platform//48` as the manifest runtime. No extra WebKitGTK
module is needed — the runtime provides GTK3 + WebKit2GTK 4.1, which is exactly what
pywebview's GTK backend (see `platform_utils.py` dependency check) requires.
