"""context providers — assemble the SLICE of the IR each agent needs, so the
prompt carries only what's relevant (payload optimization), not the whole spec.

  spec_slice  the contracts to generate (this unit's work)
  contracts   callee signatures the generated code must call correctly
  assertions  the business pre/post (text + structured `formal`) for the
              business check — the LLM reads `text` now; a Z3 backend reads
              `formal` later, same rows.
"""
from __future__ import annotations

import json
from pathlib import Path

from forgeflow.contract import context_provider


def _feature_key(task):
    return (task.get("payload") or {}).get("feature_key")


@context_provider("compile_feedback")
def _compile_feedback(env, task, spec):
    """On a regenerate-on-red retry: the errors from this task's LAST failed
    compile, so codegen can fix them instead of guessing. None on the first
    pass (no prior red) — the codegen prompt then ignores it."""
    row = env.conn.execute(
        "SELECT result FROM task_steps WHERE task_id=? AND step='compile'"
        " AND outcome='red' ORDER BY at DESC LIMIT 1", (task.get("id"),)).fetchone()
    if not row or not row[0]:
        return None
    try:
        res = json.loads(row[0])
    except (ValueError, TypeError):
        return None
    text = ""
    sp = res.get("stderr_path")
    if sp and Path(sp).exists():
        text = Path(sp).read_text(errors="replace")[-4000:]
    return {"file": res.get("file"), "errors": text or "(compile failed)"}


@context_provider("requirements")
def _requirements(env, task, spec):
    """The decomposed, ID'd requirements for this feature. The author maps each
    contract to these via `fulfills`; the coverage gate checks every one is met."""
    fk = _feature_key(task)
    if not fk:
        return []
    rows = env.conn.execute(
        "SELECT req_key, kind, text FROM requirements WHERE feature_key=? ORDER BY id",
        (fk,)).fetchall()
    return [{"req_key": r["req_key"], "kind": r["kind"], "text": r["text"]} for r in rows]


@context_provider("spec_slice")
def _spec_slice(env, task, spec):
    """The contracts of the module being generated. A fanned-out unit carries
    its `module` in the payload; without one (single-module feature) this is the
    whole feature's contracts."""
    fk = _feature_key(task)
    if not fk:
        return []
    mod = (task.get("payload") or {}).get("module")
    q = ("SELECT c.contract_key, c.module, c.signature, c.summary, c.impl_file"
         " FROM contracts c JOIN specs s ON s.id = c.spec_id"
         " WHERE s.feature_key=? AND c.status='active'")
    args = [fk]
    if mod:
        q += " AND c.module=?"
        args.append(mod)
    rows = env.conn.execute(q + " ORDER BY c.id", args).fetchall()
    return [{"contract_key": r["contract_key"], "module": r["module"],
             "signature": r["signature"], "summary": r["summary"],
             "impl_file": r["impl_file"]} for r in rows]


@context_provider("contracts")
def _contracts(env, task, spec):
    """Just the callee signatures — the interface the generated code binds to.
    The compiler will enforce these at every call site; the agent should honor
    them so the compile passes first time."""
    fk = _feature_key(task)
    if not fk:
        return []
    rows = env.conn.execute(
        "SELECT c.contract_key, c.signature FROM contracts c"
        " JOIN specs s ON s.id = c.spec_id"
        " WHERE s.feature_key=? AND c.status='active' ORDER BY c.id", (fk,)).fetchall()
    return [{"contract_key": r["contract_key"], "signature": r["signature"]}
            for r in rows]


@context_provider("skeleton")
def _skeleton(env, task, spec):
    """The frozen module interface (the .hbs) the per-function codegen codes
    against — the struct, the type set, and every function's declaration."""
    r = env.conn.execute("SELECT hbs FROM codegen_modules WHERE feature_key=? LIMIT 1",
                         (_feature_key(task),)).fetchone()
    return {"interface": r[0]} if r else {}


@context_provider("active_contract")
def _active_contract(env, task, spec):
    """The ONE function currently being generated (codegen_units.status='active')
    — its signature + business assertions. Keeps each gen call's context to a
    single function, not the whole module."""
    fk = _feature_key(task)
    u = env.conn.execute("SELECT contract_key FROM codegen_units"
                         " WHERE feature_key=? AND status='active' LIMIT 1", (fk,)).fetchone()
    if not u:
        return {}
    ck = u[0]
    c = env.conn.execute(
        "SELECT c.signature, c.summary FROM contracts c JOIN specs s ON s.id = c.spec_id"
        " WHERE s.feature_key=? AND c.contract_key=?", (fk, ck)).fetchone()
    if not c:
        return {}
    asserts = [{"kind": r["kind"], "text": r["text"], "formal": r["formal"]}
               for r in env.conn.execute(
        "SELECT a.kind, a.text, a.formal FROM contract_assertions a"
        " JOIN contracts c ON c.id = a.contract_id JOIN specs s ON s.id = c.spec_id"
        " WHERE s.feature_key=? AND c.contract_key=? ORDER BY a.seq", (fk, ck))]
    return {"contract_key": ck, "signature": c["signature"],
            "summary": c["summary"], "assertions": asserts}


@context_provider("req_trace")
def _req_trace(env, task, spec):
    """Each requirement with the contracts that claim to fulfill it. The
    conformance check reads the CODE of those contracts and decides whether the
    requirement is actually met — impl -> req, scoped by the trace."""
    fk = _feature_key(task)
    if not fk:
        return []
    out = []
    for r in env.conn.execute(
            "SELECT req_key, text FROM requirements WHERE feature_key=? ORDER BY id", (fk,)):
        cons = env.conn.execute(
            "SELECT c.contract_key, c.signature, c.impl_file FROM contract_fulfills cf"
            " JOIN contracts c ON c.id = cf.contract_id"
            " JOIN specs s ON s.id = c.spec_id"
            " WHERE s.feature_key=? AND cf.req_key=? ORDER BY c.id", (fk, r["req_key"])).fetchall()
        out.append({"req_key": r["req_key"], "text": r["text"],
                    "contracts": [{"contract_key": x["contract_key"],
                                   "signature": x["signature"],
                                   "impl_file": x["impl_file"]} for x in cons]})
    return out


@context_provider("assertions")
def _assertions(env, task, spec):
    """Business pre/post/side-effects for the feature: {contract_key: [...]}.
    Each carries `text` (LLM reads now) and `formal`+`encodable` (Z3 later)."""
    fk = _feature_key(task)
    if not fk:
        return {}
    rows = env.conn.execute(
        "SELECT c.contract_key, a.kind, a.text, a.formal, a.encodable"
        " FROM contract_assertions a"
        " JOIN contracts c ON c.id = a.contract_id"
        " JOIN specs s ON s.id = c.spec_id"
        " WHERE s.feature_key=? ORDER BY c.id, a.seq", (fk,)).fetchall()
    out = {}
    for r in rows:
        out.setdefault(r["contract_key"], []).append(
            {"kind": r["kind"], "text": r["text"],
             "formal": r["formal"], "encodable": bool(r["encodable"])})
    return out
