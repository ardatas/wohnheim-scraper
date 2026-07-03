from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .models import Residence
from .utils import now_iso


SCHEMA = """
CREATE TABLE IF NOT EXISTS residences (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  city TEXT DEFAULT '',
  address TEXT DEFAULT '',
  email TEXT DEFAULT '',
  phone TEXT DEFAULT '',
  url TEXT DEFAULT '',
  source_url TEXT DEFAULT '',
  notes TEXT DEFAULT '',
  eligibility TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active',
  priority INTEGER NOT NULL DEFAULT 3,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(name, address, url)
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  residence_id INTEGER NOT NULL REFERENCES residences(id) ON DELETE CASCADE,
  sequence INTEGER NOT NULL,
  kind TEXT NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  scheduled_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  eml_path TEXT DEFAULT '',
  generated_at TEXT NOT NULL,
  approved_at TEXT DEFAULT '',
  sent_at TEXT DEFAULT '',
  error TEXT DEFAULT '',
  UNIQUE(residence_id, sequence)
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_residence(conn: sqlite3.Connection, residence: Residence) -> int:
    now = now_iso()
    existing = find_existing(conn, residence)
    if existing:
        conn.execute(
            """
            UPDATE residences
            SET category = COALESCE(NULLIF(?, ''), category),
                city = COALESCE(NULLIF(?, ''), city),
                address = COALESCE(NULLIF(?, ''), address),
                email = COALESCE(NULLIF(?, ''), email),
                phone = COALESCE(NULLIF(?, ''), phone),
                url = COALESCE(NULLIF(?, ''), url),
                source_url = COALESCE(NULLIF(?, ''), source_url),
                notes = trim(COALESCE(notes, '') || CASE WHEN ? != '' AND instr(COALESCE(notes, ''), ?) = 0 THEN char(10) || ? ELSE '' END),
                eligibility = COALESCE(NULLIF(?, ''), eligibility),
                status = CASE WHEN status = 'closed' THEN status ELSE COALESCE(NULLIF(?, ''), status) END,
                priority = MIN(priority, ?),
                updated_at = ?
            WHERE id = ?
            """,
            (
                residence.category,
                residence.city,
                residence.address,
                residence.email,
                residence.phone,
                residence.url,
                residence.source_url,
                residence.notes,
                residence.notes,
                residence.notes,
                residence.eligibility,
                residence.status,
                residence.priority,
                now,
                existing["id"],
            ),
        )
        conn.commit()
        return int(existing["id"])

    cur = conn.execute(
        """
        INSERT INTO residences (
          name, category, city, address, email, phone, url, source_url, notes,
          eligibility, status, priority, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            residence.name,
            residence.category,
            residence.city,
            residence.address,
            residence.email,
            residence.phone,
            residence.url,
            residence.source_url,
            residence.notes,
            residence.eligibility,
            residence.status,
            residence.priority,
            now,
            now,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def find_existing(conn: sqlite3.Connection, residence: Residence) -> sqlite3.Row | None:
    if residence.url:
        row = conn.execute(
            "SELECT * FROM residences WHERE lower(url) = lower(?) AND lower(name) = lower(?)",
            (residence.url, residence.name),
        ).fetchone()
        if row:
            return row
    if residence.email:
        row = conn.execute(
            "SELECT * FROM residences WHERE lower(email) = lower(?) AND lower(name) = lower(?)",
            (residence.email, residence.name),
        ).fetchone()
        if row:
            return row
    row = conn.execute(
        """
        SELECT * FROM residences
        WHERE lower(name) = lower(?)
          AND (lower(address) = lower(?) OR address = '' OR ? = '')
        """,
        (residence.name, residence.address, residence.address),
    ).fetchone()
    return row


def list_residences(conn: sqlite3.Connection, include_inactive: bool = False) -> list[sqlite3.Row]:
    where = "" if include_inactive else "WHERE status != 'closed'"
    return list(
        conn.execute(
            f"""
            SELECT * FROM residences
            {where}
            ORDER BY category, priority, name
            """
        )
    )


def get_residence(conn: sqlite3.Connection, residence_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM residences WHERE id = ?", (residence_id,)).fetchone()


def next_sequence(conn: sqlite3.Connection, residence_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(sequence), -1) + 1 AS next_seq FROM messages WHERE residence_id = ?",
        (residence_id,),
    ).fetchone()
    return int(row["next_seq"])


def add_message(
    conn: sqlite3.Connection,
    residence_id: int,
    sequence: int,
    kind: str,
    subject: str,
    body: str,
    scheduled_at: str,
    eml_path: str = "",
) -> int:
    now = now_iso()
    cur = conn.execute(
        """
        INSERT OR REPLACE INTO messages (
          residence_id, sequence, kind, subject, body, scheduled_at, status,
          eml_path, generated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?)
        """,
        (residence_id, sequence, kind, subject, body, scheduled_at, eml_path, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_messages(conn: sqlite3.Connection, status: str | None = None) -> list[sqlite3.Row]:
    if status:
        return list(
            conn.execute(
                """
                SELECT m.*, r.name, r.email, r.category
                FROM messages m
                JOIN residences r ON r.id = m.residence_id
                WHERE m.status = ?
                ORDER BY m.scheduled_at, r.priority, r.name
                """,
                (status,),
            )
        )
    return list(
        conn.execute(
            """
            SELECT m.*, r.name, r.email, r.category
            FROM messages m
            JOIN residences r ON r.id = m.residence_id
            ORDER BY m.scheduled_at, r.priority, r.name
            """
        )
    )


def get_message(conn: sqlite3.Connection, message_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT m.*, r.name, r.email, r.category, r.address, r.url
        FROM messages m
        JOIN residences r ON r.id = m.residence_id
        WHERE m.id = ?
        """,
        (message_id,),
    ).fetchone()


def update_message_status(
    conn: sqlite3.Connection,
    message_id: int,
    status: str,
    extra: dict[str, Any] | None = None,
) -> None:
    extra = extra or {}
    fields = ["status = ?"]
    values: list[Any] = [status]
    for key, value in extra.items():
        fields.append(f"{key} = ?")
        values.append(value)
    values.append(message_id)
    conn.execute(f"UPDATE messages SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()


def last_sent_message(conn: sqlite3.Connection, residence_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM messages
        WHERE residence_id = ? AND status = 'sent' AND sent_at != ''
        ORDER BY sent_at DESC, sequence DESC
        LIMIT 1
        """,
        (residence_id,),
    ).fetchone()


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else default
