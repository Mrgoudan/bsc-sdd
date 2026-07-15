#!/usr/bin/env bash
# The runtime test floor: compile the GENERATED module together with the
# feature's smoke test into a real binary and run it. A pass means the code
# not only type/ownership-checks (the compile gate) but actually behaves at
# runtime. Everything is an argument — the harness is configuration, not code.
#
#   run_tests.sh <worktree> <smoke.cbs> <clang> <libcbs_src>
set -euo pipefail

WORKTREE="$1"; SMOKE="$2"; CLANG="$3"; LIBCBS="$4"

CBS="$(ls "$WORKTREE"/src/*.cbs 2>/dev/null | head -1)"
[ -n "$CBS" ] || { echo "no generated .cbs under $WORKTREE/src"; exit 1; }

INCS=()
for d in "$LIBCBS"/*/; do INCS+=("-I" "${d%/}"); done
INCS+=("-I" "$(dirname "$CBS")")          # the generated .hbs lives beside the .cbs

OUT="$WORKTREE/.smoke"
mkdir -p "$OUT"
"$CLANG" -Wno-nullability-completeness "${INCS[@]}" \
    "$CBS" "$SMOKE" "$LIBCBS/bishengc_safety/bishengc_safety.cbs" \
    -o "$OUT/smoke_bin"
exec "$OUT/smoke_bin"
