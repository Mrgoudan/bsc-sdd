#!/usr/bin/env python3
"""Render a spec IR from the DB to a readable, versionable YAML file.

The DB is the source of truth; this is an export projection (like the review
pack's db_export) so a spec can be read, diffed, and reviewed as a file.

Usage:
  render_spec.py --db <forgeflow.db> --feature <feature_key> [--out <file>]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys


def _q(s):
    """Quote a scalar for YAML if needed."""
    if s is None:
        return "null"
    s = str(s)
    if s == "" or any(ch in s for ch in ':#{}[],&*!|>%@`"') or s[0] in " -?" or s != s.strip():
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def render(db, feature):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    sp = c.execute("SELECT * FROM specs WHERE feature_key=?", (feature,)).fetchone()
    if not sp:
        sys.exit("no spec with feature_key=%s in %s" % (feature, db))
    L = []
    L.append("# Rendered from the forgeflow DB (source of truth). Do not hand-edit;")
    L.append("# regenerate with scripts/render_spec.py after the spec changes.")
    L.append("feature_key: %s" % _q(sp["feature_key"]))
    L.append("status: %s" % _q(sp["status"]))
    if sp["goal"]:
        L.append("goal: %s" % _q(sp["goal"]))

    # the requirement dialogue: user decisions + recorded assumptions
    drows = c.execute("SELECT stage, q_key, question, answer, answered_by, blocking"
                      " FROM dialogue WHERE feature_key=? ORDER BY id",
                      (feature,)).fetchall()
    if drows:
        L.append("dialogue:")
        for r in drows:
            L.append("  - id: %s" % _q("%s/%s" % (r["stage"], r["q_key"])))
            L.append("    question: %s" % _q(r["question"]))
            if r["answer"] is None:
                L.append("    status: OPEN (blocking=%s)" % bool(r["blocking"]))
            else:
                L.append("    answer: %s" % _q(r["answer"]))
                L.append("    decided_by: %s" % _q(
                    "user" if r["answered_by"] == "user" else "assumption (default)"))

    # the decomposed requirements (the coverage/trace targets)
    reqrows = c.execute("SELECT req_key, kind, text FROM requirements"
                        " WHERE feature_key=? ORDER BY id", (feature,)).fetchall()
    if reqrows:
        L.append("requirements:")
        for r in reqrows:
            L.append("  - req_key: %s" % _q(r["req_key"]))
            L.append("    kind: %s" % _q(r["kind"]))
            L.append("    text: %s" % _q(r["text"]))

    L.append("contracts:")
    for co in c.execute("SELECT * FROM contracts WHERE spec_id=? ORDER BY id", (sp["id"],)):
        L.append("  - contract_key: %s" % _q(co["contract_key"]))
        ff = [r[0] for r in c.execute(
            "SELECT req_key FROM contract_fulfills WHERE contract_id=? ORDER BY req_key",
            (co["id"],))]
        if ff:
            L.append("    fulfills: [%s]" % ", ".join(_q(x) for x in ff))
        if co["module"]:
            L.append("    module: %s" % _q(co["module"]))
        L.append("    signature: %s" % _q(co["signature"]))
        if co["impl_file"]:
            L.append("    impl_file: %s" % _q(co["impl_file"]))
        if co["summary"]:
            L.append("    summary: %s" % _q(co["summary"]))
        arows = c.execute("SELECT kind,text,formal,encodable,discharged_by"
                          " FROM contract_assertions"
                          " WHERE contract_id=? ORDER BY seq", (co["id"],)).fetchall()
        if arows:
            L.append("    assertions:")
            for a in arows:
                L.append("      - kind: %s" % _q(a["kind"]))
                L.append("        text: %s" % _q(a["text"]))
                if a["discharged_by"] and a["discharged_by"] != "llm":
                    L.append("        discharged_by: %s" % _q(a["discharged_by"]))
                if a["formal"]:
                    L.append("        formal: %s" % _q(a["formal"]))
                    L.append("        encodable: %s" % ("true" if a["encodable"] else "false"))

    L.append("chains:")
    ckeys = [r[0] for r in c.execute(
        "SELECT DISTINCT chain_key FROM chains WHERE spec_id=? ORDER BY chain_key", (sp["id"],))]
    for ck in ckeys:
        steps = [r[0] for r in c.execute(
            "SELECT contract_key FROM chains WHERE spec_id=? AND chain_key=? ORDER BY step_seq",
            (sp["id"], ck))]
        L.append("  - chain_key: %s" % _q(ck))
        L.append("    steps: [%s]" % ", ".join(_q(s) for s in steps))
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--feature", required=True)
    ap.add_argument("--out")
    a = ap.parse_args()
    text = render(a.db, a.feature)
    if a.out:
        with open(a.out, "w") as f:
            f.write(text)
        print("wrote %s" % a.out)
    else:
        sys.stdout.write(text)
