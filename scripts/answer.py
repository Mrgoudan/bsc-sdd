#!/usr/bin/env python3
"""The CLI half of the requirement dialogue (the board panel is the web half).

List the questions the pipeline is waiting on, answer them, and resume:

  answer.py --db run/state/forgeflow.db --feature CJSON-P1            # list
  answer.py --db ... --feature CJSON-P1 --set Q-1=replace
  answer.py --db ... --feature CJSON-P1 --accept-defaults             # take all recommendations

Answering the last open blocking question UNPARKS the waiting spec_author task
(fresh attempt): the agent re-runs with the full dialogue in its context and
either proceeds or asks follow-ups — that is the multi-turn loop.

Needs the engine on PYTHONPATH for the auto-unpark (the launcher's default).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--feature", required=True)
    ap.add_argument("--stage", help="decompose | author (default: all stages)")
    ap.add_argument("--set", action="append", default=[], metavar="Q-ID=ANSWER")
    ap.add_argument("--accept-defaults", action="store_true",
                    help="answer every open question with its recommendation")
    a = ap.parse_args()

    conn = sqlite3.connect(a.db)
    conn.row_factory = sqlite3.Row
    stage_sql = " AND stage=?" if a.stage else ""
    stage_arg = [a.stage] if a.stage else []

    changed = 0
    for kv in a.set:
        qk, _, ans = kv.partition("=")
        if not ans:
            sys.exit("--set wants Q-ID=ANSWER, got %r" % kv)
        changed += conn.execute(
            "UPDATE dialogue SET answer=?, answered_by='user',"
            " answered_at=datetime('now')"
            " WHERE feature_key=? AND q_key=?" + stage_sql,
            [ans, a.feature, qk] + stage_arg).rowcount

    if a.accept_defaults:
        changed += conn.execute(
            "UPDATE dialogue SET answer=recommended, answered_by='user',"
            " answered_at=datetime('now')"
            " WHERE feature_key=? AND answer IS NULL AND recommended IS NOT NULL"
            + stage_sql, [a.feature] + stage_arg).rowcount
    conn.commit()

    open_rows = conn.execute(
        "SELECT stage, q_key, question, options, recommended FROM dialogue"
        " WHERE feature_key=? AND answer IS NULL" + stage_sql + " ORDER BY id",
        [a.feature] + stage_arg).fetchall()
    if open_rows:
        print("open questions (%d):" % len(open_rows))
        for r in open_rows:
            print("  [%s/%s] %s" % (r["stage"], r["q_key"], r["question"]))
            opts = ", ".join(json.loads(r["options"] or "[]"))
            if opts:
                print("        options: %s   (recommended: %s)"
                      % (opts, r["recommended"]))
        print("\nanswer with: --set %s=<answer>" % open_rows[0]["q_key"])
        return

    print("no open questions%s"
          % (" (%d answered just now)" % changed if changed else ""))
    if changed:
        try:
            from forgeflow import queue
        except ImportError:
            sys.exit("answers recorded; set PYTHONPATH to the engine to auto-unpark")
        row = conn.execute(
            "SELECT id FROM tasks WHERE kind='spec_author' AND state='parked'"
            " AND payload LIKE ? ORDER BY id DESC LIMIT 1",
            ('%"feature_key": "' + a.feature + '"%',)).fetchone()
        if row:
            queue.unpark(conn, task_id=row["id"])
            conn.commit()
            print("unparked spec_author task %d — the daemon resumes it" % row["id"])
        else:
            print("no parked spec_author task found (nothing waiting on answers)")


if __name__ == "__main__":
    main()
