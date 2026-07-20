#!/usr/bin/env bash
# Live proof that the pipeline produced WORKING code: rehydrate a completed
# feature's functions from the DB, compile them, and run its real behavior
# smoke test. No fakes — the bodies come straight out of codegen_units.
#
#   ./scripts/demo_verify.sh CJSON-P1
set -euo pipefail
FK="${1:-CJSON-P1}"
PACK="$(cd "$(dirname "$0")/.." && pwd)"
DB="$PACK/run/state/forgeflow.db"
L="$HOME/bsd/llvm-project-dup/libcbs/src"
CLANG="$HOME/bsd/llvm-project-dup/build/bin/clang"
SMOKE="$HOME/bsd/bsc-sdd-projects/$FK/smoke.cbs"
OUT="$(mktemp -d)"

echo "== rehydrating $FK from the pipeline database =="
python3 - "$DB" "$FK" "$OUT" <<'PY'
import sqlite3, sys
from pathlib import Path
db, fk, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
c = sqlite3.connect(db); c.row_factory = sqlite3.Row
for m in c.execute("SELECT hbs, cbs_head, hbs_path, cbs_path FROM codegen_modules"
                   " WHERE feature_key=? AND module!='__tests__'", (fk,)):
    bodies = [b for (b,) in c.execute(
        "SELECT body FROM codegen_units WHERE feature_key=? AND module=("
        "SELECT module FROM codegen_modules WHERE feature_key=? AND hbs_path=?)"
        " AND body IS NOT NULL AND status='done' ORDER BY seq",
        (fk, fk, m["hbs_path"]))]
    (out / m["hbs_path"]).parent.mkdir(parents=True, exist_ok=True)
    (out / m["hbs_path"]).write_text(m["hbs"])
    (out / m["cbs_path"]).write_text(
        m["cbs_head"].rstrip() + "\n\n" + "\n\n".join(b.strip() for b in bodies) + "\n")
    print("  %s: %d functions -> %s" % (m["cbs_path"], len(bodies), out))
PY

CBS="$(find "$OUT" -name '*.cbs' | head -1)"
INCS=(); for d in "$L"/*/; do INCS+=("-I" "${d%/}"); done; INCS+=("-I" "$(dirname "$CBS")")
IMPLS=(); while IFS= read -r f; do IMPLS+=("$f"); done < <(find "$L" -name '*.cbs' | sort)

echo "== compiling the generated code + its smoke test (the SOUND gate) =="
"$CLANG" -Wno-nullability-completeness "${INCS[@]}" "$CBS" "$SMOKE" "${IMPLS[@]}" \
    -lpthread -lm -o "$OUT/smoke_bin"
echo "   COMPILE GREEN"
echo "== running the real behavior smoke test =="
"$OUT/smoke_bin"
echo "   exit=$?  —  the pipeline's output works."
