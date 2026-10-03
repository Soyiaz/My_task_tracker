"""Everything with a date, in one feed.

Tasks, application deadlines, planned application days, exams, lectures and
study sessions all live in different places. The calendar wants them as one
list, and so do the reminders. This module is that list — plus the small
"jump" mechanism that lets a block on the calendar open the page where the
thing was saved, with that thing pulled to the top.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from tracker import opps, planning, school, scoring, store

# kind -> how it is drawn and where it lives
KINDS = {
    "task": {
        "label": "Task",
        "icon": ":material/task_alt:",
        "color": "#6366f1",
        "page": "app_pages/todo.py",
        "page_title": "To do",
    },
    "deadline": {
        "label": "Application deadline",
        "icon": ":material/alarm:",
        "color": "#e11d48",
        "page": "app_pages/opportunities.py",
        "page_title": "Opportunities",
    },
    "apply": {
        "label": "Apply (planned / opens)",
        "icon": ":material/send:",
        "color": "#f97316",
        "page": "app_pages/opportunities.py",
        "page_title": "Opportunities",
    },
    "exam": {
        "label": "Exam / test",
        "icon": ":material/school:",
        "color": "#7c3aed",
        "page": "app_pages/school.py",
        "page_title": "School",
    },
    "lecture": {
        "label": "Lecture",
        "icon": ":material/co_present:",
        "color": "#0ea5e9",
        "page": "app_pages/school.py",
        "page_title": "School",
    },
    "study": {
        "label": "Study session",
        "icon": ":material/menu_book:",
        "color": "#059669",
        "page": "app_pages/school.py",
        "page_title": "School",
    },
}

COLUMNS = [
    "key", "kind", "id", "title", "subtitle", "day", "time", "minutes",
    "color", "done", "page", "detail", "sort_time",
]

JUMP_KEY = "agenda_jump"


def _row(kind: str, rid, title: str, day: date, at: str | None, minutes: int,
         subtitle: str = "", color: str | None = None, done: bool = False,
         detail: str = "") -> dict:
    return {
        "key": f"{kind}:{rid}",
        "kind": kind,
        "id": rid,
        "title": title,
        "subtitle": subtitle,
        "day": day,
        "time": at,
        "minutes": int(minutes),
        "color": color or KINDS[kind]["color"],
        "done": bool(done),
        "page": KINDS[kind]["page"],
        "detail": detail,
        "sort_time": at or "99:99",
    }


def events(start: date, end: date, kinds: set[str] | None = None) -> pd.DataFrame:
    """Every dated thing between ``start`` and ``end`` inclusive."""
    kinds = kinds or set(KINDS)
    rows: list[dict] = []

    if "task" in kinds:
        tasks = planning.tasks()
        times = planning.task_times()
        if len(tasks):
            tasks = tasks[tasks["day"].notna()]
            for t in tasks.to_dict("records"):
                d = store.as_date(t["day"])
                if d is None or d < start or d > end:
                    continue
                sub = t["track"] + (f" · {t['category']}" if t["category"] else "")
                rows.append(
                    _row(
                        "task", int(t["id"]), t["title"], d, times.get(int(t["id"])),
                        int(t["planned_minutes"]), sub, t["color"],
                        t["status"] == "done",
                        f"{planning.STATUS_UI.get(t['status'], t['status'])}"
                        + (" · urgent" if t.get("urgent") else ""),
                    )
                )

    if "deadline" in kinds or "apply" in kinds:
        for o in opps.all_rows():
            closed = o["status"] not in opps.OPEN
            if "deadline" in kinds and o["deadline"] and start <= o["deadline"] <= end:
                rows.append(
                    _row(
                        "deadline", o["id"], f"Deadline: {o['name']}", o["deadline"],
                        o["deadline_time"], 30, o["category"]
                        + (f" · {o['organisation']}" if o["organisation"] else ""),
                        None, closed, o["status"],
                    )
                )
            if "apply" in kinds:
                if o["apply_on"] and start <= o["apply_on"] <= end:
                    rows.append(
                        _row(
                            "apply", o["id"], f"Apply: {o['name']}", o["apply_on"],
                            o["apply_time"], 60, "Planned application day", None,
                            o["status"] not in opps.OPEN, o["status"],
                        )
                    )
                elif o["apply_from"] and start <= o["apply_from"] <= end:
                    rows.append(
                        _row(
                            "apply", o["id"], f"Opens: {o['name']}", o["apply_from"],
                            None, 30, "Applications open", None, closed, o["status"],
                        )
                    )

    names = school.course_names() if kinds & {"exam", "lecture", "study"} else {}
    colors = {c["id"]: c["color"] for c in school.courses(include_archived=True)}

    if "exam" in kinds:
        for e in school.exams():
            if e["day"] and start <= e["day"] <= end:
                rows.append(
                    _row(
                        "exam", e["id"], f"{e['kind']}: {e['title']}", e["day"], e["time"],
                        e["minutes"] or 90, names.get(e["course_id"], "?")
                        + (f" · {e['location']}" if e["location"] else ""),
                        None, e["status"] == "Done", e["topics"],
                    )
                )

    if "lecture" in kinds:
        for i, L in enumerate(school.lecture_occurrences(start, end)):
            rows.append(
                _row(
                    "lecture", f"{L['course_id']}-{L['day'].isoformat()}", L["course"],
                    L["day"], L["time"], L["minutes"],
                    "Lecture" + (f" · {L['room']}" if L["room"] else ""),
                    L["color"], L["day"] < date.today(), "",
                )
            )

    if "study" in kinds:
        for s in school.sessions():
            if s["day"] and start <= s["day"] <= end:
                rows.append(
                    _row(
                        "study", s["id"], f"Study: {names.get(s['course_id'], '?')}",
                        s["day"], s["time"], s["minutes"], s["topic"] or "Study session",
                        colors.get(s["course_id"]), s["done"], "",
                    )
                )

    df = pd.DataFrame(rows, columns=COLUMNS)
    if len(df):
        df = df.sort_values(["day", "sort_time", "kind"]).reset_index(drop=True)
    return df


def events_on(day: date) -> pd.DataFrame:
    return events(day, day)


# --- reminders --------------------------------------------------------------


def due_soon(days: int = 14, today: date | None = None) -> list[dict]:
    """What is closing, opening or being sat within ``days`` — the things
    the dashboard should put in your face."""
    today = today or date.today()
    out = []
    for o in opps.upcoming(days, today):
        if o["what"] == "deadline":
            when = o["deadline"]
            out.append(
                {
                    "kind": "deadline", "id": o["id"], "title": o["name"],
                    "subtitle": f"{o['category']} · deadline",
                    "when": when, "time": o["deadline_time"], "days_left": o["days_left"],
                    "color": KINDS["deadline"]["color"], "page": KINDS["deadline"]["page"],
                    "reqs": f"{sum(1 for q in o['requirements'] if q['done'])}/{len(o['requirements'])}"
                    if o["requirements"] else "",
                }
            )
        else:
            out.append(
                {
                    "kind": "apply", "id": o["id"], "title": o["name"],
                    "subtitle": f"{o['category']} · planned application day",
                    "when": o["apply_on"], "time": o["apply_time"], "days_left": o["days_left"],
                    "color": KINDS["apply"]["color"], "page": KINDS["apply"]["page"], "reqs": "",
                }
            )
    names = school.course_names()
    for e in school.upcoming_exams(days, today):
        out.append(
            {
                "kind": "exam", "id": e["id"], "title": f"{e['kind']}: {e['title']}",
                "subtitle": names.get(e["course_id"], "?"),
                "when": e["day"], "time": e["time"], "days_left": e["days_left"],
                "color": KINDS["exam"]["color"], "page": KINDS["exam"]["page"], "reqs": "",
            }
        )
    out.sort(key=lambda r: (r["days_left"], r["time"] or "99:99"))
    return out


# --- jumping from the calendar to the page the thing lives on ---------------


def go(kind: str, rid, source: str = "calendar") -> None:
    """Remember what was clicked and switch to its page. The page pops the
    note with ``take_jump`` and shows that item first."""
    if kind not in KINDS:
        return
    st.session_state[JUMP_KEY] = {"kind": kind, "id": rid, "source": source}
    st.switch_page(KINDS[kind]["page"])


def go_key(key: str) -> None:
    kind, _, rid = str(key).partition(":")
    if kind == "task" or kind == "study" or kind == "exam" or kind == "deadline" or kind == "apply":
        try:
            rid = int(rid)
        except ValueError:
            pass
    go(kind, rid)


def take_jump(*kinds: str) -> dict | None:
    """Pop the pending jump if it is one of ``kinds`` (any kind if none)."""
    j = st.session_state.get(JUMP_KEY)
    if not j:
        return None
    if kinds and j.get("kind") not in kinds:
        return None
    st.session_state.pop(JUMP_KEY, None)
    return j


def peek_jump(*kinds: str) -> dict | None:
    j = st.session_state.get(JUMP_KEY)
    if j and (not kinds or j.get("kind") in kinds):
        return j
    return None


# --- giving every plan a date and a time -----------------------------------


def unscheduled_tasks() -> pd.DataFrame:
    """Open tasks still missing a day or a time of day."""
    df = planning.tasks()
    if not len(df):
        return df
    df = df[df["status"].isin(["todo", "doing"])].copy()
    times = planning.task_times()
    df["has_day"] = df["day"].notna()
    df["time"] = [times.get(int(i)) for i in df["id"]]
    df["has_time"] = df["time"].notna()
    return df[~(df["has_day"] & df["has_time"])]


def busy_blocks(day: date) -> list[tuple[datetime, datetime]]:
    """Timed things already on a day, so a new one can be slotted around them."""
    ev = events_on(day)
    out = []
    for r in ev.to_dict("records"):
        t = store.as_time(r["time"])
        if t is None:
            continue
        s = datetime.combine(day, t)
        out.append((s, s + timedelta(minutes=max(int(r["minutes"]), 15))))
    return sorted(out)


def next_free_time(day: date, minutes: int = 60, earliest: time = time(9, 0),
                   latest: time = time(22, 0), blocks=None) -> time:
    """The first quarter-hour slot on ``day`` where ``minutes`` fit without
    overlapping anything already timed. Falls back to the earliest hour."""
    blocks = busy_blocks(day) if blocks is None else blocks
    cur = datetime.combine(day, earliest)
    end_limit = datetime.combine(day, latest)
    step = timedelta(minutes=15)
    span = timedelta(minutes=max(int(minutes), 15))
    while cur + span <= end_limit:
        clash = any(s < cur + span and cur < e for s, e in blocks)
        if not clash:
            return cur.time()
        cur += step
    return earliest


def auto_schedule(task_ids: list[int] | None = None) -> dict:
    """Give every open task without a day or a time one of each.

    A task without a day goes to the first day of its own week that is not
    already past (or today, for a week that has gone). A task without a
    time takes the next free slot that day, after everything already timed.
    Returns how many got a day and how many got a time.
    """
    pending = unscheduled_tasks()
    if task_ids is not None:
        pending = pending[pending["id"].isin([int(i) for i in task_ids])]
    today = date.today()
    got_day = got_time = 0
    cache: dict[date, list] = {}
    for t in pending.sort_values(["week_start", "sort", "id"]).to_dict("records"):
        tid = int(t["id"])
        day = store.as_date(t["day"])
        if day is None:
            monday = store.as_date(t["week_start"]) or scoring.week_start(today)
            sunday = monday + timedelta(days=6)
            day = today if monday <= today <= sunday else (monday if monday > today else today)
            planning.update_task(tid, day=day)
            got_day += 1
        if not t["has_time"]:
            blocks = cache.setdefault(day, busy_blocks(day))
            at = next_free_time(day, int(t["planned_minutes"]), blocks=blocks)
            planning.set_task_time(tid, at.strftime("%H:%M"))
            s = datetime.combine(day, at)
            blocks.append((s, s + timedelta(minutes=int(t["planned_minutes"]))))
            blocks.sort()
            got_time += 1
    return {"days": got_day, "times": got_time, "total": int(len(pending))}
