"""The daily journal: six questions, answered like a chat, kept in Neon.

This is deliberately a separate database from the tracker. The tracker's
SQLite file (local disk or Supabase bucket) is never touched — journal
entries live in a Neon Postgres project, keyed by the same anonymous
account id the cloud tracker uses, so the two sit side by side without
sharing a schema.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pandas as pd

from tracker import cloud

# key, the question the bot asks, section label, icon
QUESTIONS = [
    (
        "grateful",
        "What are you grateful for right now — things, people, anything at all?",
        "Grateful for",
        ":material/favorite:",
    ),
    (
        "focus",
        "What do you have to do today? Name the main focus.",
        "Today's focus",
        ":material/center_focus_strong:",
    ),
    (
        "feeling",
        "How are you feeling right now — and where is that coming from?",
        "Feeling",
        ":material/mood:",
    ),
    (
        "yesterday",
        "What happened yesterday worth keeping — something amazing, funny, hard?",
        "Yesterday",
        ":material/history:",
    ),
    (
        "progress",
        "What is going well at the moment — the thing in good progress?",
        "Going well",
        ":material/trending_up:",
    ),
    (
        "better",
        "And how can you make it better?",
        "Make it better",
        ":material/auto_awesome:",
    ),
]
KEYS = [k for k, _, _, _ in QUESTIONS]


# --- where the journal lives -------------------------------------------------


def _url() -> str | None:
    try:
        import streamlit as st

        if "neon" in st.secrets and st.secrets["neon"].get("url"):
            return str(st.secrets["neon"]["url"])
    except Exception:
        pass
    return os.environ.get("NEON_URL") or None


def configured() -> bool:
    return _url() is not None


def uid() -> str | None:
    """Who this journal belongs to.

    Signed-in cloud accounts get the same anonymous id their tracker uses.
    The shared demo gets no journal — a diary read by strangers is not a
    diary. A local install is single-owner, so 'local' is enough.
    """
    if not cloud.enabled():
        return "local"
    email = cloud.current_email()
    return cloud._uid_for(email) if email else None


# --- talking to Neon ---------------------------------------------------------
# Connections are opened per operation: a journal sees a handful of writes a
# day, and Neon's pooled endpoint makes short connections cheap — far cheaper
# than nursing a long-lived connection through Streamlit reruns.

_schema_done = False


def _connect():
    import psycopg

    return psycopg.connect(_url(), connect_timeout=10)


def ensure_schema() -> None:
    global _schema_done
    if _schema_done:
        return
    cols = ", ".join(f"{k} TEXT NOT NULL DEFAULT ''" for k in KEYS)
    with _connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS journal_entries ("
            "id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, "
            "user_id TEXT NOT NULL, "
            "day DATE NOT NULL, "
            f"{cols}, "
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
            "UNIQUE (user_id, day))"
        )
    _schema_done = True


def save_entry(user_id: str, day: date, answers: dict[str, str]) -> None:
    ensure_schema()
    cols = ", ".join(KEYS)
    slots = ", ".join(["%s"] * len(KEYS))
    updates = ", ".join(f"{k} = EXCLUDED.{k}" for k in KEYS)
    values = [str(answers.get(k, "")).strip() for k in KEYS]
    with _connect() as conn:
        conn.execute(
            f"INSERT INTO journal_entries (user_id, day, {cols}) "
            f"VALUES (%s, %s, {slots}) "
            "ON CONFLICT (user_id, day) DO UPDATE "
            f"SET {updates}, updated_at = now()",
            [user_id, day, *values],
        )


def entry_for(user_id: str, day: date) -> dict | None:
    ensure_schema()
    cols = ", ".join(KEYS)
    with _connect() as conn:
        row = conn.execute(
            f"SELECT day, {cols}, created_at FROM journal_entries "
            "WHERE user_id = %s AND day = %s",
            [user_id, day],
        ).fetchone()
    if row is None:
        return None
    out = {"day": row[0], "created_at": row[-1]}
    out.update(dict(zip(KEYS, row[1:-1])))
    return out


def entries(user_id: str, limit: int = 366) -> pd.DataFrame:
    ensure_schema()
    cols = ", ".join(KEYS)
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT day, {cols}, created_at FROM journal_entries "
            "WHERE user_id = %s ORDER BY day DESC LIMIT %s",
            [user_id, limit],
        ).fetchall()
    return pd.DataFrame(rows, columns=["day", *KEYS, "created_at"])


def delete_entry(user_id: str, day: date) -> None:
    ensure_schema()
    with _connect() as conn:
        conn.execute(
            "DELETE FROM journal_entries WHERE user_id = %s AND day = %s",
            [user_id, day],
        )


# --- small pure helpers ------------------------------------------------------


def streak(days: set[date], today: date) -> int:
    """Consecutive journaled days, counting back from today — or from
    yesterday, so the streak is not broken before today's entry is written."""
    d = today if today in days else today - timedelta(days=1)
    n = 0
    while d in days:
        n += 1
        d -= timedelta(days=1)
    return n
