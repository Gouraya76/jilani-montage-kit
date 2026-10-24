#!/bin/bash
# Installe les outils du montage (machine cloud de Claude Code). Lancé au démarrage de chaque session, en arrière-plan.
# Fin : /tmp/jm-installation.ok (ou /tmp/jm-installation.erreur). Journal : /tmp/jm-installation.log
[ -z "$CLAUDE_CODE_REMOTE" ] && exit 0
rm -f /tmp/jm-installation.ok /tmp/jm-installation.erreur
(
  set -e
  if ! command -v ffmpeg >/dev/null 2>&1 || ! fc-list 2>/dev/null | grep -qi "noto color emoji"; then
    export DEBIAN_FRONTEND=noninteractive
    (apt-get update -qq || sudo apt-get update -qq)
    (apt-get install -y -qq ffmpeg zip unzip fonts-noto-color-emoji nodejs || sudo apt-get install -y -qq ffmpeg zip unzip fonts-noto-color-emoji nodejs)
  fi
  python3 -m pip install -q --break-system-packages faster-whisper yt-dlp opencv-python-headless numpy pillow onnxruntime 2>/dev/null \
    || python3 -m pip install -q faster-whisper yt-dlp opencv-python-headless numpy pillow onnxruntime
  touch /tmp/jm-installation.ok
) > /tmp/jm-installation.log 2>&1 || touch /tmp/jm-installation.erreur
