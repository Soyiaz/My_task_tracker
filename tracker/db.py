"""SQLite storage for the summer tracker.

One file, ``tracker.db``, next to the app, with uploaded artefacts alongside
it in ``files/``. Connections are opened per operation rather than shared: the
database is local and tiny, and a fresh connection per call keeps Streamlit's
rerun threads out of trouble.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "tracker.db"
FILES_DIR = ROOT / "files"


def _session_value(key: str):
    """A per-user override set by cloud mode (tracker/cloud.py). Outside a
    Streamlit session — tests, bare scripts — there is none, and the module
    paths stand. One process serves every visitor in a deployment, so the
    override has to live in session state, never in a module global."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        if get_script_run_ctx(suppress_warning=True) is None:
            return None
        import streamlit as st

        return st.session_state.get(key)
    except Exception:
        return None


def db_path() -> Path:
    override = _session_value("_user_db_path")
    return Path(override) if override else DB_PATH


def files_dir() -> Path:
    override = _session_value("_user_files_dir")
    return Path(override) if override else FILES_DIR


def _mark_dirty() -> None:
    """Tell cloud mode this user's database changed, so it gets parked in
    remote storage at the end of the run. A no-op everywhere else."""
    try:
        from tracker import cloud

        cloud.mark_dirty()
    except Exception:
        pass

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id           INTEGER PRIMARY KEY,
    key          TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    icon         TEXT NOT NULL DEFAULT '',
    color        TEXT NOT NULL DEFAULT '#6366f1',
    goal         TEXT NOT NULL DEFAULT '',
    target_share REAL NOT NULL DEFAULT 0.15,
    sort         INTEGER NOT NULL DEFAULT 0
);

-- What kind of work it was, inside a track.
CREATE TABLE IF NOT EXISTS categories (
    id       INTEGER PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    key      TEXT NOT NULL,
    name     TEXT NOT NULL,
    requires TEXT NOT NULL DEFAULT '',
    domains  TEXT NOT NULL DEFAULT '',
    sort     INTEGER NOT NULL DEFAULT 0,
    UNIQUE (track_id, key)
);

CREATE TABLE IF NOT EXISTS subcategories (
    id          INTEGER PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    key         TEXT NOT NULL,
    name        TEXT NOT NULL,
    domains     TEXT NOT NULL DEFAULT '',
    sort        INTEGER NOT NULL DEFAULT 0,
    UNIQUE (category_id, key)
);

-- The lenses the whole summer is measured by, cutting across every track.
CREATE TABLE IF NOT EXISTS domains (
    id           INTEGER PRIMARY KEY,
    key          TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    color        TEXT NOT NULL DEFAULT '#6366f1',
    target_share REAL NOT NULL DEFAULT 0.25,
    sort         INTEGER NOT NULL DEFAULT 0
);

-- Skills, outputs and habits: anything that is simply done or not done.
CREATE TABLE IF NOT EXISTS items (
    id       INTEGER PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    section  TEXT NOT NULL DEFAULT '',
    name     TEXT NOT NULL,
    kind     TEXT NOT NULL DEFAULT 'skill',
    weight   REAL NOT NULL DEFAULT 1.0,
    status   TEXT NOT NULL DEFAULT 'todo',
    notes    TEXT NOT NULL DEFAULT '',
    sort     INTEGER NOT NULL DEFAULT 0,
    done_on  TEXT
);

-- The things that end up in the portfolio: boards, automations, 3D assets.
CREATE TABLE IF NOT EXISTS projects (
    id         INTEGER PRIMARY KEY,
    track_id   INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    category   TEXT NOT NULL DEFAULT '',
    difficulty TEXT NOT NULL DEFAULT 'Intermediate',
    status     TEXT NOT NULL DEFAULT 'todo',
    weight     REAL NOT NULL DEFAULT 3.0,
    domains    TEXT NOT NULL DEFAULT '',
    link       TEXT NOT NULL DEFAULT '',
    notes      TEXT NOT NULL DEFAULT '',
    done_on    TEXT
);

