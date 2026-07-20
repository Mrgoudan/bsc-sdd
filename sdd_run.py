#!/usr/bin/env python3
"""sdd_run — the SDD pipeline as ONE self-contained script. No forgeflow, no
vendored copy: this single file runs a feature straight through

    requirement -> R-items -> spec -> skeleton -> whole module
                -> COMPILE (the sound gate) -> smoke test

by calling the model (GLM via the `claude` CLI), the BiSheng C compiler, and
SQLite-free flat files directly.

It is the pipeline's *labor* without the *factory*. It has NO repair loops (a
compile red stops), no human gates, no resumability, no audit trail, no board.
Those are the forgeflow engine. Use this to run a simple happy-path feature on
a machine with nothing but Python 3 + the compiler + the model CLI; use the
engine (./run-bsc-sdd.sh) for anything real.

    FORGEFLOW_SECRETS=~/.config/forgeflow/secrets.env \\
        python3 sdd_run.py --feature CC-RUN
    python3 sdd_run.py --feature CC-RUN --from module   # resume from a stage

Config: the CONFIG dict below (override any value with env SDD_<KEY>).
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

CONFIG = {
    "bsc_clang":  "~/bsd/llvm-project-dup/build/bin/clang",
    "libcbs_src": "~/bsd/llvm-project-dup/libcbs/src",
    "projects":   "~/bsd/bsc-sdd-projects",
    "out":        "~/bsd/bsc-sdd/sdd_run_out",
    "cli":        "claude",
    "model":      "GLM-5.2",
    "env_keys":   ["ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN"],
    "timeout_s":  1800,
}


def cfg(k):
    return os.environ.get("SDD_" + k.upper(), CONFIG[k])


def path(k):
    return Path(str(cfg(k))).expanduser()


# ---- inlined prompts (faithful to the pack, condensed for one file) --------
P_DECOMPOSE = """Decompose the requirement below into ATOMIC, independently
checkable requirement items. Each item: a stable id (R-1, R-2, ...), one
sentence of pure behavior (no implementation vocabulary), and a kind
(behavior | success_signal | constraint | out_of_scope). Cover the whole
document; invent nothing it does not state. Return ONLY JSON:
{ "requirements": [ {"req_key":"R-1","text":"...","kind":"behavior"} ] }"""

P_AUTHOR = """Author a spec IR from the requirement + its decomposed R-items.
Emit one CONTRACT per function: a BiSheng C signature with ownership
annotations (borrows after *, _Owned only when you keep/free, never _Mut/
_Const in a declaration), a summary, the R-item keys it fulfills, and its
behavior assertions (pre/post/side_effect). Every in-scope R-item must be
fulfilled by >=1 contract; every contract must cite >=1 R-item. Group
contracts into one module. Return ONLY JSON:
{ "feature_key":"F", "contracts":[ {"contract_key":"K","module":"m",
"signature":"_Safe ...","summary":"...","fulfills":["R-1"],
"assertions":[{"kind":"post","text":"..."}] } ] }"""

P_SKELETON = """Produce the module interface ONCE: the .hbs (includes, the
struct(s) typedef'd by bare name, and a declaration for EVERY contract
signature verbatim) and a .cbs preamble (include the .hbs + any private
helpers). Do not implement the public functions. Never _Mut/_Const in a
declaration. Return ONLY JSON: { "hbs":"...", "cbs_head":"..." }"""

P_GENMODULE = """Implement EVERY function of the module in one go, so
caller/callee wiring stays consistent (a caller and callee must agree on
ownership and who does what — do not pass the same input twice, do not use a
value after it is moved). Signatures VERBATIM from the skeleton. BSC
discipline: borrows after *, _Unsafe scoped to raw-pointer/syscall work.
Return ONLY JSON: { "functions":[ {"contract_key":"K","body":"<code>"} ] }"""


# ---- model call ------------------------------------------------------------
def load_secrets():
    p = os.environ.get("FORGEFLOW_SECRETS")
    out = {}
    if p and Path(p).is_file():
        for line in Path(p).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip()
    return out


def ask(prompt, secrets):
    env = dict(os.environ)
    for k in cfg("env_keys"):
        if k in secrets:
            env[k] = secrets[k]
    argv = [cfg("cli"), "-p", "--permission-mode", "bypassPermissions",
            "--output-format", "json", "--model", str(cfg("model"))]
    p = subprocess.run(argv, input=prompt.encode(), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, env=env,
                       timeout=int(cfg("timeout_s")))
    if p.returncode != 0:
        sys.exit("model call failed (%d): %s" % (p.returncode,
                 p.stderr.decode()[-400:]))
    txt = p.stdout.decode("utf-8", "replace")
    try:
        e = json.loads(txt)
        return e.get("result") or e.get("text") or txt
    except ValueError:
        return txt


def extract_json(text):
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        return json.loads(m.group(1))
    i = text.find("{")
    if i >= 0:
        d = 0
        for j in range(i, len(text)):
            d += (text[j] == "{") - (text[j] == "}")
            if d == 0:
                return json.loads(text[i:j + 1])
    raise ValueError("no JSON object in model reply")


def gen(prompt, extra, secrets):
    return extract_json(ask(prompt + "\n\n" + extra, secrets))


# ---- the stages ------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feature", required=True)
    ap.add_argument("--from", dest="frm", default="decompose",
                    choices=["decompose", "spec", "skeleton", "module", "compile"])
    a = ap.parse_args()
    secrets = load_secrets()
    fdir = path("projects") / a.feature
    req = (fdir / "requirement.md").read_text()
    smoke = fdir / "smoke.cbs"
    out = path("out") / a.feature
    out.mkdir(parents=True, exist_ok=True)
    order = ["decompose", "spec", "skeleton", "module", "compile"]
    start = order.index(a.frm)
    print("== sdd_run: %s (one script, no engine) ==" % a.feature)

    reqs = None                        # only the spec stage needs the R-items
    if start <= 0:
        reqs = gen(P_DECOMPOSE, "## Requirement\n" + req, secrets)["requirements"]
        (out / "requirements.json").write_text(json.dumps(reqs, indent=1))
        print("  decompose: %d R-items" % len(reqs))
    elif start == 1:
        reqs = json.loads((out / "requirements.json").read_text())

    if start <= 1:
        spec = gen(P_AUTHOR, "## Requirement\n%s\n## R-items\n%s"
                   % (req, json.dumps(reqs)), secrets)
        (out / "spec.json").write_text(json.dumps(spec, indent=1))
        print("  spec: %d contracts" % len(spec["contracts"]))
    else:
        spec = json.loads((out / "spec.json").read_text())
    module = spec["contracts"][0].get("module") or "module"

    if start <= 2:
        sigs = "\n".join(c["signature"] for c in spec["contracts"] if c.get("signature"))
        sk = gen(P_SKELETON, "## Contracts\n" + sigs, secrets)
        (out / (module + ".hbs")).write_text(sk["hbs"])
        (out / "cbs_head.txt").write_text(sk.get("cbs_head", ""))
        print("  skeleton: %d-byte interface" % len(sk["hbs"]))
    else:
        sk = {"hbs": (out / (module + ".hbs")).read_text(),
              "cbs_head": (out / "cbs_head.txt").read_text()}

    if start <= 3:
        cs = json.dumps([{"contract_key": c["contract_key"],
                          "signature": c["signature"],
                          "assertions": c.get("assertions", [])}
                         for c in spec["contracts"]])
        res = gen(P_GENMODULE, "## Frozen interface\n```c\n%s\n```\n## Contracts\n%s"
                  % (sk["hbs"], cs), secrets)
        cbs = sk["cbs_head"].rstrip() + "\n\n" + \
            "\n\n".join(f["body"].strip() for f in res["functions"]) + "\n"
        (out / (module + ".cbs")).write_text(cbs)
        print("  module: %d bodies -> %s.cbs" % (len(res["functions"]), module))

    ok = compile_and_smoke(module, out, smoke)
    print("== %s ==" % ("DONE — compiles" + (" + smoke passes" if ok else "")
                        if ok else "STOPPED"))
    sys.exit(0 if ok else 1)


def compile_and_smoke(module, out, smoke):
    clang, libcbs = str(path("bsc_clang")), path("libcbs_src")
    incs = []
    for d in sorted(libcbs.iterdir()):
        if d.is_dir():
            incs += ["-I", str(d)]
    incs += ["-I", str(out)]
    cbs = str(out / (module + ".cbs"))
    print("  compile (the SOUND gate)...")
    r = subprocess.run([clang, "-fsyntax-only", "-Wno-nullability-completeness"]
                       + incs + [cbs], stderr=subprocess.PIPE)
    if r.returncode != 0:
        print("  COMPILE RED (no repair loop — that's the engine):\n"
              + r.stderr.decode()[-1500:])
        return False
    print("  COMPILE GREEN")
    if not smoke.is_file():
        print("  (no smoke.cbs — skipping runtime floor)")
        return True
    impls = sorted(str(f) for f in libcbs.rglob("*.cbs"))
    b = str(out / "smoke_bin")
    print("  smoke test...")
    r = subprocess.run([clang, "-Wno-nullability-completeness"] + incs
                       + [cbs, str(smoke)] + impls + ["-lpthread", "-lm", "-o", b],
                       stderr=subprocess.PIPE)
    if r.returncode != 0:
        print("  smoke link failed:\n" + r.stderr.decode()[-1000:])
        return False
    r = subprocess.run([b])
    print("  smoke exit=%d" % r.returncode)
    return r.returncode == 0


if __name__ == "__main__":
    main()
