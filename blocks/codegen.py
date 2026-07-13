"""codegen blocks — turn the spec into BiSheng C.

codegen.plan   fan-out units (one per contract). Payload optimization: each
               unit later carries only its slice of the spec, not the whole
               thing. (Skeleton: enumerates units; true group fan-out TODO.)
codegen.write  write the agent's generated .cbs files into the worktree.
"""
from __future__ import annotations

from pathlib import Path

from forgeflow.blocks import block


def _payload_spec(task):
    return (task.get("payload") or {}).get("spec") or {}


@block("codegen.plan", "local", {"ok", "empty"})
def codegen_plan(ctx, task, prev):
    """Enumerate codegen units from the spec's contracts. Each unit is the
    smallest thing an agent generates in one shot (one function/API)."""
    spec = _payload_spec(task)
    units = [{"contract_key": c.get("contract_key"),
              "impl_file": c.get("impl_file")}
             for c in spec.get("contracts") or [] if c.get("contract_key")]
    if not units:
        return "empty", {}
    # TODO: real fan-out — emit one codegen task per unit via a group/_join so
    # functions generate in parallel (lane: llm). Skeleton runs them as one.
    return "ok", {"units": units, "unit_count": len(units)}


@block("codegen.write", "local", {"ok", "empty"}, required_params={"repo"})
def codegen_write(ctx, task, prev):
    """Write the agent's files into the worktree. The agent returns
    prev['files'] = [{path, content}]; path is repo-relative."""
    files = (prev or {}).get("files") or []
    # prefer the worktree the codegen agent ran in; fall back to the repo.
    root = Path((prev or {}).get("path") or ctx["repo"]).expanduser()
    written = []
    for f in files:
        rel = (f or {}).get("path")
        content = (f or {}).get("content")
        if not rel or content is None:
            continue
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        written.append(str(dest))
    if not written:
        return "empty", {}
    return "ok", {"written": written, "root": str(root)}
