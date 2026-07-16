#!/usr/bin/env bash
# notify hook: args = <event-name> <payload-json> (appended by the engine).
# Log always; desktop-ping when notify-send exists. Swap for a webhook curl
# to route into chat — this file IS the integration point.
DIR="$(cd "$(dirname "$0")/.." && pwd)"
echo "$(date '+%F %T')  $1  $2" >> "$DIR/run/notifications.log"
command -v notify-send >/dev/null && notify-send "forgeflow: $1" "board: http://127.0.0.1:8791/decisions" || true
