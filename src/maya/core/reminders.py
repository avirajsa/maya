"""Persistent local reminders for Maya.

The worker must be started by Maya's application and supplied a callback that
routes due reminders into Maya's existing speech/event pipeline.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
import sqlite3
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = Path(os.getenv("MAYA_REMINDERS_DB", str(PROJECT_ROOT / "data" / "reminders.sqlite3")))
TIMEZONE = ZoneInfo(os.getenv("MAYA_TIMEZONE", "Asia/Kolkata"))
ReminderCallback = Callable[[dict], Awaitable[None]]


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            scheduled_at TEXT NOT NULL,
            recurrence TEXT NOT NULL DEFAULT 'once',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            last_delivered_at TEXT
        )
    """)
    conn.commit()
    return conn


def create_reminder(message: str, scheduled_at: str, recurrence: str = "once") -> dict:
    """Create reminder using an ISO-8601 timestamp. recurrence: once/daily/weekly."""
    if not message.strip():
        raise ValueError("Reminder message cannot be empty")
    if recurrence not in {"once", "daily", "weekly"}:
        raise ValueError("recurrence must be once, daily, or weekly")
    dt = datetime.fromisoformat(scheduled_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TIMEZONE)
    if dt <= datetime.now(TIMEZONE):
        raise ValueError("Reminder time must be in the future")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO reminders(message, scheduled_at, recurrence, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
            (message.strip(), dt.astimezone(TIMEZONE).isoformat(), recurrence, datetime.now(TIMEZONE).isoformat()),
        )
        row = conn.execute("SELECT * FROM reminders WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)


def list_reminders(include_delivered: bool = False) -> list[dict]:
    with _connect() as conn:
        if include_delivered:
            rows = conn.execute("SELECT * FROM reminders ORDER BY scheduled_at").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE status='pending' ORDER BY scheduled_at"
            ).fetchall()
        return [dict(row) for row in rows]


def cancel_reminder(reminder_id: int) -> dict:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM reminders WHERE id=?", (reminder_id,)).fetchone()
        if not row:
            return {"id": reminder_id, "cancelled": False, "reason": "not found"}
        conn.execute("UPDATE reminders SET status='cancelled' WHERE id=?", (reminder_id,))
        return {"id": reminder_id, "message": row["message"], "cancelled": True}


def snooze_reminder(reminder_id: int, minutes: int = 10) -> dict:
    if not 1 <= minutes <= 10080:
        raise ValueError("Snooze must be between 1 minute and 7 days")
    scheduled = (datetime.now(TIMEZONE) + timedelta(minutes=minutes)).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE reminders SET scheduled_at=?, status='pending' WHERE id=? AND status IN ('pending','delivered')",
            (scheduled, reminder_id),
        )
        if cur.rowcount == 0:
            return {"id": reminder_id, "snoozed": False, "reason": "reminder not found"}
        return {"id": reminder_id, "scheduled_at": scheduled, "snoozed": True}


async def run_reminder_worker(on_due: ReminderCallback, poll_seconds: int = 10) -> None:
    """Run until cancelled. on_due(reminder) must speak/dispatch it before returning."""
    if poll_seconds < 1:
        raise ValueError("poll_seconds must be at least 1")
    logger.info("Maya reminder worker started; DB=%s", DB_PATH)
    while True:
        now = datetime.now(TIMEZONE)
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE status='pending' AND scheduled_at<=? ORDER BY scheduled_at",
                (now.isoformat(),),
            ).fetchall()
        for raw in rows:
            reminder = dict(raw)
            try:
                await on_due(reminder)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Failed to deliver reminder id=%s; it will retry", reminder["id"])
                continue
            delivered_at = datetime.now(TIMEZONE)
            with _connect() as conn:
                current = conn.execute("SELECT status, recurrence, scheduled_at FROM reminders WHERE id=?",
                                       (reminder["id"],)).fetchone()
                if not current or current["status"] != "pending":
                    continue
                if current["recurrence"] == "once":
                    conn.execute("UPDATE reminders SET status='delivered', last_delivered_at=? WHERE id=?",
                                 (delivered_at.isoformat(), reminder["id"]))
                else:
                    interval = timedelta(days=1 if current["recurrence"] == "daily" else 7)
                    next_dt = datetime.fromisoformat(current["scheduled_at"])
                    while next_dt <= delivered_at:
                        next_dt += interval
                    conn.execute("UPDATE reminders SET scheduled_at=?, last_delivered_at=? WHERE id=?",
                                 (next_dt.isoformat(), delivered_at.isoformat(), reminder["id"]))
        await asyncio.sleep(poll_seconds)
