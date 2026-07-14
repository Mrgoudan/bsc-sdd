"""spec blocks — persist the spec IR and run the DETERMINISTIC structural
checks. No proving here: spec.validate only guarantees the IR is well-formed
(the MC-* layer). Semantic/business checking happens later against real code,
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


@block("reqs.load", "state", {"ok", "empty"})
def reqs_load(ctx, task, prev):
    """Persist the decomposed requirements (from `decompose`) by feature_key,
    BEFORE the spec is authored — so the coverage gate is an INDEPENDENT
    completeness check, not the author grading its own decomposition."""
    conn = ctx["_conn"]
    fk = (task.get("payload") or {}).get("feature_key")
    reqs = (prev or {}).get("requirements") or []
    if not fk or not reqs:
        return "empty", {}
    conn.execute("DELETE FROM requirements WHERE feature_key=?", (fk,))
    n = 0
    for r in reqs:
        if not r.get("req_key") or not r.get("text"):
            continue
        conn.execute("INSERT OR IGNORE INTO requirements(feature_key, req_key, text, kind)"
                     " VALUES (?,?,?,?)", (fk, r["req_key"], r["text"], r.get("kind")))
        n += 1
    return "ok", {"feature_key": fk, "req_count": n}


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
