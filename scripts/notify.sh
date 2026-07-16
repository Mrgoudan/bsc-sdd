#!/usr/bin/env bash
# notify hook: args = <event-name> <payload-json> (appended by the engine).
# Log always; desktop-ping when notify-send exists. Swap for a webhook curl
# to route into chat — this file IS the integration point.
DIR="$(cd "$(dirname "$0")/.." && pwd)"
echo "$(date '+%F %T')  $1  $2" >> "$DIR/run/notifications.log"
# webhook example (Feishu/DingTalk/Slack-compatible endpoints): uncomment + set URL
# curl -s -m 5 -X POST -H 'Content-Type: application/json' \
#   -d "{\"msg_type\":\"text\",\"content\":{\"text\":\"forgeflow: $1 — http://<host>:8791/decisions\"}}" \
#   "$FORGE_NOTIFY_WEBHOOK" >/dev/null 2>&1 || true
command -v notify-send >/dev/null && notify-send "forgeflow: $1" "board: http://127.0.0.1:8791/decisions" || true
