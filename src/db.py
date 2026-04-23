"""Tiny SQLite layer to remember which events we already notified about."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "state.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notified (
            event_id TEXT PRIMARY KEY,
            ts       INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS platform_status (
            platform TEXT PRIMARY KEY,
            last_ok  INTEGER,
            last_err TEXT
        )
        """
    )
    return conn


def already_notified(event_id: str) -> bool:
    with _conn() as c:
        row = c.execute(
            "SELECT 1 FROM notified WHERE event_id = ?", (event_id,)
        ).fetchone()
        return row is not None


def mark_notified(event_id: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO notified(event_id, ts) VALUES (?, ?)",
            (event_id, int(time.time())),
        )


def prune_old(window_hours: int) -> None:
    cutoff = int(time.time()) - window_hours * 3600
    with _conn() as c:
        c.execute("DELETE FROM notified WHERE ts < ?", (cutoff,))


def record_status(platform: str, ok: bool, err: str = "") -> None:
    now = int(time.time())
    with _conn() as c:
        if ok:
            c.execute(
                "INSERT INTO platform_status(platform, last_ok, last_err) VALUES (?, ?, '') "
                "ON CONFLICT(platform) DO UPDATE SET last_ok=excluded.last_ok, last_err=''",
                (platform, now),
            )
        else:
            c.execute(
                "INSERT INTO platform_status(platform, last_ok, last_err) VALUES (?, NULL, ?) "
                "ON CONFLICT(platform) DO UPDATE SET last_err=excluded.last_err",
                (platform, err[:500]),
            )


def get_status() -> list[tuple[str, int | None, str]]:
    with _conn() as c:
        return list(
            c.execute("SELECT platform, last_ok, last_err FROM platform_status")
        )
