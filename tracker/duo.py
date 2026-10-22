"""Duo: the shared tracker Lily and Zen run together, seen from here.

The duo tracker is a separate app — a Telegram bot, a website and an Android
app over one API — where the two of them share tasks, a weekly duel that
starts at 100 XP and only goes down, and a calendar of how each day went.
This module is the bridge to it:

- reading the shared board (both people's day, the duel, the week, goals)
  for the Duo page, and marking Lily's own duo tasks from there;
- mirroring ticks made here: when a task on this tracker is named exactly
  like one of today's duo tasks, finishing it here finishes it there too.

Nothing in this tracker's own database changes. Without the ``[duo]``
secrets every function is a no-op and the Duo page shows setup steps.
"""

from __future__ import annotations

import os
import time
from datetime import date, timedelta

import requests
import streamlit as st

from tracker import cloud

TIMEOUT = 8  # seconds — the bridge must never hold up a tick for long

# This tracker's task statuses → the duo action that mirrors them. "Dropped"
# (not happening today) becomes an excuse, which costs no XP but is limited.
MIRROR = {"done": "done", "todo": "undo", "dropped": "excused"}

_tokens: dict = {}  # password -> (token, expiry); one per duo account


def _token_slot() -> dict:
    return _tokens.setdefault(str(_settings().get("password")), {"value": None, "expires": 0.0})


# --- configuration -----------------------------------------------------------


def _settings() -> dict:
    """The duo credentials for this session.

    ``[duo]`` carries the server address and, for a single-user install, one
    password. With accounts, each person has their own duo password under
    ``[duo.accounts]`` keyed by their email, and the signed-in account's entry
    wins — so Li's ticks land on Lily's duo side and Zen's on Zen's."""
    try:
        base = dict(st.secrets["duo"]) if "duo" in st.secrets else None
    except Exception:
        base = None
    if base is None:
        base = {
            "url": os.environ.get("DUO_URL"),
            "password": os.environ.get("DUO_PASSWORD"),
            "email": os.environ.get("DUO_EMAIL"),
        }
    accounts = {str(k).strip().lower(): dict(v) for k, v in (base.pop("accounts", None) or {}).items()}
    if accounts and cloud.enabled():
        me_ = (cloud.current_email() or "").strip().lower()
        own = accounts.get(me_)
        if own:
            return {**base, **own, "email": me_}
        # Accounts are configured but this one is not among them: no bridge.
        base.pop("password", None)
    return base


def configured() -> bool:
    s = _settings()
    return bool(s.get("url") and s.get("password"))


def _base() -> str:
    url = str(_settings().get("url") or "").strip().rstrip("/")
    return url[:-4] if url.endswith("/api") else url


def active() -> bool:
    """Configured, and — in a hosted deployment with accounts — only for the
    account the duo password belongs to, so nobody else's ticks land there."""
    if not configured():
        return False
    owner = str(_settings().get("email") or "").strip().lower()
    if not owner or not cloud.enabled():
        return True
    return (cloud.current_email() or "").strip().lower() == owner


# --- the API -----------------------------------------------------------------


class DuoError(Exception):
    pass


