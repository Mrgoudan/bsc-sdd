#!/usr/bin/env python3
"""Migrate an existing bsc-sdd state DB to the current pack schema.

The engine applies schema/schema.sql with CREATE TABLE IF NOT EXISTS, which
adds new TABLES but never new COLUMNS — so a DB created by an older pack
version silently lacks columns the code now queries (and crashes). This script
is the pack's column-migration path: idempotent ALTERs, safe to run every
launch (the launcher calls it before exec'ing the engine).

  python3 scripts/migrate_db.py --db run/state/forgeflow.db
"""
from __future__ import annotations

import argparse
import sqlite3

# (table, column, ALTER clause) — append-only; never edit past entries.
MIGRATIONS = [
    ("contracts", "hash",
     "ALTER TABLE contracts ADD COLUMN hash TEXT"),
    ("contract_assertions", "discharged_by",
     "ALTER TABLE contract_assertions ADD COLUMN discharged_by TEXT NOT NULL DEFAULT 'llm'"),
    ("codegen_units", "attempts",
     "ALTER TABLE codegen_units ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0"),
    ("codegen_units", "last_error",
     "ALTER TABLE codegen_units ADD COLUMN last_error TEXT"),
]


def migrate(db):
    conn = sqlite3.connect(db)
    applied = []
    for table, col, ddl in MIGRATIONS:
        if not conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                            (table,)).fetchone():
            continue                       # table not there yet: schema.sql will create it complete
        cols = {r[1] for r in conn.execute('PRAGMA table_info("%s")' % table)}
        if col not in cols:
            conn.execute(ddl)
            applied.append("%s.%s" % (table, col))
    conn.commit()
    return applied


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    a = ap.parse_args()
    applied = migrate(a.db)
    print("migrated: %s" % (", ".join(applied) if applied else "nothing to do"))
