"""spec blocks — persist the spec IR and run the DETERMINISTIC structural
checks. No proving here: spec.validate only guarantees the IR is well-formed
(the MC-* layer). Semantic/behavior checking happens later against real code,
where the compiler + tests are sound.

Block rules: outcomes from structure only; db writes via conn on the state
class; nothing committed here (the engine owns the step-boundary transaction).
"""
from __future__ import annotations

import hashlib
import json

from forgeflow.blocks import block


def _get_spec(prev):
    """The author agent's IR, carried in prev['spec'] (see schemas/spec_result)."""
    return (prev or {}).get("spec") or {}


def _contract_hash(c):
    """Content hash of everything that determines a contract's generated code —
    signature, assertions, fulfills, paths. Reconcile diffs on this: same hash =>
    the function's code is still valid; different => re-codegen just that one."""
    payload = {
        "signature": c.get("signature", ""),
        "module": c.get("module") or "",
        "impl_file": c.get("impl_file") or "",
        "fulfills": sorted(c.get("fulfills") or []),
        "calls": [[cl.get("callee", ""), sorted((cl.get("args") or {}).items())]
                  for cl in (c.get("calls") or [])],   # a call change re-gens the fn
        "assertions": sorted(
            [a.get("kind", ""), a.get("text", ""), a.get("formal") or "",
             a.get("discharged_by") or "llm"]
            for a in (c.get("assertions") or [])),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _write_assertions_fulfills(conn, cid, c):
    """(re)write a contract's assertions + fulfills rows. Returns assertion count."""
    for rk in (c.get("fulfills") or []):
        conn.execute("INSERT OR IGNORE INTO contract_fulfills(contract_id, req_key)"
                     " VALUES (?,?)", (cid, rk))
    n = 0
    for i, a in enumerate(c.get("assertions") or []):
        if not a.get("kind") or not a.get("text"):
            continue
        conn.execute(
            "INSERT INTO contract_assertions(contract_id, kind, text,"
            " formal, encodable, discharged_by, seq) VALUES (?,?,?,?,?,?,?)",
            (cid, a["kind"], a["text"], a.get("formal"),
             1 if a.get("encodable") else 0, a.get("discharged_by") or "llm", i))
        n += 1
    return n


def _norm(s):
    return " ".join((s or "").split()).lower()


@block("reqs.load", "state", {"ok", "empty"})
def reqs_load(ctx, task, prev):
    """Persist the decomposed requirements (from `decompose`) by feature_key,
    BEFORE the spec is authored — so the coverage gate is an INDEPENDENT
    completeness check, not the author grading its own decomposition.

    STABLE-KEY RECONCILE, not wipe-and-reinsert: `contract_fulfills` (and via
    the contract hash, the whole progressive economy) keys on req_key, so a
    re-decompose that renumbers identical items must not churn keys. Same key ->
    update in place; new key whose TEXT matches an unclaimed old item -> keep
    the OLD key (renumbering safety net); truly new -> insert; gone -> delete."""
    conn = ctx["_conn"]
    fk = (task.get("payload") or {}).get("feature_key")
    reqs = (prev or {}).get("requirements") or []
    if not fk or not reqs:
        return "empty", {}
    old = {k: (t, kd) for k, t, kd in conn.execute(
        "SELECT req_key, text, kind FROM requirements WHERE feature_key=?", (fk,))}
    incoming_keys = {r.get("req_key") for r in reqs}
    # old items whose key the incoming list does NOT reuse, indexed by text —
    # a renumbered-but-identical item remaps onto its old key
    text_to_oldkey = {}
    for k, (t, _kd) in old.items():
        if k not in incoming_keys:
            text_to_oldkey.setdefault(_norm(t), k)
    seen, added, changed = set(), [], []
    for r in reqs:
        k, t, kd = r.get("req_key"), r.get("text"), r.get("kind")
        if not k or not t:
            continue
        if k not in old:
            k = text_to_oldkey.pop(_norm(t), k)   # renumbering safety net
        if k in seen:
            continue
        seen.add(k)
        if k in old:
            if _norm(old[k][0]) != _norm(t) or (old[k][1] or None) != (kd or None):
                conn.execute("UPDATE requirements SET text=?, kind=?"
                             " WHERE feature_key=? AND req_key=?", (t, kd, fk, k))
                changed.append(k)
        else:
            conn.execute("INSERT INTO requirements(feature_key, req_key, text, kind)"
                         " VALUES (?,?,?,?)", (fk, k, t, kd))
            added.append(k)
    removed = sorted(set(old) - seen)
    for k in removed:
        conn.execute("DELETE FROM requirements WHERE feature_key=? AND req_key=?", (fk, k))
    return "ok", {"feature_key": fk, "req_count": len(seen),
                  "reconcile": {"added": added, "changed": changed,
                                "removed": removed,
                                "kept": len(seen) - len(added) - len(changed)}}


@block("spec.ask", "state", {"proceed", "waiting"}, required_params={"stage"})
def spec_ask(ctx, task, prev):
    """The Q&A router — how ambiguity stops resolving silently. The agent's
    result may carry `questions`; each is either:
      - non-blocking: auto-answered with the agent's `recommended` and recorded
        as an ASSUMPTION (answered_by='default') — reviewable, overridable;
      - blocking: recorded unanswered; if any remain unanswered, emit
        spec.questions and route 'waiting' (the workflow parks). The user
        answers (scripts/answer.py or the board) and unparks; the agent re-runs
        with the whole dialogue in context and may ask follow-ups (multi-turn).
    'proceed' passes the agent's result through untouched for the next step."""
    conn = ctx["_conn"]
    fk = (task.get("payload") or {}).get("feature_key")
    stage = ctx["stage"]
    questions = (prev or {}).get("questions") or []
    recorded = 0
    for q in questions:
        qk, text = q.get("id"), q.get("question")
        if not qk or not text:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO dialogue(feature_key, stage, q_key, question,"
            " why, options, recommended, blocking) VALUES (?,?,?,?,?,?,?,?)",
            (fk, stage, qk, text, q.get("why_it_matters"),
             json.dumps(q.get("options") or []), q.get("recommended"),
             1 if q.get("blocking") else 0))
        recorded += 1
    # assumptions: non-blocking + still unanswered -> take the recommendation
    conn.execute(
        "UPDATE dialogue SET answer=recommended, answered_by='default',"
        " answered_at=datetime('now') WHERE feature_key=? AND stage=? AND"
        " blocking=0 AND answer IS NULL AND recommended IS NOT NULL",
        (fk, stage))
    open_qs = [dict(r) for r in conn.execute(
        "SELECT q_key, question, why, options, recommended FROM dialogue"
        " WHERE feature_key=? AND stage=? AND answer IS NULL", (fk, stage))]
    if open_qs:
        return "waiting", {
            "open_questions": open_qs, "stage": stage,
            "_staged": [{"op": "emit_event", "name": "spec.questions",
                         "payload": {"feature_key": fk, "stage": stage,
                                     "questions": open_qs}}]}
    out = dict(prev or {})
    out["assumptions_recorded"] = recorded
    return "proceed", out


@block("spec.load", "state", {"ok", "empty"})
def spec_load(ctx, task, prev):
    """INCREMENTAL reconcile of the IR into the DB — the heart of progressive
    (non-waterfall) SDD. Diffs the new IR against the existing spec by
    contract_key + content hash:
      - unchanged  -> left alone (its done codegen unit + body survive)
      - changed    -> updated; its codegen unit invalidated (-> pending)
      - added      -> inserted (a pending unit is seeded in sdd_build)
      - removed    -> dropped, with its codegen unit
    A signature change ripples through the interface, so it dirties the skeleton
    and re-pends every unit (coarse but correct; the compiler catches callers).
    """
    conn = ctx["_conn"]
    spec = _get_spec(prev)
    contracts = spec.get("contracts") or []
    fk = spec.get("feature_key")
    if not fk or not contracts:
        return "empty", {}

    row = conn.execute("SELECT id FROM specs WHERE feature_key=?", (fk,)).fetchone()
    if row:
        spec_id = row[0]
        conn.execute("UPDATE specs SET requirement=?, goal=? WHERE id=?",
                     (spec.get("requirement", ""), spec.get("goal"), spec_id))
    else:
        spec_id = conn.execute(
            "INSERT INTO specs(feature_key, requirement, goal, status)"
            " VALUES (?,?,?, 'draft')",
            (fk, spec.get("requirement", ""), spec.get("goal"))).lastrowid

    existing = {r[0]: (r[1], r[2], r[3]) for r in conn.execute(   # ck -> (id, hash, sig)
        "SELECT contract_key, id, hash, signature FROM contracts WHERE spec_id=?", (spec_id,))}
    new_keys, added, changed = set(), [], []
    sig_changed = False

    for c in contracts:
        ck = c.get("contract_key")
        if not ck or not c.get("signature"):
            continue
        new_keys.add(ck)
        h = _contract_hash(c)
        if ck in existing:
            cid, old_hash, old_sig = existing[ck]
            if old_hash == h:
                continue                                    # unchanged — keep done unit
            conn.execute("UPDATE contracts SET module=?, signature=?, summary=?,"
                         " impl_file=?, hash=? WHERE id=?",
                         (c.get("module"), c["signature"], c.get("summary"),
                          c.get("impl_file"), h, cid))
            conn.execute("DELETE FROM contract_assertions WHERE contract_id=?", (cid,))
            conn.execute("DELETE FROM contract_fulfills WHERE contract_id=?", (cid,))
            _write_assertions_fulfills(conn, cid, c)
            conn.execute("UPDATE codegen_units SET status='pending', body=NULL, attempts=0"
                         " WHERE feature_key=? AND contract_key=?", (fk, ck))
            changed.append(ck)
            if c["signature"] != old_sig:
                sig_changed = True
        else:
            cid = conn.execute(
                "INSERT INTO contracts(spec_id, contract_key, module, signature,"
                " summary, impl_file, hash) VALUES (?,?,?,?,?,?,?)",
                (spec_id, ck, c.get("module"), c["signature"], c.get("summary"),
                 c.get("impl_file"), h)).lastrowid
            _write_assertions_fulfills(conn, cid, c)
            added.append(ck)

    removed = [ck for ck in existing if ck not in new_keys]
    for ck in removed:
        cid = existing[ck][0]
        conn.execute("DELETE FROM contract_assertions WHERE contract_id=?", (cid,))
        conn.execute("DELETE FROM contract_fulfills WHERE contract_id=?", (cid,))
        conn.execute("DELETE FROM contracts WHERE id=?", (cid,))
        conn.execute("DELETE FROM codegen_units WHERE feature_key=? AND contract_key=?", (fk, ck))

    if sig_changed:                                         # interface rippled
        conn.execute("DELETE FROM codegen_modules WHERE feature_key=?", (fk,))
        conn.execute("UPDATE codegen_units SET status='pending', body=NULL, attempts=0"
                     " WHERE feature_key=?", (fk,))

    conn.execute("DELETE FROM chains WHERE spec_id=?", (spec_id,))   # chains: cheap replace
    for ch in spec.get("chains") or []:
        for seq, step in enumerate(ch.get("steps") or []):
            conn.execute("INSERT INTO chains(spec_id, chain_key, step_seq, contract_key)"
                         " VALUES (?,?,?,?)", (spec_id, ch.get("chain_key"), seq, step))

    return "ok", {"spec": spec, "spec_id": spec_id,
                  "reconcile": {"added": added, "changed": changed, "removed": removed,
                                "unchanged": len(new_keys) - len(added) - len(changed),
                                "sig_changed": sig_changed}}


@block("spec.validate", "state", {"ok", "invalid"})
def spec_validate(ctx, task, prev):
    """Deterministic MC-style checks over the IR. Pure structure, no LLM:
      - contract_keys unique
      - every chain step resolves to a declared contract
      - every contract has a signature AND an impl_file
      - encodable assertions actually carry a `formal` form
      - COVERAGE: every decomposed requirement is fulfilled by >=1 contract, no
        contract cites an unknown requirement, no contract is untraceable
    """
    conn = ctx["_conn"]
    spec = _get_spec(prev)
    contracts = spec.get("contracts") or []
    keys = [c.get("contract_key") for c in contracts if c.get("contract_key")]
    errors = []

    dupes = {k for k in keys if keys.count(k) > 1}
    if dupes:
        errors.append("duplicate contract_key(s): %s" % ", ".join(sorted(dupes)))

    keyset = set(keys)
    for ch in spec.get("chains") or []:
        for step in ch.get("steps") or []:
            if step not in keyset:
                errors.append("chain %s references unknown contract %s"
                              % (ch.get("chain_key"), step))

    for c in contracts:
        ck = c.get("contract_key", "?")
        if not c.get("signature"):
            errors.append("contract %s missing signature" % ck)
        if not c.get("impl_file"):
            errors.append("contract %s missing impl_file" % ck)
        for a in c.get("assertions") or []:
            if a.get("encodable") and not a.get("formal"):
                errors.append("contract %s: assertion marked encodable but has"
                              " no `formal` form: %s" % (ck, a.get("text", "")[:60]))

    # --- coverage: the req <-> spec trace (independent completeness gate) ---
    # out_of_scope items are EXCLUSIONS — they must NOT be built, so they don't
    # need a fulfilling contract (and a contract that fulfills one is a red flag).
    fk = (task.get("payload") or {}).get("feature_key")
    rows = conn.execute(
        "SELECT req_key, kind FROM requirements WHERE feature_key=?", (fk,)).fetchall()
    reqs = set(r[0] for r in rows)
    must_cover = set(r[0] for r in rows if r[1] != "out_of_scope")
    oos = reqs - must_cover
    fulfilled = set()
    if reqs:
        for c in contracts:
            ff = c.get("fulfills") or []
            if not ff:
                errors.append("contract %s fulfills no requirement (untraceable)"
                              % c.get("contract_key", "?"))
            for rk in ff:
                if rk not in reqs:
                    errors.append("contract %s cites unknown requirement %s"
                                  % (c.get("contract_key", "?"), rk))
                elif rk in oos:
                    errors.append("contract %s fulfills out-of-scope requirement %s"
                                  % (c.get("contract_key", "?"), rk))
                else:
                    fulfilled.add(rk)
        for rk in sorted(must_cover - fulfilled):
            errors.append("requirement %s is not fulfilled by any contract" % rk)

    if errors:
        return "invalid", {"errors": errors, "spec": spec}
    return "ok", {"spec": spec, "checks_passed": True,
                  "coverage": {"requirements": len(reqs), "covered": len(fulfilled)}}
