#!/bin/sh
# Bambu Studio は CLI モードでも X11 に接続しようとするため、
# 仮想ディスプレイを立ててからコマンドを渡す。
set -e

Xvfb :99 -screen 0 1024x768x24 > /dev/null 2>&1 &
XVFB_PID=$!
trap 'kill "$XVFB_PID" 2>/dev/null || true' EXIT

# ディスプレイが上がるまで待つ
for _ in $(seq 1 50); do
    if [ -e /tmp/.X11-unix/X99 ]; then break; fi
    sleep 0.1
done

exec bambu-studio "$@"
