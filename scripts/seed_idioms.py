#!/usr/bin/env python3
"""Seed the bsc_idioms RAG corpus into a state DB from data/idioms.jsonl.
Idempotent (INSERT OR REPLACE by id). Run once against the daemon's state DB:

  python3 scripts/seed_idioms.py --db run/state/forgeflow.db --dir data
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def seed(db, path):
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE IF NOT EXISTS bsc_idioms"
                 " (id TEXT PRIMARY KEY, title TEXT NOT NULL, pattern TEXT NOT NULL, tags TEXT)")
    n = 0
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        conn.execute("INSERT OR REPLACE INTO bsc_idioms(id, title, pattern, tags)"
                     " VALUES (?,?,?,?)", (d["id"], d["title"], d["pattern"], d.get("tags")))
        n += 1
    conn.commit()
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--dir", default="data")
    a = ap.parse_args()
    n = seed(a.db, str(Path(a.dir) / "idioms.jsonl"))
    print("seeded %d idioms into %s" % (n, a.db))
