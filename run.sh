#!/usr/bin/env bash
# Start the Catan server.
#
# Usage:
#   ./run.sh              # normal (default): local machine, ?debug=1 allowed only from localhost
#   ./run.sh --codespace  # Codespaces / dev: also allow ?debug=1 (hot-seat) from the forwarded URL
#
# Everything is plain Python 3 - no dependencies to install.
set -e
cd "$(dirname "$0")"

if [ "$1" = "--codespace" ]; then
  # Codespaces forwards ports through a proxy, so the request never comes from
  # 127.0.0.1. Allow the RFC1918 ranges + loopback so ?debug=1 works while you
  # test. NEVER use this on a machine that is reachable from the internet.
  export CATAN_DEBUG_CIDRS="127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
  echo "[run] codespace mode: ?debug=1 is enabled from private ranges"
fi

exec python3 server.py
