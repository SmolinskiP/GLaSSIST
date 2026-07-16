#!/bin/sh
# WebKitGTK's accelerated compositing is broken on the NVIDIA proprietary
# driver: GBM buffers fail and canvas frames stop being presented, freezing
# the animation. Software compositing renders it correctly.
if grep -q '^nvidia ' /proc/modules 2>/dev/null; then
    export WEBKIT_DISABLE_COMPOSITING_MODE=1
fi
cd /app/share/glasssist
exec python3 main.py "$@"
