#!/usr/bin/env bash
# Interactive design discussion: talk to the model ABOUT a pending decision,
# with the whole thread + spec context assembled from the DB. On exit, distill
# your conclusions back into the thread:
#
#   ./run-bsc-sdd.sh discuss 3
#   ... interactive session ...
#   ./run-bsc-sdd.sh decide 3 revise --comment "we concluded: hybrid of A+C, cap depth at 128"
#
# The DECISION THREAD stays the source of truth — the discussion informs it,
# the verdict routes the workflow.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
DID="${1:?usage: discuss <decision-id>}"
CTX="$DIR/run/discussions/decision-$DID.md"
mkdir -p "$DIR/run/discussions"

python3 - "$DIR/run/state/forgeflow.db" "$DID" > "$CTX" <<'PY'
import json, sqlite3, sys
conn = sqlite3.connect(sys.argv[1]); conn.row_factory = sqlite3.Row
d = conn.execute("SELECT * FROM decisions WHERE id=?", (sys.argv[2],)).fetchone()
if d is None:
    sys.exit("no decision %s" % sys.argv[2])
print("# Design discussion: %s (round %d, %s)\n" % (d["key"], d["round"], d["status"]))
print("## The question\n\n%s\n" % d["title"])
if d["body"]:
    print("%s\n" % d["body"])
print("## Options on the table\n")
for o in json.loads(d["options"] or "[]"):
    if isinstance(o, dict):
        print("### %s%s" % (o.get("title"), "  (recommended)" if o.get("title") == d["recommended"] else ""))
        if o.get("summary"): print(o["summary"])
        for p in o.get("pros") or []: print("- + %s" % p)
        for c in o.get("cons") or []: print("- − %s" % c)
        if o.get("risks"): print("- risk: %s" % o["risks"])
        if o.get("sketch"): print("```\n%s\n```" % o["sketch"])
        print()
    else:
        print("- %s" % o)
print("## Thread so far\n")
for r in conn.execute("SELECT round, verdict, answer FROM decisions WHERE key=? ORDER BY round", (d["key"],)):
    a = json.loads(r["answer"] or "{}")
    print("- round %d: %s%s%s" % (r["round"], r["verdict"] or "open",
          (" rejected=%s" % a.get("rejected")) if a.get("rejected") else "",
          (' comment="%s"' % a.get("comment")) if a.get("comment") else ""))
print("\n## Your task\n\nDiscuss the tradeoffs with me. Challenge the options; propose hybrids;"
      "\nquantify the risks for THIS codebase (explore it — you are in the repo)."
      "\nEnd with a concrete recommendation and its key signatures.")
PY

echo "context: $CTX"
echo "(end the session with Ctrl+C / exit; then record conclusions:"
echo "   ./run-bsc-sdd.sh decide $DID <verdict> --comment '...')"
cd "$DIR" && REPO="$(python3 -c "
import yaml; print(yaml.safe_load(open('project.yaml'))['paths']['repo'])")"
REPO="${REPO/#\~/$HOME}"
cd "$REPO"
exec claude --model GLM-5.2 "$(cat "$CTX")"
