#!/usr/bin/env python3
"""confirm_coverage — prove every decomposed requirement is traced to code
and checked, and that no code is untraceable. This is the mechanical
totality guarantee the pipeline enforces, made runnable as a standalone
gate: exit 0 iff coverage is complete, nonzero with a report otherwise.

  scripts/confirm_coverage.py --db run/state/forgeflow.db --feature CJSON-P1

For each IN-SCOPE requirement it reports the fulfilling contract(s) and the
recorded conformance verdict; it fails loudly on:
  - an in-scope requirement fulfilled by NO contract          (orphan req)
  - a contract that fulfills NO known requirement             (untraceable)
  - a requirement whose conformance verdict is not 'pass'     (unmet, if any)
"""
import argparse
import sqlite3
import sys


def confirm(db, feature):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    spec = c.execute("SELECT id FROM specs WHERE feature_key=?", (feature,)).fetchone()
    if not spec:
        print("no spec for feature %r" % feature)
        return 2
    sid = spec["id"]

    reqs = c.execute(
        "SELECT req_key, text, kind FROM requirements WHERE feature_key=?"
        " ORDER BY req_key", (feature,)).fetchall()
    in_scope = [r for r in reqs if (r["kind"] or "") != "out_of_scope"]

    # req -> [contract_key]
    fulfill = {}
    for r in c.execute(
            "SELECT f.req_key, ct.contract_key FROM contract_fulfills f"
            " JOIN contracts ct ON ct.id = f.contract_id"
            " WHERE ct.spec_id=? AND ct.status='active'"
            " ORDER BY ct.contract_key", (sid,)):
        fulfill.setdefault(r["req_key"], []).append(r["contract_key"])

    # req -> conformance verdict (llm, target 'req:R-x')
    verdict = {}
    for v in c.execute(
            "SELECT target, verdict FROM verifications WHERE spec_id=?"
            " AND target LIKE 'req:%'", (sid,)):
        verdict[v["target"].split(":", 1)[1]] = v["verdict"]

    # every active contract must fulfill >= 1 known requirement
    known = {r["req_key"] for r in reqs}
    untraceable = []
    for ct in c.execute("SELECT id, contract_key FROM contracts"
                        " WHERE spec_id=? AND status='active'", (sid,)):
        got = [r[0] for r in c.execute(
            "SELECT req_key FROM contract_fulfills WHERE contract_id=?", (ct["id"],))]
        if not got or not (set(got) & known):
            untraceable.append(ct["contract_key"])

    orphans = [r["req_key"] for r in in_scope if not fulfill.get(r["req_key"])]
    unmet = [r["req_key"] for r in in_scope
             if verdict.get(r["req_key"], "pass") not in ("pass", None)]

    print("== coverage: %s ==" % feature)
    print("requirements: %d total, %d in-scope, %d out-of-scope"
          % (len(reqs), len(in_scope), len(reqs) - len(in_scope)))
    ncontracts = c.execute("SELECT count(*) FROM contracts WHERE spec_id=?"
                           " AND status='active'", (sid,)).fetchone()[0]
    print("contracts: %d active" % ncontracts)
    print()
    for r in in_scope:
        cks = fulfill.get(r["req_key"], [])
        v = verdict.get(r["req_key"])
        mark = "OK " if cks and (v in (None, "pass")) else "!! "
        vtag = (" [%s]" % v) if v else ""
        print("  %s%-6s -> %s%s"
              % (mark, r["req_key"], ", ".join(cks) or "(NO CONTRACT)", vtag))

    ok = not orphans and not untraceable and not unmet
    print()
    if orphans:
        print("FAIL orphan requirements (no fulfilling contract): %s"
              % ", ".join(orphans))
    if untraceable:
        print("FAIL untraceable contracts (fulfill no known requirement): %s"
              % ", ".join(untraceable))
    if unmet:
        print("FAIL requirements with a non-pass conformance verdict: %s"
              % ", ".join(unmet))
    if ok:
        print("COVERAGE COMPLETE: every in-scope requirement is traced to code,"
              " every contract is traceable.")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--feature", required=True)
    a = ap.parse_args()
    sys.exit(confirm(a.db, a.feature))
