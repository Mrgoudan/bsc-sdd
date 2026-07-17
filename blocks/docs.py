"""docs.render — the two human-readable documents, as PROJECTIONS of the DB.

  spec.md    WHAT the system should do: the source requirement, the decomposed
             R-items (behavior / success signals / constraints / out of scope),
             and the Q&A that shaped them.
  design.md  HOW the system does it: the picked design decision, the contracts
             (signatures + traceability), the behavior assertions with who
             discharges each, the call chains, and the verification trail.

Both are REGENERATED from the database at every pipeline milestone — nobody
edits them, so they can never drift from what the pipeline actually holds.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from forgeflow.blocks import block


def _fk(task):
    return (task.get("payload") or {}).get("feature_key")


def _stamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


_KIND_TITLES = (("behavior", "Behavior"),
                ("success_signal", "Success signals"),
                ("constraint", "Constraints"),
                ("out_of_scope", "Out of scope"))


def _spec_md(conn, fk, spec):
    out = ["# %s — specification (WHAT)" % fk, "",
           "> Generated %s from the pipeline database — do not edit; the"
           " pipeline regenerates this file." % _stamp(), ""]
    if spec["goal"]:
        out += ["**Goal.** %s" % spec["goal"], ""]
    out += ["**Status:** %s" % spec["status"], ""]

    reqs = conn.execute("SELECT req_key, text, kind FROM requirements"
                        " WHERE feature_key=? ORDER BY id", (fk,)).fetchall()
    by_kind = {}
    for r in reqs:
        by_kind.setdefault(r["kind"] or "behavior", []).append(r)
    out += ["## Requirements", ""]
    for kind, title in _KIND_TITLES:
        rows = by_kind.pop(kind, [])
        if not rows:
            continue
        out += ["### %s" % title, ""]
        out += ["- **%s** — %s" % (r["req_key"], r["text"]) for r in rows]
        out += [""]
    for kind, rows in sorted(by_kind.items()):        # any other kind
        out += ["### %s" % kind, ""]
        out += ["- **%s** — %s" % (r["req_key"], r["text"]) for r in rows]
        out += [""]

    qa = conn.execute("SELECT stage, q_key, question, answer, answered_by"
                      " FROM dialogue WHERE feature_key=? ORDER BY id",
                      (fk,)).fetchall()
    if qa:
        out += ["## Questions & answers", ""]
        for r in qa:
            who = {"default": "assumption (agent default)",
                   "user": "decided by user"}.get(r["answered_by"],
                                                  r["answered_by"] or "open")
            out += ["- **%s/%s** — %s" % (r["stage"], r["q_key"], r["question"]),
                    "  - **answer:** %s _(%s)_"
                    % (r["answer"] or "(unanswered)", who)]
        out += [""]

    out += ["## Source requirement", "",
            "```", (spec["requirement"] or "").rstrip(), "```", ""]
    return "\n".join(out)


def _design_md(conn, fk, spec):
    import json
    out = ["# %s — design (HOW)" % fk, "",
           "> Generated %s from the pipeline database — do not edit; the"
           " pipeline regenerates this file." % _stamp(), ""]

    dec = conn.execute("SELECT * FROM decisions WHERE key=? AND"
                       " verdict='picked' ORDER BY round DESC LIMIT 1",
                       ("%s/design" % fk,)).fetchone()
    if dec:
        picked = (json.loads(dec["answer"] or "{}")).get("picked")
        out += ["## Design decision", "",
                "**%s** — round %d, picked: **%s**"
                % (dec["title"], dec["round"], picked), ""]
        for o in json.loads(dec["options"] or "[]"):
            if isinstance(o, dict) and o.get("title") == picked:
                if o.get("summary"):
                    out += [o["summary"], ""]
                if o.get("sketch"):
                    out += ["```", str(o["sketch"]).rstrip(), "```", ""]

    contracts = conn.execute(
        "SELECT c.* FROM contracts c JOIN specs s ON s.id = c.spec_id"
        " WHERE s.feature_key=? AND c.status='active' ORDER BY c.module, c.id",
        (fk,)).fetchall()
    fulfills, asserts = {}, {}
    for c in contracts:
        fulfills[c["id"]] = [r[0] for r in conn.execute(
            "SELECT req_key FROM contract_fulfills WHERE contract_id=?"
            " ORDER BY req_key", (c["id"],))]
        asserts[c["id"]] = conn.execute(
            "SELECT kind, text, formal, discharged_by FROM contract_assertions"
            " WHERE contract_id=? ORDER BY seq", (c["id"],)).fetchall()
    modules = {}
    for c in contracts:
        modules.setdefault(c["module"] or "default", []).append(c)

    out += ["## Contracts (%d, by module)" % len(contracts), ""]
    for mod in sorted(modules):
        out += ["### module `%s`" % mod, ""]
        for c in modules[mod]:
            out += ["#### %s" % c["contract_key"], ""]
            if c["summary"]:
                out += [c["summary"], ""]
            out += ["```c", c["signature"], "```", "",
                    "fulfills: %s" % (", ".join(fulfills[c["id"]]) or "—"), ""]
            if asserts[c["id"]]:
                out += ["| assertion | kind | discharged by |",
                        "|---|---|---|"]
                out += ["| %s | %s | %s |"
                        % (a["text"].replace("|", "\\|"), a["kind"],
                           a["discharged_by"])
                        for a in asserts[c["id"]]]
                out += [""]

    chains = conn.execute(
        "SELECT ch.chain_key, ch.step_seq, ch.contract_key FROM chains ch"
        " JOIN specs s ON s.id = ch.spec_id WHERE s.feature_key=?"
        " ORDER BY ch.chain_key, ch.step_seq", (fk,)).fetchall()
    if chains:
        by_chain = {}
        for r in chains:
            by_chain.setdefault(r["chain_key"], []).append(r["contract_key"])
        out += ["## Call chains", ""]
        out += ["- **%s**: %s" % (k, " → ".join(v))
                for k, v in sorted(by_chain.items())]
        out += [""]

    v = conn.execute(
        "SELECT checker, verdict, sound, count(*) n FROM verifications"
        " WHERE spec_id=? GROUP BY checker, verdict, sound"
        " ORDER BY checker, verdict", (spec["id"],)).fetchall()
    if v:
        out += ["## Verification trail", "",
                "| checker | verdict | basis | count |", "|---|---|---|---|"]
        out += ["| %s | %s | %s | %d |"
                % (r["checker"], r["verdict"],
                   "sound" if r["sound"] else "argued", r["n"]) for r in v]
        out += [""]
    units = conn.execute(
        "SELECT status, count(*) n FROM codegen_units WHERE feature_key=?"
        " GROUP BY status", (fk,)).fetchall()
    if units:
        out += ["Functions: " + ", ".join("%d %s" % (r["n"], r["status"])
                                          for r in units), ""]
    return "\n".join(out)


@block("docs.render", "state", {"ok", "empty"}, required_params={"out_dir"})
def docs_render(ctx, task, prev):
    """Write <out_dir>/<feature_key>/spec.md (WHAT) and design.md (HOW),
    rendered from the DB. Runs at every milestone (validated spec, finished
    build, function edit), so the folder always mirrors the pipeline."""
    conn = ctx["_conn"]
    fk = _fk(task)
    spec = conn.execute("SELECT * FROM specs WHERE feature_key=?",
                        (fk,)).fetchone()
    if not spec:
        return "empty", {}
    out = Path(str(ctx["out_dir"])).expanduser() / fk
    out.mkdir(parents=True, exist_ok=True)
    spec_md = _spec_md(conn, fk, spec)
    design_md = _design_md(conn, fk, spec)
    (out / "spec.md").write_text(spec_md)
    (out / "design.md").write_text(design_md)
    return "ok", {"spec_md": str(out / "spec.md"),
                  "design_md": str(out / "design.md"),
                  "spec_bytes": len(spec_md), "design_bytes": len(design_md)}
