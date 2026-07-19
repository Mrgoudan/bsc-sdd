#!/usr/bin/env bash
# The runtime test floor: compile the GENERATED module together with the
# feature's smoke test into a real binary and run it. A pass means the code
# not only type/ownership-checks (the compile gate) but actually behaves at
# runtime. Everything is an argument — the harness is configuration, not code.
#
#   run_tests.sh <worktree> <smoke.cbs> <clang> <libcbs_src> [extra_test.cbs ...]
#
# The smoke test is REQUIRED (the human-authored behavior floor). Every extra
# arg is an OPTIONAL test file with its own main (e.g. the TDD-generated
# suite) — built and run separately; an absent extra is skipped with a note,
# because it only exists when the run asked for it.
set -euo pipefail

WORKTREE="$1"; SMOKE="$2"; CLANG="$3"; LIBCBS="$4"; shift 4

# module sources: ANY .cbs in the worktree except test files and build dirs
# (never assume a src/ layout — the module path is the spec's business)
MODS=()
while IFS= read -r f; do MODS+=("$f"); done < <(
    find "$WORKTREE" -name "*.cbs" \
         -not -path "*/tests/*" -not -path "*/.smoke/*" -not -path "*/.git/*" \
         | sort)
[ "${#MODS[@]}" -gt 0 ] || { echo "no generated .cbs under $WORKTREE"; exit 1; }
[ -f "$SMOKE" ] || { echo "smoke test $SMOKE missing (required)"; exit 1; }

INCS=()
for d in "$LIBCBS"/*/; do INCS+=("-I" "${d%/}"); done
for f in "${MODS[@]}"; do INCS+=("-I" "$(dirname "$f")"); done  # .hbs beside .cbs

OUT="$WORKTREE/.smoke"
mkdir -p "$OUT"
# link every libcbs impl TU — String etc. are not header-only
IMPLS=()
while IFS= read -r f; do IMPLS+=("$f"); done < <(find "$LIBCBS" -name "*.cbs" | sort)

run_suite() {  # <label> <test.cbs>
    "$CLANG" -Wno-nullability-completeness "${INCS[@]}" \
        "${MODS[@]}" "$2" "${IMPLS[@]}" \
        -lpthread -lm \
        -o "$OUT/$1_bin"
    "$OUT/$1_bin"
    echo "suite $1: PASS"
}

run_suite smoke "$SMOKE"
n=0
for extra in "$@"; do
    n=$((n + 1))
    if [ -f "$extra" ]; then
        run_suite "extra$n" "$extra"
    else
        echo "suite extra$n: skipped ($extra absent — not a TDD run)"
    fi
done
