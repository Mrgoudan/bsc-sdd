"""context providers — assemble the SLICE of the IR each agent needs, so the
prompt carries only what's relevant (payload optimization), not the whole spec.

  spec_slice  the contracts to generate (this unit's work)
  contracts   callee signatures the generated code must call correctly
  assertions  the behavior pre/post (text + structured `formal`) for the
              behavior check — the LLM reads `text` now; a Z3 backend reads
              `formal` later, same rows.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from forgeflow.contract import context_provider


def _feature_key(task):
    return (task.get("payload") or {}).get("feature_key")


def _tokens(s):
    return set(re.findall(r"[a-z_]{3,}", (s or "").lower()))


@context_provider("similar")
def _similar(env, task, spec):
    """RAG: the vetted BSC idioms most relevant to the function being generated.
    Query = the ACTIVE function's summary + signature (per-function retrieval —
    the engine's select: only queries the payload, which is fixed per task, so
    we retrieve here). Lexical (token-overlap) ranking, the same class as the
    engine's embed_with: hashing. `spec.k` = how many to return (default 2)."""
    fk = _feature_key(task)
    u = env.conn.execute("SELECT contract_key FROM codegen_units"
                         " WHERE feature_key=? AND status='active' LIMIT 1", (fk,)).fetchone()
    if not u:
        return []
    c = env.conn.execute(
        "SELECT c.signature, c.summary FROM contracts c JOIN specs s ON s.id = c.spec_id"
        " WHERE s.feature_key=? AND c.contract_key=?", (fk, u[0])).fetchone()
    if not c:
        return []
    q = _tokens((c["summary"] or "") + " " + (c["signature"] or ""))
    if not q:
        return {}
    scored = []
    for r in env.conn.execute("SELECT id, title, pattern, tags FROM bsc_idioms"):
        d = _tokens("%s %s %s" % (r["title"], r["pattern"], r["tags"] or ""))
        overlap = len(q & d)
        if overlap:
            scored.append((overlap / float(len(q | d)), r["title"], r["pattern"]))
    scored.sort(key=lambda x: -x[0])
    k = int((spec or {}).get("k", 2))
    idioms = [{"score": round(s, 3), "idiom": t, "pattern": p} for s, t, p in scored[:k]]

    # the self-improving half: the most similar already-GREEN function of this
    # feature as a worked exemplar — every green compile makes this corpus better.
    best, best_s = None, 0.0
    for r in env.conn.execute(
            "SELECT u.contract_key, u.body, c.signature, c.summary"
            " FROM codegen_units u JOIN contracts c ON c.contract_key = u.contract_key"
            " JOIN specs s ON s.id = c.spec_id AND s.feature_key = u.feature_key"
            " WHERE u.feature_key=? AND u.status='done' AND u.body IS NOT NULL"
            " AND u.contract_key != ?", (fk, u[0])):
        d = _tokens((r["summary"] or "") + " " + (r["signature"] or ""))
        if not d:
            continue
        s_ = len(q & d) / float(len(q | d))
        if s_ > best_s:
            best_s, best = s_, {"contract_key": r["contract_key"],
                                "score": round(s_, 3), "body": r["body"][:2000]}
    return {"idioms": idioms, "exemplar": best}


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


@context_provider("fix_hints")
def _fix_hints(env, task, spec):
    """When the current function is red: the closest past (error -> body that
    fixed it) lessons, ranked by error-text overlap. The pipeline learning from
    its own compiler fights. None on a first pass (no red)."""
    row = env.conn.execute(
        "SELECT result FROM task_steps WHERE task_id=? AND step='compile'"
        " AND outcome='red' ORDER BY at DESC LIMIT 1", (task.get("id"),)).fetchone()
    if not row or not row[0]:
        return None
    try:
        res = json.loads(row[0])
    except (ValueError, TypeError):
        return None
    err = ""
    sp = res.get("stderr_path")
    if sp and Path(sp).exists():
        err = Path(sp).read_text(errors="replace")[-2000:]
    q = _tokens(err)
    if not q:
        return None
    scored = []
    for r in env.conn.execute("SELECT contract_key, error, body FROM fix_lessons"):
        d = _tokens(r["error"])
        if not d:
            continue
        s_ = len(q & d) / float(len(q | d))
        if s_ > 0:
            scored.append((s_, r["contract_key"], r["error"][:300], r["body"][:1500]))
    scored.sort(key=lambda x: -x[0])
    k = int((spec or {}).get("k", 2))
    return [{"score": round(s_, 3), "past_error": e, "fixed_body": b,
             "from": ck} for s_, ck, e, b in scored[:k]] or None