def _login() -> str:
    _token = _token_slot()
    if _token["value"] and time.time() < _token["expires"]:
        return _token["value"]
    r = requests.post(
        f"{_base()}/api/auth/login",
        json={"password": _settings().get("password")},
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        raise DuoError("The duo password was refused.")
    _token["value"] = r.json()["token"]
    _token["expires"] = time.time() + 7 * 86400  # tokens last 90 days; renew weekly
    return _token["value"]


def _request(method: str, path: str, body: dict | None = None, auth: bool = False):
    headers = {"X-Client": "streamlit"}
    if auth:
        headers["Authorization"] = f"Bearer {_login()}"
    try:
        r = requests.request(method, f"{_base()}{path}", json=body, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise DuoError("The duo tracker could not be reached.") from exc
    if r.status_code == 401 and auth:
        _token_slot()["value"] = None  # expired or rotated: log in again once
        return _request(method, path, body, auth)
    data = r.json() if r.content else {}
    if not r.ok:
        raise DuoError(data.get("error") or f"The duo tracker answered {r.status_code}.")
    return data


def me() -> str | None:
    """The duo member id this tracker acts as (from the login token)."""
    try:
        return _request("GET", "/api/auth/me", auth=True)["telegramId"]
    except DuoError:
        return None


@st.cache_data(ttl=30, show_spinner=False)
def board() -> dict:
    return _request("GET", "/api/board")


@st.cache_data(ttl=60, show_spinner=False)
def week() -> dict:
    return _request("GET", "/api/week")


@st.cache_data(ttl=120, show_spinner=False)
def month(year: int, month_: int) -> dict:
    first = date(year, month_, 1)
    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return _request("GET", f"/api/range?from={first.isoformat()}&to={last.isoformat()}")


@st.cache_data(ttl=60, show_spinner=False)
def structure() -> list[dict]:
    """The plan as the duo tracker holds it: [{owner, area, items}]."""
    return _request("GET", "/api/structure")


def push_structure(rows: list[dict]) -> list[dict]:
    """Replace the duo tracker's plan with these rows (owner li / zen / lizen,
    area, items). The website's Plan page and the app's Tasks tab read it."""
    out = _request("PUT", "/api/structure", rows, auth=True)
    structure.clear()
    return out


def refresh() -> None:
    board.clear()
    week.clear()
    month.clear()
    structure.clear()
    tasks.clear()


def mark(task_id: str, day: str, action: str, amount: int = 1) -> dict:
    out = _request(
        "POST",
        "/api/occurrences/mark",
        {"taskId": task_id, "date": day, "action": action, "amount": amount},
        auth=True,
    )
    refresh()
    return out


def partner_id() -> str | None:
    """The other member's duo id."""
    try:
        mine = me()
        return next((m["userId"] for m in board()["members"] if m["userId"] != mine), None)
    except DuoError:
        return None


@st.cache_data(ttl=60, show_spinner=False)
def tasks() -> list[dict]:
    return _request("GET", "/api/tasks")


def create_task(name: str, day: str, time_: str | None, assigned: list[str], area: str = "") -> dict:
    """A one-time duo task on that day, for the given members."""
    body = {
        "name": name, "type": "one-time", "assignedTo": assigned,
        "schedule": {"date": day, **({"time": time_} if time_ else {})},
        "startDate": day, "area": area, "description": "From the plan tracker",
    }
    out = _request("POST", "/api/tasks", body, auth=True)
    refresh()
    return out


def update_task(task_id: str, body: dict) -> dict:
    out = _request("PUT", f"/api/tasks/{task_id}", body, auth=True)
    refresh()
    return out


def delete_task(task_id: str) -> None:
    _request("DELETE", f"/api/tasks/{task_id}", auth=True)
    refresh()


def contribute(goal_id: str, amount: float, note: str = "") -> dict:
    out = _request("POST", f"/api/goals/{goal_id}/contribute", {"amount": amount, "note": note}, auth=True)
    refresh()
    return out


# --- the bridge --------------------------------------------------------------


def _norm(s: str) -> str:
    return " ".join(str(s).lower().split())


def mirror_status(title: str, day: str | None, status: str, duo_task_id: str | None = None) -> str | None:
    """Best effort: apply the same outcome to the linked duo occurrence, or
    failing a link, to one of your duo tasks on that day carrying the same
    name. Returns a short note for the UI, or None when nothing matched.
    Never raises."""
    action = MIRROR.get(status)
    if not action or not active():
        return None
    try:
        b = board()
        mine = me()
        member = next((m for m in b["members"] if m["userId"] == mine), None)
        if member is None:
            return None
        day = day or b["today"]
        candidates = member["items"] + member.get("yesterdayPending", [])
        match = None
        if duo_task_id:
            match = next((o for o in candidates if str(o["taskId"]) == str(duo_task_id) and o["date"] == day), None)
        if match is None:
            match = next(
                (o for o in candidates if o["date"] == day and _norm(o["taskName"]) == _norm(title)),
                None,
            )
        if match is None or (action == "undo" and match["status"] == "pending"):
            return None
        mark(match["taskId"], day, action)
        return f"Also marked in the duo tracker: {match['taskName']}"
    except DuoError as exc:
        return f"Duo tracker not updated: {exc}"
    except Exception:
        return None
