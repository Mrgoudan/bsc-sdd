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

# read-only, offline subcommands — no secrets/agents needed, so they run
# before the secrets gate:
#   ./run-bsc-sdd.sh verify   <FEATURE>   # rehydrate + compile + run smoke
#   ./run-bsc-sdd.sh coverage <FEATURE>   # requirement -> code totality gate
if [ "${1:-}" = "verify" ]; then
  shift; exec "$PACK_DIR/scripts/demo_verify.sh" "$@"
fi
if [ "${1:-}" = "coverage" ]; then
  shift
  exec python3 "$PACK_DIR/scripts/confirm_coverage.py" \
       --db "$FF_ROOT/state/forgeflow.db" --feature "${1:?feature key required}"
fi

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

# column migrations: the engine's IF-NOT-EXISTS schema apply adds new tables
# but never new columns — bring an existing state DB up to the current pack
# schema before the engine touches it (idempotent, instant).
if [ -f "$FF_ROOT/state/forgeflow.db" ]; then
  python3 "$PACK_DIR/scripts/migrate_db.py" --db "$FF_ROOT/state/forgeflow.db"
fi

# the requirement dialogue, without ceremony:
#   ./run-bsc-sdd.sh questions              # what is the pipeline waiting on?
#   ./run-bsc-sdd.sh answer Q-1=replace     # answer + auto-resume
#   ./run-bsc-sdd.sh answer --accept-defaults
if [ "${1:-}" = "questions" ]; then
  shift
  exec python3 "$PACK_DIR/scripts/answer.py" --db "$FF_ROOT/state/forgeflow.db" "$@"
fi
if [ "${1:-}" = "discuss" ]; then
  shift
  exec "$PACK_DIR/scripts/discuss.sh" "$@"
fi
if [ "${1:-}" = "answer" ]; then
  shift
  ARGS=()
  for a in "$@"; do
    case "$a" in
      Q-*=*|q-*=*) ARGS+=("--set" "$a");;   # bare Q-1=x sugar
      *)           ARGS+=("$a");;
    esac
  done
  exec python3 "$PACK_DIR/scripts/answer.py" --db "$FF_ROOT/state/forgeflow.db" "${ARGS[@]}"
fi

# one daemon per root: a second `run` would reset the live daemon's running
# tasks as "orphans" and race its walks. flock makes the second start a no-op.
export PYTHONUNBUFFERED=1                 # daemon logs flush line-by-line
if [ "${1:-}" = "run" ]; then
  exec flock -n "$FF_ROOT/daemon.lock" python3 -m forgeflow --root "$FF_ROOT" --pack "$PACK_DIR" "$@" \
    || { echo "another daemon already holds $FF_ROOT/daemon.lock"; exit 1; }
fi
exec python3 -m forgeflow --root "$FF_ROOT" --pack "$PACK_DIR" "$@"
