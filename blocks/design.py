"""design.check — the MECHANICAL design gate (stage 2), before any codegen.

Every new function declares its direct calls to other new functions with an
arg data-flow (`param <- source`). This gate checks each such handoff against a
qualifier-compatibility table: can the source value's ownership/nullability
satisfy the callee param's? It is DETERMINISTIC — no LLM, no compile — so an
inconsistent DESIGN is caught before we spend implementation.

Scope (per the design decision): NEW functions, DIRECTLY called. Library calls
(safe_malloc, etc.) are external + compiler-checked; transitive calls are not
modelled. This verifies "the pieces I am building fit together" at the type
level, which the compiler later re-confirms soundly on the generated code.
"""
from __future__ import annotations

import re

from forgeflow.blocks import block

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _quals(fragment):
    """Ownership/nullability qualifiers present in a type fragment."""
    borrow = ("_Borrow" in fragment) or ("&_Mut" in fragment) or ("&_Const" in fragment)
    mut = ("&_Mut" in fragment) or (
        "_Borrow" in fragment and "&_Const" not in fragment and "const " not in fragment)
    return {"owned": "_Owned" in fragment, "borrow": borrow, "mut": mut,
            "nonnull": "_Nonnull" in fragment, "nullable": "_Nullable" in fragment}


def _split_top(s):
    """Split a param list on top-level commas (respecting <> and () nesting)."""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "<(":
            depth += 1
        elif ch in ">)":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return out


def parse_signature(sig):
    """-> {return: quals, params: {name: quals}}. Pragmatic BSC-signature parse:
    the last identifier of each param decl is its name; qualifiers are keywords."""
    lp = sig.find("(")
    if lp < 0:
        return {"return": _quals(sig), "params": {}}
    head, rp = sig[:lp], sig.rfind(")")
    body = sig[lp + 1:rp] if rp > lp else ""
    params = {}
    if body.strip() and body.strip() != "void":
        for p in _split_top(body):
            names = _IDENT.findall(p)
            if names:
                params[names[-1]] = _quals(p)      # last identifier = param name
    return {"return": _quals(head), "params": params}


def compat(src, dst):
    """Can a value with quals `src` be passed where `dst` is required? None = ok,
    else the reason it's a CHAIN_BREAK."""
    if dst["owned"] and not src["owned"]:
        return "callee wants _Owned but the source is not owned"
    if dst["borrow"] and not (src["owned"] or src["borrow"]):
        return "callee wants a borrow but the source is a bare value"
    if dst["mut"] and src["borrow"] and not src["mut"]:
        return "callee wants &_Mut but the source is a const borrow"
    if dst["nonnull"] and src["nullable"]:
        return "callee wants _Nonnull but the source is _Nullable (needs a null check)"
    return None


def _resolve_source(source, caller_sig, sigs):
    """A source ref: 'param:<name>' (the caller's param) or 'result:<contract_key>'
    (the return of a directly-called new function)."""
    if source.startswith("param:"):
        return caller_sig["params"].get(source[6:])
    if source.startswith("result:"):
        k = source[7:]
        return sigs[k]["return"] if k in sigs else None
    return None


@block("design.check", "local", {"ok", "broken"})
def design_check(ctx, task, prev):
    """The mechanical design gate. Walks every new function's direct calls and
    checks each arg handoff's qualifier compatibility (+ callee/param resolve +
    use-after-move). No calls declared => nothing to check (passes)."""
    spec = (prev or {}).get("spec") or {}
    contracts = {c["contract_key"]: c for c in (spec.get("contracts") or [])
                 if c.get("contract_key") and c.get("signature")}
    sigs = {k: parse_signature(c["signature"]) for k, c in contracts.items()}
    breaks = []

    for ck, c in contracts.items():
        caller = sigs[ck]
        moved = {}                                  # owned source -> times consumed
        for call in (c.get("calls") or []):
            callee = call.get("callee")
            if callee not in sigs:
                breaks.append({"in": ck, "callee": callee,
                               "reason": "calls unknown new function"})
                continue
            cps = sigs[callee]["params"]
            for param, source in (call.get("args") or {}).items():
                if param not in cps:
                    breaks.append({"in": ck, "callee": callee, "param": param,
                                   "reason": "callee has no such param"})
                    continue
                src = _resolve_source(source, caller, sigs)
                if src is None:
                    breaks.append({"in": ck, "callee": callee, "param": param,
                                   "reason": "unresolved source '%s'" % source})
                    continue
                why = compat(src, cps[param])
                if why:
                    breaks.append({"in": ck, "callee": callee, "param": param,
                                   "source": source, "reason": why})
                if src["owned"] and cps[param]["owned"]:
                    moved[source] = moved.get(source, 0) + 1
                    if moved[source] > 1:
                        breaks.append({"in": ck, "source": source,
                                       "reason": "owned value moved into more than one call"})

    if breaks:
        return "broken", {"chain_breaks": breaks, "count": len(breaks)}
    return "ok", {"spec": spec, "checked": len(contracts)}
