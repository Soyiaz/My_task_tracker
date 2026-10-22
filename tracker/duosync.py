"""Keep this tracker's tasks and the duo tracker's in step, both ways.

The duo tracker (the Telegram bot, the website, the Android app and its
widgets) is one hub: every spoke reads and writes the same API. This module
makes the tracker one more spoke:

- **Out.** Every task here with a day from today on goes to the duo tracker
  as a one-time task on that day, for you (or for both of you, if you say
  so), unless you switch it off for that task. From then on renaming it,
  moving it, giving it a time, ticking it or deleting it here does the same
  there, and a day or deletion changed there comes back here.
- **In.** Your duo tasks for today (and yesterday while it is still open)
  come into this tracker as tasks on that day, filed under the track whose
  name matches the duo area — the plan's areas are this tracker's tracks —
  or under a *Duo* track otherwise. Whatever happens to them on the website,
  the bot or a widget — ticked, undone, renamed, re-timed, deleted — shows
  here on the next pull; ticking them here counts there.

The link between a task here and an occurrence there (duo task id + day)
lives in the ``duo_links`` setting, so no table changes. Pulling happens at
most once a minute per session and never blocks the page for long: the duo
API is read with an 8 s timeout and every failure is swallowed.
"""

from __future__ import annotations

import json
import time
from datetime import date

import streamlit as st

from tracker import db, duo, planning, scoring

KEY = "duo_links"
PULL_EVERY = 60  # seconds, per session
IMPORT_MINUTES = 30  # the planned length of a task that came in from duo
DUO_TRACK = ("duo", "Duo", ":material/group:", "#3B6FE0", "Shared with the duo tracker.")

# Duo occurrence status -> this tracker's task status.
IN_STATUS = {"done": "done", "pending": "todo", "missed": "dropped", "ignored": "dropped", "excused": "dropped"}

_pulling = False  # while a pull writes tasks, nothing is pushed back out


# --- the links -----------------------------------------------------------------


def links() -> dict[int, dict]:
    """{tracker task id: {"task": duo task id, "day": "YYYY-MM-DD",
    "origin": "tracker" | "duo" | "off", "gone": bool}}

    ``origin: off`` means "never send this one"; ``gone`` means it was
    deleted here and must not come back."""
    try:
        raw = json.loads(db.get_setting(KEY) or "{}")
    except ValueError:
        raw = {}
    out = {}
    for k, v in raw.items():
        try:
            if isinstance(v, dict) and v.get("task"):
                out[int(k)] = v
        except (TypeError, ValueError):
            continue
    return out


def _save(data: dict[int, dict]) -> None:
    db.set_setting(KEY, json.dumps({str(k): v for k, v in sorted(data.items())}))


def link_for(task_id: int) -> dict | None:
    return links().get(int(task_id))


def on_duo(link: dict | None) -> bool:
    """A live link: the task is on Duo right now."""
    return bool(link) and link.get("origin") != "off" and not link.get("gone")


def opt_out(task_id: int) -> None:
    """Keep this task off Duo, now and on later pulls."""
    data = links()
    data[int(task_id)] = {"task": "off", "day": "", "origin": "off"}
    _save(data)


def set_link(task_id: int, duo_task_id: str, day: str, origin: str) -> None:
    data = links()
    data[int(task_id)] = {"task": str(duo_task_id), "day": day, "origin": origin}
    _save(data)


def unlink(task_id: int) -> None:
    data = links()
    if data.pop(int(task_id), None) is not None:
        _save(data)


def _by_occurrence(data: dict[int, dict]) -> dict[tuple[str, str], int]:
    return {(v["task"], v["day"]): k for k, v in data.items() if v.get("origin") != "off"}


# --- where an incoming task is filed ------------------------------------------------


def _track_for(area: str | None) -> int:
    """The track named like the duo area, else the Duo track (made on demand)."""
    tracks = scoring.tracks()
    if area:
        hit = tracks[tracks["name"].str.strip().str.lower() == str(area).strip().lower()]
        if len(hit):
            return int(hit.iloc[0]["id"])
    row = db.one("SELECT id FROM tracks WHERE key = ?", (DUO_TRACK[0],))
    if row:
        return int(row["id"])
    nxt = int(db.query("SELECT COALESCE(MAX(sort), 0) + 1 AS n FROM tracks")["n"].iloc[0])
    return db.execute(
        "INSERT INTO tracks(key, name, icon, color, goal, target_share, sort) VALUES (?, ?, ?, ?, ?, 0, ?)",
        (*DUO_TRACK, nxt),
    )