CREATE TABLE IF NOT EXISTS opportunities (
    id     INTEGER PRIMARY KEY,
    name   TEXT NOT NULL,
    kind   TEXT NOT NULL DEFAULT '',
    mode   TEXT NOT NULL DEFAULT 'Remote',
    day    TEXT,
    status TEXT NOT NULL DEFAULT 'idea',
    result TEXT NOT NULL DEFAULT '',
    income REAL NOT NULL DEFAULT 0.0,
    notes  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS books (
    id         INTEGER PRIMARY KEY,
    month      TEXT NOT NULL,
    title      TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'todo',
    reflection TEXT NOT NULL DEFAULT ''
);

-- The week's contract with yourself: what it is for, and how it went.
CREATE TABLE IF NOT EXISTS week_plan (
    week_start  TEXT PRIMARY KEY,
    intention   TEXT NOT NULL DEFAULT '',
    wins        TEXT NOT NULL DEFAULT '',
    blockers    TEXT NOT NULL DEFAULT '',
    next_focus  TEXT NOT NULL DEFAULT '',
    planned_on  TEXT,
    reviewed_on TEXT
);

CREATE TABLE IF NOT EXISTS week_hours (
    week_start TEXT NOT NULL,
    track_id   INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    hours      REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (week_start, track_id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY,
    week_start      TEXT NOT NULL,
    day             TEXT,
    track_id        INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    category_id     INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    subcategory_id  INTEGER REFERENCES subcategories(id) ON DELETE SET NULL,
    title           TEXT NOT NULL,
    domains         TEXT NOT NULL DEFAULT '',
    planned_minutes INTEGER NOT NULL DEFAULT 60,
    status          TEXT NOT NULL DEFAULT 'todo',
    urgent          INTEGER NOT NULL DEFAULT 0,
    milestone_kind  TEXT,
    milestone_id    INTEGER,
    sort            INTEGER NOT NULL DEFAULT 0,
    done_on         TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS ix_tasks_week ON tasks(week_start);
CREATE INDEX IF NOT EXISTS ix_tasks_day ON tasks(day);

CREATE TABLE IF NOT EXISTS time_log (
    id             INTEGER PRIMARY KEY,
    day            TEXT NOT NULL,
    track_id       INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    category_id    INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    subcategory_id INTEGER REFERENCES subcategories(id) ON DELETE SET NULL,
    task_id        INTEGER,
    minutes        INTEGER NOT NULL,
    title          TEXT NOT NULL DEFAULT '',
    purpose        TEXT NOT NULL DEFAULT '',
    detail         TEXT NOT NULL DEFAULT '',
    link           TEXT NOT NULL DEFAULT '',
    domains        TEXT NOT NULL DEFAULT '',
    focus          INTEGER,
    notes          TEXT NOT NULL DEFAULT '',
    source         TEXT NOT NULL DEFAULT 'manual',
    created_at     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS ix_time_log_day ON time_log(day);

-- Uploaded artefacts, kept on disk with a pointer here.
CREATE TABLE IF NOT EXISTS attachments (
    id          INTEGER PRIMARY KEY,
    owner_kind  TEXT NOT NULL,
    owner_id    INTEGER NOT NULL,
    filename    TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    size        INTEGER NOT NULL DEFAULT 0,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS ix_attachments_owner ON attachments(owner_kind, owner_id);

-- At most one running stopwatch, so a single row with a fixed id.
CREATE TABLE IF NOT EXISTS timer (
    id             INTEGER PRIMARY KEY CHECK (id = 1),
    track_id       INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    category_id    INTEGER,
    subcategory_id INTEGER,
    task_id        INTEGER,
    activity       TEXT NOT NULL DEFAULT '',
    domains        TEXT NOT NULL DEFAULT '',
    started_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "start_date": "2026-07-15",
    "end_date": "2026-09-15",
    "weekly_hours": "35",
    "schema_version": str(SCHEMA_VERSION),
}

ALL_TABLES = (
    "attachments",
    "time_log",
    "timer",
    "tasks",
    "week_hours",
    "week_plan",
    "items",
    "projects",
    "opportunities",
    "books",
    "subcategories",
    "categories",
    "domains",
    "tracks",
)


@contextmanager
def connect():
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def execute(sql: str, params: Sequence[Any] = ()) -> int:
    """Run one statement; return the last row id."""
    with connect() as conn:
        cur = conn.execute(sql, params)
        rid = cur.lastrowid
    _mark_dirty()
    return rid


def execute_many(sql: str, rows: Iterable[Sequence[Any]]) -> None:
    with connect() as conn:
        conn.executemany(sql, list(rows))
    _mark_dirty()


def query(sql: str, params: Sequence[Any] = ()) -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql_query(sql, conn, params=tuple(params))


def one(sql: str, params: Sequence[Any] = ()):
    with connect() as conn:
        return conn.execute(sql, params).fetchone()


# --- writing back an edited table -------------------------------------------

NUMERIC_DEFAULTS = {"weight": 1.0, "income": 0.0, "target_share": 0.0}


def _clean(column: str, value):
    """A blank cell in a freshly added row arrives as NaN; SQLite wants a real
    value."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return NUMERIC_DEFAULTS.get(column, "")
    return value


def sync_table(
    table: str,
    original: pd.DataFrame,
    edited: pd.DataFrame,
    defaults: dict | None = None,
    stamp_done: bool = False,
) -> dict:
    """Push a ``st.data_editor`` result back into a table.

    Rows without an id are new, rows that vanished were deleted, the rest are
    updates. With ``stamp_done`` the ``done_on`` date is kept in step with the
    status, so week and month reports can say what was finished when.
    """
    defaults = defaults or {}
    today = date.today().isoformat()
    cols = [c for c in edited.columns if c != "id"]
    counts = {"inserted": 0, "updated": 0, "deleted": 0}
    kept: set[int] = set()

    for row in edited.to_dict("records"):
        values = {c: _clean(c, row[c]) for c in cols}
        rid = row.get("id")
        if rid is None or pd.isna(rid):
            payload = {**defaults, **values}
            if stamp_done and payload.get("status") == "done":
                payload["done_on"] = today
            keys = list(payload)
            execute(
                f"INSERT INTO {table}({','.join(keys)}) "
                f"VALUES ({','.join('?' * len(keys))})",
                [payload[k] for k in keys],
            )
            counts["inserted"] += 1
            continue

        rid = int(rid)
        kept.add(rid)
        sets = ", ".join(f"{c} = ?" for c in values)
        params = list(values.values())
        if stamp_done:
            # Keep an existing completion date, stamp a new one, clear it if
            # the row is reopened.
            sets += ", done_on = CASE WHEN ? = 'done' THEN COALESCE(done_on, ?) END"
            params += [values.get("status", "todo"), today]
        execute(f"UPDATE {table} SET {sets} WHERE id = ?", params + [rid])
        counts["updated"] += 1

    if "id" in original.columns and len(original):
        for rid in set(original["id"].dropna().astype(int)) - kept:
            execute(f"DELETE FROM {table} WHERE id = ?", (int(rid),))
            counts["deleted"] += 1

    return counts


# --- settings ---------------------------------------------------------------


def get_setting(key: str, default: str | None = None) -> str | None:
    row = one("SELECT value FROM settings WHERE key = ?", (key,))
    if row is None:
        return DEFAULT_SETTINGS.get(key, default)
    return row["value"]


def set_setting(key: str, value: Any) -> None:
    execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


# --- lifecycle --------------------------------------------------------------


def _add_missing_columns() -> None:
    """Columns added after a database was first created. ``CREATE TABLE IF NOT
    EXISTS`` leaves an existing table alone, so they go on by hand."""
    later = {
        "tasks": [("urgent", "INTEGER NOT NULL DEFAULT 0")],
    }
    for table, columns in later.items():
        have = {
            r["name"] for r in query(f"PRAGMA table_info({table})").to_dict("records")
        }
        for name, spec in columns:
            if name not in have:
                execute(f"ALTER TABLE {table} ADD COLUMN {name} {spec}")


def init() -> None:
    """Create the schema, and lay down the plan the first time."""
    files_dir().mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
    _add_missing_columns()

    for key, value in DEFAULT_SETTINGS.items():
        if one("SELECT value FROM settings WHERE key = ?", (key,)) is None:
            set_setting(key, value)

    if one("SELECT 1 FROM tracks LIMIT 1") is None:
        from tracker import seed

        seed.plant()


def wipe(keep_log: bool = False) -> None:
    """Delete everything and re-plant. ``keep_log`` is never used by the app —
    the structure and the log are joined at the hip, and half a rebuild would
    leave entries pointing at categories that no longer exist."""
    with connect() as conn:
        for table in ALL_TABLES:
            if keep_log and table in ("time_log", "attachments"):
                continue
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM settings")
    _mark_dirty()
    init()


# Kept for the Settings page, which calls it by the older name.
reset = wipe
