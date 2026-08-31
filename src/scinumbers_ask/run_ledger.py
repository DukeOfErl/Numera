"""Spend accumulated by a run, keyed by the run's label.

A run is not a session, and the run budget's job is to bound what a run of
questions can cost -- an evaluation set most of all. Run spend used to live in the
session's checkpoint, so a driver opening a session per question started every
question at zero and the budget bounded nothing at all.

Kept in the same file as the checkpoints, under its own table: one file is one
thing for a caller to manage, and the checkpointer's own tables are untouched.

Increments are written as deltas with SQL doing the addition, so two processes
working on one run cannot lose each other's spend to a read-modify-write.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing

TABLE = "run_spend"


def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {TABLE} (run TEXT PRIMARY KEY, micro INTEGER NOT NULL)"
    )
    conn.commit()
    return conn


def read(path: str, run: str) -> int:
    """What this run has spent so far. Absent means nothing, not unknown."""
    with closing(_connect(path)) as conn:
        row = conn.execute(f"SELECT micro FROM {TABLE} WHERE run = ?", (run,)).fetchone()
    return int(row[0]) if row else 0


def add(path: str, run: str, micro: int) -> None:
    """Add to this run's total, atomically.

    A delta rather than a new total: the caller's in-memory figure may be stale by
    the time it is written, and overwriting with it would discard whatever another
    process in the same run recorded meanwhile.
    """
    if not micro:
        return
    with closing(_connect(path)) as conn:
        conn.execute(
            f"INSERT INTO {TABLE} (run, micro) VALUES (?, ?) "
            "ON CONFLICT(run) DO UPDATE SET micro = micro + excluded.micro",
            (run, micro),
        )
        conn.commit()
