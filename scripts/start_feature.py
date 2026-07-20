#!/usr/bin/env python3
"""Read a per-feature config and drive the pipeline: emit spec.requested with
its settings, and apply the declared controls. Keeps run parameters in a file
you version, instead of ad-hoc emit --data.

  start_feature.py --db <db> --projects <dir> --feature CC-RUN [--drive] [--dry]
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, "/home/ziruichen/bsd/forgeflow")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--projects", required=True)
    ap.add_argument("--feature", required=True)
    ap.add_argument("--drive", action="store_true",
                    help="run the one-shot claim loop after emitting (no daemon)")
    ap.add_argument("--dry", action="store_true",
                    help="print the payload, do not emit")
    a = ap.parse_args()

    fdir = Path(a.projects) / a.feature
    cfg_path = fdir / "feature.yaml"
    if not cfg_path.is_file():
        sys.exit("no config: %s" % cfg_path)
    cfg = yaml.safe_load(cfg_path.read_text()) or {}

    fk = cfg.get("feature_key", a.feature)
    req = cfg.get("requirement", "requirement.md")
    req_path = (fdir / req) if not Path(req).is_absolute() else Path(req)
    if not req_path.is_file():
        sys.exit("requirement not found: %s" % req_path)
    def _yn(v):                                # YAML no/yes -> False/True; normalize
        if isinstance(v, bool):
            return "yes" if v else "no"
        return str(v)
    payload = {"feature_key": fk,
               "requirement": req_path.read_text(),
               "base": str(cfg.get("base", "main")),
               "tdd": _yn(cfg.get("tdd", "no"))}

    if a.dry:
        print("would emit spec.requested for %s:" % fk)
        print("  base=%s tdd=%s answers=%s" %
              (payload["base"], payload["tdd"], cfg.get("answers", "auto")))
        print("  requirement: %d bytes from %s" %
              (len(payload["requirement"]), req_path))
        return

    from forgeflow import db, config, engine
    pack = config.load_pack("/home/ziruichen/bsd/bsc-sdd")
    root = Path(a.db).parent.parent            # <root>/state/forgeflow.db
    eng = engine.Engine(root, pack=pack)
    ev = db.emit_event(eng.conn, "spec.requested", payload, eng.subscriptions)
    print("emitted spec.requested (event %s) for %s" % (ev, fk))

    # control: auto-answer non-blocking questions (assumptions) if asked
    if str(cfg.get("answers", "auto")).lower() == "auto":
        print("controls: answers=auto (agent defaults taken on non-blocking Qs)")

    if a.drive:
        print("driving the one-shot claim loop (no daemon)...")
        n = eng.run_until_idle(workers=pack.concurrency.get("workers", 1) or 1)
        print("executed %d task(s); run `... status %s` to see where it is" % (n, fk))


if __name__ == "__main__":
    main()
