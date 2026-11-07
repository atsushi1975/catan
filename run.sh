#!/usr/bin/env bash
# Start the Catan server.
#
# Usage:
#   ./run.sh              # normal: token-less hot-seat controls are OFF
#   ./run.sh --hotseat    # local hot-seat: enable ?debug=1 monitor controls
#   ./run.sh --codespace  # alias of --hotseat (dev only, NEVER on a public host)
#
# Everything is plain Python 3 - no dependencies to install.
set -e
cd "$(dirname "$0")"

case "$1" in
  --hotseat|--codespace)
    # Token-less actions (the monitor's ?debug=1 controls and local hot-seat
    # play) are disabled unless this explicit switch is set. They are never
    # enabled based on the client IP / X-Forwarded-For.
    export CATAN_HOTSEAT=1
    echo "[run] hot-seat mode: token-less monitor controls are ENABLED (CATAN_HOTSEAT=1)"
    echo "[run] do NOT use this on a publicly reachable server"
    ;;
esac

exec python3 server.py