@context_provider("prior_art")
def _prior_art(env, task, spec):
    """Reuse-first for the author: existing contracts from OTHER features whose
    purpose matches this feature's requirements (call/extend them instead of
    duplicating), plus the closest design idioms. Query = the R-* texts."""
    fk = _feature_key(task)
    if not fk:
        return {}
    q = _tokens(" ".join(t for (t,) in env.conn.execute(
        "SELECT text FROM requirements WHERE feature_key=?", (fk,))))
    if not q:
        return {}
    apis = []
    for r in env.conn.execute(
            "SELECT s.feature_key AS fk2, c.contract_key, c.signature, c.summary"
            " FROM contracts c JOIN specs s ON s.id = c.spec_id"
            " WHERE s.feature_key != ? AND c.status='active'", (fk,)):
        d = _tokens((r["summary"] or "") + " " + (r["signature"] or ""))
        if not d:
            continue
        s_ = len(q & d) / float(len(q | d))
        if s_ > 0:
            apis.append((s_, {"feature": r["fk2"], "contract_key": r["contract_key"],
                              "signature": r["signature"], "summary": r["summary"]}))
    apis.sort(key=lambda x: -x[0])
    idioms = []
    for r in env.conn.execute("SELECT title, pattern, tags FROM bsc_idioms"):
        d = _tokens("%s %s %s" % (r["title"], r["pattern"], r["tags"] or ""))
        s_ = len(q & d) / float(len(q | d)) if d else 0
        if s_ > 0:
            idioms.append((s_, {"idiom": r["title"], "pattern": r["pattern"]}))
    idioms.sort(key=lambda x: -x[0])
    return {"existing_apis": [a for _, a in apis[:5]],
            "design_idioms": [i for _, i in idioms[:3]]}


@context_provider("decompose_feedback")
def _decompose_feedback(env, task, spec):
    """On a decompose retry after the fidelity gate (reqs_check) failed: the
    gate's findings (missing / invented / distorted items), so the re-decompose
    fixes exactly those instead of starting over. None on the first pass."""
    row = env.conn.execute(
        "SELECT result FROM task_steps WHERE task_id=? AND step='reqs_check'"
        " AND outcome='FAIL' ORDER BY at DESC LIMIT 1", (task.get("id"),)).fetchone()
    if not row or not row[0]:
        return None
    try:
        res = json.loads(row[0])
    except (ValueError, TypeError):
        return None
    return {"findings": res.get("findings") or [], "summary": res.get("summary")}


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
    """The frozen interface (the .hbs) of the ACTIVE function's module — the
    struct, the type set, and every declaration the body codes against."""
    fk = _feature_key(task)
    u = env.conn.execute("SELECT module FROM codegen_units WHERE feature_key=?"
                         " AND status='active' LIMIT 1", (fk,)).fetchone()
    if u:
        r = env.conn.execute("SELECT hbs FROM codegen_modules WHERE feature_key=?"
                             " AND module=?", (fk, u[0])).fetchone()
        if r:
            return {"interface": r[0]}
    r = env.conn.execute("SELECT hbs FROM codegen_modules WHERE feature_key=? LIMIT 1",
                         (fk,)).fetchone()
    return {"interface": r[0]} if r else {}


@context_provider("active_contract")
def _active_contract(env, task, spec):
    """The ONE function currently being generated (codegen_units.status='active')
    — its signature + behavior assertions. Keeps each gen call's context to a
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
    bodies = dict(env.conn.execute(
        "SELECT contract_key, body FROM codegen_units"
        " WHERE feature_key=? AND body IS NOT NULL", (fk,)))
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
                                   "impl_file": x["impl_file"],
                                   "body": (bodies.get(x["contract_key"]) or "")[:3000] or None}
                                  for x in cons]})
    return out


@context_provider("assertions")
def _assertions(env, task, spec):
    """Behavior pre/post/side-effects for the feature: {contract_key: [...]}.
    Each carries `text` (LLM reads now) and `formal`+`encodable` (Z3 later)."""
    fk = _feature_key(task)
    if not fk:
        return {}
    rows = env.conn.execute(
        "SELECT c.contract_key, a.kind, a.text, a.formal, a.encodable"
        " FROM contract_assertions a"
        " JOIN contracts c ON c.id = a.contract_id"
        " JOIN specs s ON s.id = c.spec_id"
        " WHERE s.feature_key=? AND a.discharged_by != 'compiler'"  # compiler proves those
        " ORDER BY c.id, a.seq", (fk,)).fetchall()
    grouped = {}
    for r in rows:
        grouped.setdefault(r["contract_key"], []).append(
            {"kind": r["kind"], "text": r["text"],
             "formal": r["formal"], "encodable": bool(r["encodable"])})
    # serve the CODE with the claims: the judge gets each contract's generated
    # body (from codegen_units) instead of hunting the worktree for it.
    bodies = dict(env.conn.execute(
        "SELECT contract_key, body FROM codegen_units"
        " WHERE feature_key=? AND body IS NOT NULL", (fk,)))
    return [{"contract_key": ck, "impl": (bodies.get(ck) or "")[:4000] or None,
             "assertions": asserts} for ck, asserts in grouped.items()]