# --- out: this tracker -> duo ----------------------------------------------------------


def send(task_id: int, both: bool = False) -> str:
    """Create the duo task for a task made here and link the two. Raises
    duo.DuoError when the duo tracker says no."""
    t = planning.get_task(task_id)
    if t is None:
        raise duo.DuoError("That task is gone.")
    if on_duo(link_for(task_id)):
        return "Already on Duo."
    day = t["day"] or date.today().isoformat()
    me = duo.me()
    if not me:
        raise duo.DuoError("The duo password was refused.")
    assigned = [me] + ([duo.partner_id()] if both and duo.partner_id() else [])
    created = duo.create_task(
        t["title"], day, planning.task_times().get(int(task_id)), assigned, area=t.get("track") or "",
    )
    set_link(task_id, created["_id"], day, "tracker")
    duo.refresh()
    return "Also added to Duo" + (" for both of you" if len(assigned) > 1 else "")


def push_edit(task_id: int, fields: dict) -> None:
    """After a task changed here: carry the name, day and time over."""
    if _pulling:
        return
    link = link_for(task_id)
    if not on_duo(link) or not duo.active():
        return
    body: dict = {}
    if "title" in fields and fields["title"]:
        body["name"] = fields["title"]
    sched: dict = {}
    if "time" in fields:
        sched["time"] = fields["time"] or None
    if "day" in fields and fields["day"] and link["origin"] == "tracker":
        sched["date"] = fields["day"]
        link["day"] = fields["day"]
    if sched:
        body["schedule"] = sched
    if not body:
        return
    try:
        duo.update_task(link["task"], body)
        data = links()
        data[int(task_id)] = link
        _save(data)
        duo.refresh()
    except duo.DuoError as exc:
        st.toast(f"Duo tracker not updated: {exc}", icon=":material/sync_problem:")


def push_delete(task_id: int) -> None:
    """Before a task is deleted here: a task that started here is deleted
    there too; one that came from duo is left alone there (it may be a
    recurring task) and simply not brought back today."""
    if _pulling:
        return
    link = link_for(task_id)
    if not on_duo(link):
        return
    if link["origin"] == "tracker" and duo.active():
        try:
            duo.delete_task(link["task"])
            duo.refresh()
        except duo.DuoError as exc:
            st.toast(f"Duo tracker not updated: {exc}", icon=":material/sync_problem:")
    data = links()
    data[int(task_id)] = {**link, "gone": True}
    _save(data)


def remove(task_id: int) -> str:
    """Take a task off Duo without deleting it here, and keep it off."""
    link = link_for(task_id)
    if on_duo(link):
        push_delete(task_id)
    opt_out(task_id)
    return "Taken off Duo."


# --- in: duo -> this tracker ------------------------------------------------------------


def _my_occurrences(board: dict, me: str) -> list[dict]:
    member = next((m for m in board["members"] if m["userId"] == me), None)
    if member is None:
        return []
    return list(member.get("yesterdayPending", [])) + list(member["items"])


