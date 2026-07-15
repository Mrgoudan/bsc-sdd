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


def _idf_rank(query_text, docs, k):
    """IDF-weighted ranking (BM25-lite): score = sum of idf over shared tokens /
    sum of idf over query tokens. Rare tokens dominate, so code boilerplate
    (_safe, void, json_value...) stops deciding matches — the raw-overlap
    failure mode at scale. docs = [(payload, text)]; returns [(score, payload)].
    Deterministic; the pinned-embedder upgrade replaces this per corpus via the
    engine cascade (see project.yaml corpora)."""
    import math
    q = _tokens(query_text)
    if not q or not docs:
        return []
    toks = [_tokens(t) for _, t in docs]
    n = len(docs)
    df = {}
    for ts in toks:
        for t in ts:
            df[t] = df.get(t, 0) + 1
    idf = {t: math.log(1.0 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
    qmass = sum(idf.get(t, math.log(1.0 + n)) for t in q) or 1.0
    scored = []
    for (payload, _), ts in zip(docs, toks):
        s = sum(idf[t] for t in (q & ts))
        if s > 0:
            scored.append((s / qmass, payload))
    scored.sort(key=lambda x: -x[0])
    return scored[:k]


# error-signature normalization: match compiler errors by CLASS, not by the
# incidental identifiers/paths/line numbers in one occurrence of it.
_ERR_PATH = re.compile(r"\S+\.(?:cbs|hbs|cpp|cc|c|h)\b(?::\d+)*")  # longest-first
_ERR_QUOTED = re.compile(r"'[^']*'|‘[^’]*’|\"[^\"]*\"")
_ERR_NUM = re.compile(r"\b\d+\b")


def error_signature(text):
    """Normalize a compiler diagnostic to its class: drop file paths, line/col
    numbers, and quoted identifiers, keep the diagnostic wording."""
    s = (text or "").lower()
    s = _ERR_PATH.sub(" ", s)
    s = _ERR_QUOTED.sub(" <id> ", s)
    s = _ERR_NUM.sub(" ", s)
    return " ".join(s.split())


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
    qtext = (c["summary"] or "") + " " + (c["signature"] or "")
    docs = [(({"idiom": r["title"], "pattern": r["pattern"]}),
             "%s %s %s" % (r["title"], r["pattern"], r["tags"] or ""))
            for r in env.conn.execute("SELECT title, pattern, tags FROM bsc_idioms")]
    k = int((spec or {}).get("k", 2))
    # (the green-function EXEMPLAR is served by the select: over the
    # green_bodies corpus — the engine cascade owns that retrieval now.)
    return {"idioms": [dict(p, score=round(s, 3))
                       for s, p in _idf_rank(qtext, docs, k)]}


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
    if not err.strip():
        return None
    # match by error CLASS: both sides normalized (paths/linenos/identifiers
    # stripped) so 'item' vs 'tmp_fee' wording can't decide the match.
    docs = [({"from": r["contract_key"], "past_error": r["error"][:300],
              "fixed_body": r["body"][:1500]}, error_signature(r["error"]))
            for r in env.conn.execute("SELECT contract_key, error, body FROM fix_lessons")]
    k = int((spec or {}).get("k", 2))
    return [dict(p, score=round(s, 3))
            for s, p in _idf_rank(error_signature(err), docs, k)] or None


@context_provider("prior_art")
def _prior_art(env, task, spec):
    """Reuse-first for the author: existing contracts from OTHER features whose
    purpose matches this feature's requirements (call/extend them instead of
    duplicating), plus the closest design idioms. Query = the R-* texts."""
    fk = _feature_key(task)
    if not fk:
        return {}
    qtext = " ".join(t for (t,) in env.conn.execute(
        "SELECT text FROM requirements WHERE feature_key=?", (fk,)))
    if not qtext.strip():
        return {}
    api_docs = [({"feature": r["fk2"], "contract_key": r["contract_key"],
                  "signature": r["signature"], "summary": r["summary"]},
                 (r["summary"] or "") + " " + (r["signature"] or ""))
                for r in env.conn.execute(
            "SELECT s.feature_key AS fk2, c.contract_key, c.signature, c.summary"
            " FROM contracts c JOIN specs s ON s.id = c.spec_id"
            " WHERE s.feature_key != ? AND c.status='active'", (fk,))]
    idiom_docs = [({"idiom": r["title"], "pattern": r["pattern"]},
                   "%s %s %s" % (r["title"], r["pattern"], r["tags"] or ""))
                  for r in env.conn.execute("SELECT title, pattern, tags FROM bsc_idioms")]
    # NOTE: prose->code vocabulary gap is where lexical fails first; this corpus
    # is the first candidate for the pinned-embedder flip (see project.yaml).
    return {"existing_apis": [dict(p, score=round(s, 3))
                              for s, p in _idf_rank(qtext, api_docs, 5)],
            "design_idioms": [p for _, p in _idf_rank(qtext, idiom_docs, 3)]}


@context_provider("requirement_delta")
def _requirement_delta(env, task, spec):
    """The DETERMINISTIC diff between the stored requirement (last run) and the
    incoming one. Anchoring defense: an agent re-decomposing with its previous
    list in context tends to REPRODUCE it and silently drop new clauses (it
    happened live: a new last-write-wins clause vanished and the fidelity gate
    false-PASSed). Never ask a model to spot a diff — hand it the diff."""
    import difflib
    fk = _feature_key(task)
    new = (task.get("payload") or {}).get("requirement")
    if not fk or not new:
        return None
    row = env.conn.execute("SELECT cursor FROM watermarks WHERE scope=?",
                           ("reqs.doc.%s" % fk,)).fetchone()
    if not row:                                   # legacy fallback
        row = env.conn.execute("SELECT requirement FROM specs WHERE feature_key=?",
                               (fk,)).fetchone()
    if not row or not row[0] or row[0] == new:
        return None
    diff = list(difflib.unified_diff(row[0].splitlines(), new.splitlines(),
                                     "previous", "current", lineterm=""))
    return {"changed": True, "diff": "\n".join(diff[:400])}


@context_provider("current_spec")
def _current_spec(env, task, spec):
    """THIS feature's existing spec, in full (a re-run aid): the author must
    re-emit unchanged contracts VERBATIM so their content hashes stay stable and
    the reconcile re-pends only what the requirement change actually touched.
    Without this, paraphrase noise would masquerade as semantic change."""
    fk = _feature_key(task)
    if not fk:
        return []
    out = []
    for c in env.conn.execute(
            "SELECT c.id, c.contract_key, c.module, c.signature, c.summary,"
            " c.impl_file FROM contracts c JOIN specs s ON s.id = c.spec_id"
            " WHERE s.feature_key=? AND c.status='active' ORDER BY c.id", (fk,)):
        asserts = [{"kind": a["kind"], "text": a["text"], "formal": a["formal"],
                    "encodable": bool(a["encodable"]),
                    "discharged_by": a["discharged_by"]}
                   for a in env.conn.execute(
                       "SELECT kind, text, formal, encodable, discharged_by"
                       " FROM contract_assertions WHERE contract_id=?"
                       " ORDER BY seq", (c["id"],))]
        fulfills = [r[0] for r in env.conn.execute(
            "SELECT req_key FROM contract_fulfills WHERE contract_id=?"
            " ORDER BY req_key", (c["id"],))]
        out.append({"contract_key": c["contract_key"], "module": c["module"],
                    "signature": c["signature"], "summary": c["summary"],
                    "impl_file": c["impl_file"], "fulfills": fulfills,
                    "assertions": asserts})
    return out


@context_provider("dialogue")
def _dialogue(env, task, spec):
    """The requirement Q&A so far — the multi-turn memory. Answered rows are
    DECISIONS (answered_by='user') or ASSUMPTIONS (='default'); treat both as
    requirements. Unanswered blocking rows are still open. Never re-ask an
    answered question."""
    fk = _feature_key(task)
    if not fk:
        return []
    return [{"stage": r["stage"], "id": r["q_key"], "question": r["question"],
             "answer": r["answer"], "answered_by": r["answered_by"],
             "blocking": bool(r["blocking"])}
            for r in env.conn.execute(
                "SELECT stage, q_key, question, answer, answered_by, blocking"
                " FROM dialogue WHERE feature_key=? ORDER BY id", (fk,))]


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
