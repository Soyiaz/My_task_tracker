"""The journal, over Telegram.

A background thread long-polls Telegram from inside the running app, so the
bot needs no server of its own — it lives and dies with the deployment. All
conversation state sits in Neon, so a reboot mid-conversation loses nothing.

The gate: a new chat must give the access code before anything answers.
Then email + password — sign up once, and the email decides which journal
the entries land in. Use the same email as the website's Google login and
the bot and the site share one journal; any other email is its own.
"""

from __future__ import annotations

import hashlib
import json
import secrets as pysecrets
import threading
import time as _time
from datetime import date, timedelta

import requests

from tracker import cloud, journal

POLL_TIMEOUT = 50

MENU = (
    "What now?\n\n"
    "journal — write today's entry\n"
    "read — read a day you wrote\n"
    "days — the days you have written\n"
    "logout — switch accounts"
)


def _config() -> dict | None:
    try:
        import streamlit as st

        if "telegram" in st.secrets and st.secrets["telegram"].get("token"):
            return dict(st.secrets["telegram"])
    except Exception:
        pass
    return None


def configured() -> bool:
    return _config() is not None and journal.configured()


# --- state in Neon -----------------------------------------------------------

_schema_done = False


def ensure_schema() -> None:
    global _schema_done
    if _schema_done:
        return
    journal.ensure_schema()
    with journal._connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS journal_users ("
            "email TEXT PRIMARY KEY, salt TEXT NOT NULL, pw_hash TEXT NOT NULL, "
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS bot_chats ("
            "chat_id BIGINT PRIMARY KEY, stage TEXT NOT NULL DEFAULT 'gate', "
            "email TEXT, uid TEXT, answers TEXT NOT NULL DEFAULT '{}', "
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS bot_state ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
    _schema_done = True


def _chat(chat_id: int) -> dict:
    with journal._connect() as conn:
        row = conn.execute(
            "SELECT chat_id, stage, email, uid, answers FROM bot_chats WHERE chat_id = %s",
            [chat_id],
        ).fetchone()
    if row is None:
        with journal._connect() as conn:
            conn.execute(
                "INSERT INTO bot_chats (chat_id) VALUES (%s) ON CONFLICT DO NOTHING",
                [chat_id],
            )
        return {"chat_id": chat_id, "stage": "gate", "email": None, "uid": None, "answers": {}}
    return {
        "chat_id": row[0],
        "stage": row[1],
        "email": row[2],
        "uid": row[3],
        "answers": json.loads(row[4] or "{}"),
    }


def _save_chat(c: dict) -> None:
    with journal._connect() as conn:
        conn.execute(
            "UPDATE bot_chats SET stage = %s, email = %s, uid = %s, answers = %s, "
            "updated_at = now() WHERE chat_id = %s",
            [c["stage"], c["email"], c["uid"], json.dumps(c["answers"]), c["chat_id"]],
        )


def _get_state(key: str) -> str | None:
    with journal._connect() as conn:
        row = conn.execute("SELECT value FROM bot_state WHERE key = %s", [key]).fetchone()
    return row[0] if row else None


def _set_state(key: str, value: str) -> None:
    with journal._connect() as conn:
        conn.execute(
            "INSERT INTO bot_state (key, value) VALUES (%s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            [key, value],
        )


# --- accounts ----------------------------------------------------------------


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()


def _create_user(email: str, password: str) -> bool:
    salt = pysecrets.token_hex(8)
    try:
        with journal._connect() as conn:
            conn.execute(
                "INSERT INTO journal_users (email, salt, pw_hash) VALUES (%s, %s, %s)",
                [email, salt, _hash(password, salt)],
            )
        return True
    except Exception:
        return False  # already registered


def _check_user(email: str, password: str) -> bool:
    with journal._connect() as conn:
        row = conn.execute(
            "SELECT salt, pw_hash FROM journal_users WHERE email = %s", [email]
        ).fetchone()
    if row is None:
        return False
    return pysecrets.compare_digest(_hash(password, row[0]), row[1])


def _user_exists(email: str) -> bool:
    with journal._connect() as conn:
        return (
            conn.execute("SELECT 1 FROM journal_users WHERE email = %s", [email]).fetchone()
            is not None
        )


# --- formatting --------------------------------------------------------------


def _format_entry(entry: dict) -> str:
    d = entry["day"]
    d = d if isinstance(d, date) else date.fromisoformat(str(d))
    lines = [f"📖 {d:%A %d %B %Y}", ""]
    for k, _, label, _ in journal.QUESTIONS:
        text = str(entry.get(k, "") or "").strip()
        if text:
            lines.append(f"— {label} —")
            lines.append(text)
            lines.append("")
    return "\n".join(lines).strip()


def _recent_days(uid: str, n: int = 10) -> list[date]:
    df = journal.entries(uid, limit=n)
    return [
        d if isinstance(d, date) else date.fromisoformat(str(d)) for d in df["day"]
    ]


def _parse_day(text: str) -> date | None:
    t = text.strip().lower()
    if t == "today":
        return date.today()
    if t == "yesterday":
        return date.today() - timedelta(days=1)
    try:
        return date.fromisoformat(t)
    except ValueError:
        return None


# --- the conversation --------------------------------------------------------


def handle_text(chat_id: int, text: str) -> str:
    """One incoming message in, one reply out. Everything the bot is."""
    ensure_schema()
    c = _chat(chat_id)
    t = (text or "").strip()
    cmd = t.lstrip("/").lower()

    # the gate comes before everything
    if c["stage"] == "gate":
        if t == str(_config().get("access_code", "")):
            c["stage"] = "auth"
            _save_chat(c)
            return (
                "You're in. 🎐\n\n"
                "This journal is per account. Reply:\n"
                "signup — first time here\n"
                "login — already registered\n\n"
                "Tip: use the same email you sign into the website with, "
                "and the bot and the site share one journal."
            )
        return "Access code?"

    if cmd == "start":
        if c["uid"]:
            return f"Back again. Signed in as {c['email']}.\n\n{MENU}"
        c["stage"] = "auth"
        _save_chat(c)
        return "signup or login?"

    # --- authentication ---
    if c["stage"] == "auth":
        if cmd == "signup":
            c["stage"] = "signup_email"
            _save_chat(c)
            return "Your email? (Use the website's Google email to share one journal.)"
        if cmd == "login":
            c["stage"] = "login_email"
            _save_chat(c)
            return "Your email?"
        return "signup or login?"

    if c["stage"] in ("signup_email", "login_email"):
        email = t.lower()
        if "@" not in email or " " in email or len(email) < 5:
            return "That does not look like an email. Try again."
        if c["stage"] == "signup_email" and _user_exists(email):
            c["stage"] = "login_pw"
            c["email"] = email
            _save_chat(c)
            return "That email is already registered — password?"
        c["email"] = email
        c["stage"] = "signup_pw" if c["stage"] == "signup_email" else "login_pw"
        _save_chat(c)
        return "And a password?" if c["stage"] == "signup_pw" else "Password?"

    if c["stage"] == "signup_pw":
        if len(t) < 6:
            return "At least 6 characters, please."
        if not _create_user(c["email"], t):
            c["stage"] = "login_pw"
            _save_chat(c)
            return "That email is already registered — password?"
        c["uid"] = cloud._uid_for(c["email"])
        c["stage"] = "menu"
        _save_chat(c)
        return f"Registered. This is {c['email']}'s journal now.\n\n{MENU}"

    if c["stage"] == "login_pw":
        if not _check_user(c["email"], t):
            return "Wrong password. Try again, or send /start to switch email."
        c["uid"] = cloud._uid_for(c["email"])
        c["stage"] = "menu"
        _save_chat(c)
        return f"Welcome back, {c['email']}.\n\n{MENU}"

    # --- everything below needs an account ---
    if not c["uid"]:
        c["stage"] = "auth"
        _save_chat(c)
        return "signup or login?"

    if cmd == "logout":
        c.update({"stage": "auth", "email": None, "uid": None, "answers": {}})
        _save_chat(c)
        return "Logged out. signup or login?"

    # --- journaling ---
    if c["stage"] == "menu":
        if cmd == "journal":
            note = ""
            if journal.entry_for(c["uid"], date.today()):
                note = "(Today is already written — finishing this rewrites it.)\n\n"
            c["stage"] = "q0"
            c["answers"] = {}
            _save_chat(c)
            return f"{note}{date.today():%A, %d %B}.\n\n1/6 · {journal.QUESTIONS[0][1]}"
        if cmd == "read":
            c["stage"] = "read_day"
            _save_chat(c)
            return "Which day? Send a date like 2026-08-24, or today / yesterday."
        if cmd == "days":
            days = _recent_days(c["uid"])
            if not days:
                return "Nothing written yet. Send journal to start today's."
            listing = "\n".join(f"• {d.isoformat()} ({d:%a})" for d in days)
            return f"Your latest entries:\n{listing}\n\nSend read to open one."
        return MENU

    if c["stage"] == "read_day":
        if cmd == "cancel":
            c["stage"] = "menu"
            _save_chat(c)
            return MENU
        d = _parse_day(t)
        if d is None:
            return "Send a date like 2026-08-24, or today / yesterday. (cancel to stop)"
        entry = journal.entry_for(c["uid"], d)
        c["stage"] = "menu"
        _save_chat(c)
        if entry is None:
            days = _recent_days(c["uid"], 5)
            hint = (
                "\nDays you did write: " + ", ".join(x.isoformat() for x in days)
                if days
                else ""
            )
            return f"Nothing written on {d.isoformat()}.{hint}\n\n{MENU}"
        return _format_entry(entry)

    if c["stage"].startswith("q"):
        if cmd == "cancel":
            c["stage"] = "menu"
            c["answers"] = {}
            _save_chat(c)
            return f"Dropped. Nothing saved.\n\n{MENU}"
        i = int(c["stage"][1:])
        if not t:
            return journal.QUESTIONS[i][1]
        c["answers"][journal.KEYS[i]] = t
        if i + 1 < len(journal.QUESTIONS):
            c["stage"] = f"q{i + 1}"
            _save_chat(c)
            return f"{i + 2}/6 · {journal.QUESTIONS[i + 1][1]}"
        journal.save_entry(c["uid"], date.today(), c["answers"])
        c["stage"] = "menu"
        c["answers"] = {}
        _save_chat(c)
        days = {
            d if isinstance(d, date) else date.fromisoformat(str(d))
            for d in journal.entries(c["uid"], 60)["day"]
        }
        run = journal.streak(days, date.today())
        return (
            f"Saved. 📖 That's {run} day{'s' if run != 1 else ''} in a row.\n"
            "See you tomorrow — or read it on the website's Journal page."
        )

    c["stage"] = "menu"
    _save_chat(c)
    return MENU


# --- telegram plumbing -------------------------------------------------------


def _api(method: str, **params):
    token = _config()["token"]
    r = requests.post(
        f"https://api.telegram.org/bot{token}/{method}", json=params, timeout=POLL_TIMEOUT + 10
    )
    return r.json()


def _loop() -> None:
    ensure_schema()
    offset = int(_get_state("tg_offset") or 0)
    while True:
        try:
            resp = _api("getUpdates", offset=offset + 1, timeout=POLL_TIMEOUT)
            for u in resp.get("result", []):
                offset = max(offset, int(u["update_id"]))
                msg = u.get("message") or {}
                chat_id = (msg.get("chat") or {}).get("id")
                text = msg.get("text")
                if chat_id is None or text is None:
                    continue
                try:
                    reply = handle_text(int(chat_id), text)
                except Exception as e:  # a broken turn must not kill the bot
                    reply = f"Something went wrong on my side ({type(e).__name__}). Try again."
                _api("sendMessage", chat_id=chat_id, text=reply)
            if resp.get("result"):
                _set_state("tg_offset", str(offset))
        except Exception:
            _time.sleep(5)  # network hiccup — breathe, then poll again


_thread: threading.Thread | None = None
_lock = threading.Lock()


def ensure_running() -> None:
    """Start the polling thread once per process. Safe to call every rerun."""
    global _thread
    if not configured():
        return
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        _thread = threading.Thread(target=_loop, name="journal-bot", daemon=True)
        _thread.start()
