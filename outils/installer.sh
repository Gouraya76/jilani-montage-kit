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
  # yt-dlp à jour + curl-cffi : sans ce module, TikTok refuse le téléchargement (« no impersonate target is available »).
  PAQUETS=(faster-whisper "yt-dlp[default,curl-cffi]" opencv-python-headless numpy pillow onnxruntime)
  python3 -m pip install -q -U --break-system-packages "${PAQUETS[@]}" 2>/dev/null || python3 -m pip install -q -U "${PAQUETS[@]}"
  # Jeton anti-robot YouTube (bgutil-ytdlp-pot-provider, open source) : sans lui, YouTube refuse souvent les serveurs.
  # Facultatif : s'il échoue, le montage marche quand même (sans YouTube).
  (
    python3 -m pip install -q -U --break-system-packages bgutil-ytdlp-pot-provider 2>/dev/null || python3 -m pip install -q -U bgutil-ytdlp-pot-provider
    VER=$(python3 -m pip show bgutil-ytdlp-pot-provider | sed -n 's/^Version: //p')
    rm -rf /opt/bgutil && git clone -q --depth 1 --branch "$VER" https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil
    cd /opt/bgutil/server && npm ci --silent && npx tsc && test -f build/generate_once.js && echo "bgutil OK $VER"
  ) || echo "bgutil : installation impossible (YouTube restera souvent bloqué)"
  touch /tmp/jm-installation.ok
) > /tmp/jm-installation.log 2>&1 || touch /tmp/jm-installation.erreur
