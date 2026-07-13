"""spec blocks — persist the spec IR and run the DETERMINISTIC structural
checks. No proving here: spec.validate only guarantees the IR is well-formed
(the MC-* layer). Semantic/business checking happens later against real code,
where the compiler + tests are sound.

Block rules: outcomes from structure only; db writes via conn on the state
class; nothing committed here (the engine owns the step-boundary transaction).
"""
from __future__ import annotations

from forgeflow.blocks import block


def _get_spec(prev):
    """The author agent's IR, carried in prev['spec'] (see schemas/spec_result)."""
    return (prev or {}).get("spec") or {}


@block("spec.load", "state", {"ok", "empty"})
def spec_load(ctx, task, prev):
    """Stage the IR into specs / contracts / contract_assertions / chains.
    Idempotent on feature_key so a re-run replaces cleanly."""
    conn = ctx["_conn"]
    spec = _get_spec(prev)
    contracts = spec.get("contracts") or []
    if not spec.get("feature_key") or not contracts:
        return "empty", {}

    fk = spec["feature_key"]
    # replace any prior draft of this feature (cascade by hand — no FK cascade)
    row = conn.execute("SELECT id FROM specs WHERE feature_key=?", (fk,)).fetchone()
    if row:
        old = row[0]
        conn.execute("DELETE FROM contract_assertions WHERE contract_id IN"
                     " (SELECT id FROM contracts WHERE spec_id=?)", (old,))
        conn.execute("DELETE FROM contracts WHERE spec_id=?", (old,))
        conn.execute("DELETE FROM chains WHERE spec_id=?", (old,))
        conn.execute("DELETE FROM specs WHERE id=?", (old,))

    cur = conn.execute(
        "INSERT INTO specs(feature_key, requirement, goal, status)"
        " VALUES (?,?,?, 'draft')",
        (fk, spec.get("requirement", ""), spec.get("goal")))
    spec_id = cur.lastrowid

    n_c = n_a = n_s = 0
    for c in contracts:
        if not c.get("contract_key") or not c.get("signature"):
            continue
        cc = conn.execute(
            "INSERT INTO contracts(spec_id, contract_key, module, signature,"
            " summary, impl_file) VALUES (?,?,?,?,?,?)",
            (spec_id, c["contract_key"], c.get("module"), c["signature"],
             c.get("summary"), c.get("impl_file")))
        cid = cc.lastrowid
        n_c += 1
        for i, a in enumerate(c.get("assertions") or []):
            if not a.get("kind") or not a.get("text"):
                continue
            conn.execute(
                "INSERT INTO contract_assertions(contract_id, kind, text,"
                " formal, encodable, seq) VALUES (?,?,?,?,?,?)",
                (cid, a["kind"], a["text"], a.get("formal"),
                 1 if a.get("encodable") else 0, i))
            n_a += 1

    for ch in spec.get("chains") or []:
        ck = ch.get("chain_key")
        for seq, step in enumerate(ch.get("steps") or []):
            conn.execute(
                "INSERT INTO chains(spec_id, chain_key, step_seq, contract_key)"
                " VALUES (?,?,?,?)", (spec_id, ck, seq, step))
            n_s += 1

    return "ok", {"spec": spec, "spec_id": spec_id,
                  "counts": {"contracts": n_c, "assertions": n_a, "steps": n_s}}


@block("spec.validate", "local", {"ok", "invalid"})
def spec_validate(ctx, task, prev):
    """Deterministic MC-style checks over the IR. Pure structure, no LLM:
      - contract_keys unique
      - every chain step resolves to a declared contract
      - every contract has a signature AND an impl_file
      - encodable assertions actually carry a `formal` form
    """
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

    if errors:
        return "invalid", {"errors": errors, "spec": spec}
    return "ok", {"spec": spec, "checks_passed": True}
