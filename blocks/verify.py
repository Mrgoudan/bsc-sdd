"""verify blocks — the SOUND gates.

verify.compile  the crown jewel: run the BSC compiler over the generated .cbs.
                A green compile PROVES the safety column (null/own/init/borrow)
                inside every function AND at every call site — the whole safety
                design plus the joins, soundly, for free. Red = a real defect.
verify.test     the business floor: run the target's tests (sound per case).

Both record a `verifications` row with sound=1 so the audit trail distinguishes
compiler/test evidence from the LLM residual (sound=0).
"""
from __future__ import annotations

from pathlib import Path

from forgeflow.blocks import block
from forgeflow.util import run_cmd, template


def _feature_key(task):
    return (task.get("payload") or {}).get("feature_key")


def _spec_id(conn, feature_key):
    row = conn.execute("SELECT id FROM specs WHERE feature_key=?",
                       (feature_key,)).fetchone()
    return row[0] if row else None


def _record(conn, task, checker, target, verdict, evidence=None):
    sid = _spec_id(conn, _feature_key(task))
    conn.execute(
        "INSERT INTO verifications(spec_id, contract_id, checker, target,"
        " verdict, sound, evidence, run_id) VALUES (?,?,?,?,?,1,?,?)",
        (sid, None, checker, target, verdict, evidence, task.get("run_id")))


@block("verify.compile", "state", {"green", "red", "error", "timeout"},
       required_params={"cmd", "repo"})
def verify_compile(ctx, task, prev):
    """Compile each generated file with the BSC compiler. First failure => red.
    cmd is templated per file with {file}."""
    conn = ctx["_conn"]
    written = (prev or {}).get("written") or []
    if not written:
        # nothing generated to compile — treat as an error, not a pass
        _record(conn, task, "compiler", "safety", "unknown", "no files")
        return "error", {"reason": "no generated files to compile"}

    for path in written:
        cmd = [template(a, {"file": path}) for a in ctx["cmd"]]
        code, out, err = run_cmd(cmd, ctx["_timeout_s"], Path(ctx["_step_dir"]),
                                 tools=ctx.get("_tools"))
        if code != 0:
            _record(conn, task, "compiler", "safety", "fail", err)
            return "red", {"file": path, "stderr_path": err, "exit_code": code}
    _record(conn, task, "compiler", "safety", "pass")
    return "green", {"compiled": len(written)}


@block("verify.test", "state", {"pass", "fail", "error", "timeout"},
       required_params={"cmd", "repo"})
def verify_test(ctx, task, prev):
    """Run the target's tests — the sound floor for business logic."""
    conn = ctx["_conn"]
    cmd = [template(a, {}) for a in ctx["cmd"]]
    code, out, err = run_cmd(cmd, ctx["_timeout_s"], Path(ctx["_step_dir"]),
                             tools=ctx.get("_tools"))
    if code == 0:
        _record(conn, task, "test", "tests", "pass")
        return "pass", {"stdout_path": out}
    _record(conn, task, "test", "tests", "fail", err)
    return "fail", {"stderr_path": err, "exit_code": code}