def pull(force: bool = False) -> dict:
    """Bring today's duo tasks in and apply what changed there. Cheap when
    called often: at most one real pull a minute per session."""
    global _pulling
    counts = {"new": 0, "updated": 0, "removed": 0}
    if not duo.active():
        return counts
    now = time.time()
    if not force and now - float(st.session_state.get("_duo_pull_at", 0)) < PULL_EVERY:
        return counts
    st.session_state["_duo_pull_at"] = now

    try:
        board = duo.board()
        me = duo.me()
    except duo.DuoError:
        return counts
    if not me:
        return counts

    occurrences = {
        (str(o["taskId"]), o["date"]): o for o in _my_occurrences(board, me) if o.get("status") != "void"
    }
    # The occurrence carries a snapshot of the task's name and time; the task
    # itself is what the website edits, so prefer it when it can be read.
    try:
        live = {str(t["_id"]): t for t in duo.tasks()}
    except duo.DuoError:
        live = {}
    for (duo_task_id, _), o in occurrences.items():
        t = live.get(duo_task_id)
        if t:
            o["taskName"] = t.get("name") or o["taskName"]
            o["time"] = (t.get("schedule") or {}).get("time") or o.get("time")
    data = links()
    seen = _by_occurrence(data)
    today = board["today"]
    times = planning.task_times()

    _pulling = True
    try:
        # The task itself changed there: moved to another day, or deleted.
        if live:
            for tid, link in list(data.items()):
                if not on_duo(link) or link["origin"] != "tracker":
                    continue
                lt = live.get(link["task"])
                if lt is None:
                    # Deleted on the website or in the app.
                    t = planning.get_task(tid)
                    if t is not None and t["status"] == "todo":
                        planning.delete_task(tid)
                        counts["removed"] += 1
                    data.pop(tid, None)
                    continue
                when = str((lt.get("schedule") or {}).get("date") or "")[:10]
                if when and when != link["day"]:
                    planning.update_task(tid, day=when)
                    link["day"] = when
                    counts["updated"] += 1

        # What is there: bring in, or bring up to date.
        for (duo_task_id, day), o in occurrences.items():
            tid = seen.get((duo_task_id, day))
            if tid is not None:
                link = data[tid]
                if link.get("gone"):
                    continue  # deleted here on purpose; stays there
                t = planning.get_task(tid)
                if t is None:
                    data.pop(tid, None)
                    continue
                changed = False
                want = IN_STATUS.get(o["status"], "todo")
                if t["status"] != want and not (want == "todo" and t["status"] == "doing"):
                    planning.update_task(tid, status=want)
                    changed = True
                if o["taskName"] and o["taskName"] != t["title"]:
                    planning.update_task(tid, title=o["taskName"])
                    changed = True
                if o.get("time") and o["time"] != times.get(tid):
                    planning.set_task_time(tid, o["time"])
                    changed = True
                counts["updated"] += int(changed)
                continue
            # New here: file it on that day, under the matching track.
            tid = planning.add_task(
                scoring.week_start(date.fromisoformat(day)),
                _track_for(o.get("area")),
                o["taskName"],
                IMPORT_MINUTES,
                day=date.fromisoformat(day),
            )
            if o.get("time"):
                planning.set_task_time(tid, o["time"])
            want = IN_STATUS.get(o["status"], "todo")
            if want != "todo":
                planning.update_task(tid, status=want)
            data[tid] = {"task": duo_task_id, "day": day, "origin": "duo"}
            counts["new"] += 1

        # What is gone from duo today: a task that came from there and was
        # never started here goes too. Yesterday is left alone - its tasks
        # drop off the board when the day closes, which is not a deletion.
        for tid, link in list(data.items()):
            if link.get("origin") == "off":
                continue
            if link.get("gone"):
                if link["day"] < today:
                    data.pop(tid, None)  # old enough to forget
                continue
            if link["day"] != today or (link["task"], link["day"]) in occurrences:
                continue
            t = planning.get_task(tid)
            if t is None:
                data.pop(tid, None)
            elif link["origin"] == "duo" and t["status"] == "todo":
                planning.delete_task(tid)
                data.pop(tid, None)
                counts["removed"] += 1
            else:
                data.pop(tid, None)  # keep the task here, just unlinked
        _save(data)

        # Everything here with a day from today on is on Duo too.
        me_id = me
        for r in planning.board().to_dict("records"):
            tid = int(r["id"])
            if tid in data or r["status"] not in ("todo", "doing") or not r.get("day"):
                continue
            day = r["day"] if isinstance(r["day"], str) else str(r["day"])[:10]
            if day < today:
                continue
            try:
                created = duo.create_task(
                    r["title"], day, times.get(tid), [me_id], area=r.get("track") or "",
                )
            except duo.DuoError:
                break  # the duo tracker is unhappy; try again next pull
            data[tid] = {"task": created["_id"], "day": day, "origin": "tracker"}
            counts["sent"] = counts.get("sent", 0) + 1
        _save(data)
    finally:
        _pulling = False

    if counts["new"]:
        st.toast(f"{counts['new']} task{'s' if counts['new'] != 1 else ''} came in from Duo", icon=":material/sync:")
    if counts.get("sent"):
        st.toast(f"{counts['sent']} task{'s' if counts['sent'] != 1 else ''} sent to Duo", icon=":material/sync:")
    return counts

