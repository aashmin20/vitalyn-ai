"""
outbox.py — durable local queue for fall events the database could not accept.

A potential-fall alert must not be lost because the cloud database (Supabase) is
unreachable. When the write fails, the event is stored here (a small local SQLite
file) and replayed by flush() once the database is back. Event and alert ids are
generated before the first attempt, so replays are idempotent.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import closing
from typing import Callable, Optional

OUTBOX_PATH = os.getenv(
    "VITALYN_OUTBOX_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "outbox.db"),
)
_lock = threading.Lock()


def _connect(path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or OUTBOX_PATH, timeout=5)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS outbox ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, "
        "payload TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, "
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    return conn


def enqueue(kind: str, payload: dict, path: Optional[str] = None) -> int:
    with _lock, closing(_connect(path)) as conn:
        cur = conn.execute("INSERT INTO outbox (kind, payload) VALUES (?, ?)", (kind, json.dumps(payload)))
        conn.commit()
        return int(cur.lastrowid)


def pending(path: Optional[str] = None) -> int:
    try:
        with _lock, closing(_connect(path)) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0])
    except sqlite3.Error:
        return 0


def flush(handler: Callable[[str, dict], None], path: Optional[str] = None, limit: int = 50) -> int:
    """Replay queued items oldest-first. Stops at the first failure (database still down)."""
    done = 0
    with _lock, closing(_connect(path)) as conn:
        rows = conn.execute("SELECT id, kind, payload FROM outbox ORDER BY id LIMIT ?", (limit,)).fetchall()
        for row_id, kind, payload in rows:
            try:
                handler(kind, json.loads(payload))
            except Exception:
                conn.execute("UPDATE outbox SET attempts = attempts + 1 WHERE id = ?", (row_id,))
                conn.commit()
                break
            conn.execute("DELETE FROM outbox WHERE id = ?", (row_id,))
            conn.commit()
            done += 1
    return done
