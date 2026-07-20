#!/usr/bin/env python3
"""export_workflow_md — render a forgeflow workflow as a processable Markdown
document: YAML frontmatter (name/consumes/emits) + a step table (block,
actor, routing) + a mermaid graph + per-step detail. The result is both
human-readable and machine-parseable (frontmatter + tables), so it fits a
markdown-level workflow-processing pipeline — or an agent reading the
palette.

  scripts/export_workflow_md.py code_gen
  scripts/export_workflow_md.py --all --out run/docs/workflows
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, "/home/ziruichen/bsd/forgeflow")
from forgeflow import config, loader           # noqa: E402
from forgeflow import blocks as bm             # noqa: E402

_TERMINALS = {"done", "failed", "parked", "deferred"}


def _actor(block):
    if block.name == "human.ask":
        return "human"
    if block.exec_class == "llm":
        return "model"
    return "machinery"


def render(wf):
    L = []
    # --- frontmatter: the machine-processable header ---
    L += ["---", "workflow: %s" % wf.kind,
          "consumes: [%s]" % ", ".join(wf.consumes),
          "emits: [%s]" % ", ".join(wf.emits),
          "steps: %d" % len(wf.steps), "---", ""]
    L += ["# workflow: `%s`" % wf.kind, "",
          "Consumes **%s** → emits **%s**." %
          (", ".join(wf.consumes) or "(none)", ", ".join(wf.emits) or "(none)"),
          ""]

    # --- step table: block, actor, and every outcome's target ---
    L += ["## Steps", "",
          "| # | step | block | actor | outcome → next |",
          "|---|------|-------|-------|----------------|"]
    for i, s in enumerate(wf.steps):
        routes = []
        for (sn, outcome), target in sorted(wf.dispatch.items()):
            if sn == s.name:
                routes.append("`%s`→%s" % (outcome, target))
        L.append("| %d | %s | `%s` | %s | %s |" %
                 (i + 1, s.name, s.block.name, _actor(s.block),
                  " · ".join(routes)))
    L += [""]

    # --- mermaid graph: the visual, also markdown-native ---
    def nid(n):
        return n.replace("-", "_")
    L += ["## Graph", "", "```mermaid", "flowchart TD"]
    for s in wf.steps:
        targets = {t for (sn, _o), t in wf.dispatch.items() if sn == s.name}
        branch = len(targets) >= 2 or s.block.name == "human.ask"
        shape = "{%s}" if branch else "[%s]"
        L.append('  %s%s' % (nid(s.name), shape % s.name))
    seen = set()
    for (sn, outcome), target in sorted(wf.dispatch.items()):
        edge = (sn, target)
        if target in _TERMINALS:
            L.append('  %s -->|%s| %s([%s])' % (nid(sn), outcome, target, target))
        else:
            L.append('  %s -->|%s| %s' % (nid(sn), outcome, nid(target)))
    L += ["```", ""]

    # --- per-step detail: params + context (what each step is fed) ---
    L += ["## Step detail", ""]
    for s in wf.steps:
        L.append("### `%s`" % s.name)
        doc = (s.block.fn.__doc__ or "").strip().split("\n")[0].strip()
        L.append("- **block:** `%s` — %s" % (s.block.name, doc))
        if s.llm:
            L.append("- **agent:** `%s` (schema `%s`)" % (s.llm, s.schema))
        if s.params:
            L.append("- **params:** %s" % ", ".join(
                "`%s`" % k for k in sorted(s.params)))
        if s.context:
            L.append("- **context:** %s" % ", ".join(
                "`%s`" % c for c, _ in s.context))
        L.append("- **timeout:** %ds · **max visits:** %d" %
                 (s.timeout_s, s.max_visits))
        L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workflow", nargs="?")
    ap.add_argument("--pack", default="/home/ziruichen/bsd/bsc-sdd")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    pack = config.load_pack(a.pack)
    bm.load_files(pack.block_files)
    wfs = loader.load_defs(pack.workflow_dirs, pack=pack)
    names = sorted(wfs) if a.all else [a.workflow]
    for n in names:
        md = render(wfs[n])
        if a.out:
            p = Path(a.out) / ("%s.md" % n)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(md)
            print("wrote", p)
        else:
            print(md)


if __name__ == "__main__":
    main()
