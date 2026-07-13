#!/usr/bin/env bash
# Launch bsc-sdd on the forgeflow engine. Secrets come from one 0600 env file
# ($FORGEFLOW_SECRETS): sourcing (set -a) puts ANTHROPIC_* in the environment
# for the agents' env_keys.
#
# Usage:
#   ./run-bsc-sdd.sh validate
#   ./run-bsc-sdd.sh emit spec.requested --data '{"feature_key":"FEATURE-001", ...}' --drive
#   ./run-bsc-sdd.sh run
set -euo pipefail

PACK_DIR="$(cd "$(dirname "$0")" && pwd)"
ENGINE="${ENGINE:-$HOME/bsd/forgeflow}"
SECRETS="${FORGEFLOW_SECRETS:-$PACK_DIR/config/secrets.env}"
FF_ROOT="${FF_ROOT:-$PACK_DIR/run}"
mkdir -p "$FF_ROOT"                    # paths.data_root anchor must exist at load

if [ ! -f "$SECRETS" ]; then
  echo "missing $SECRETS — create it (chmod 600) with ANTHROPIC_BASE_URL/AUTH_TOKEN" >&2
  exit 1
fi
perm=$(stat -c '%a' "$SECRETS")
if [ "$perm" != "600" ]; then
  echo "refusing: $SECRETS is mode $perm, must be 600 (chmod 600 it)" >&2
  exit 1
fi

set -a; . "$SECRETS"; set +a
export FORGEFLOW_SECRETS="$SECRETS"
export PYTHONPATH="$ENGINE${PYTHONPATH:+:$PYTHONPATH}"

# egress off by default until there's a forge target wired (this pack has none yet).
export FORGE_WRITE="${FORGE_WRITE:-0}"

# domestic endpoints (GLM/gitcode) — drop any international proxy so calls go direct.
if [ -z "${NO_PROXY_UNSET:-}" ]; then
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
fi

exec python3 -m forgeflow --root "$FF_ROOT" --pack "$PACK_DIR" "$@"
