"""School: courses, how far the lectures have got, how far you have got,
exams, and the study plan that gets you there in time.

Four JSON collections in the settings table (``store.py``):

``school_courses``   a course: name, code, units, colour, lecture slots, how
                     many chapters/topics the syllabus has.
``school_weeks``     one row per course per week: chapters the lecture covered
                     that week, chapters you studied, hours you studied.
``school_exams``     quizzes, tests, midterms, finals, assignments — with a
                     date and a time, and the day you mean to start studying.
``school_sessions``  the study plan: dated, timed study blocks, one per
                     sitting, that the calendar draws and you tick off.

Nothing here touches the tracker's SQLite schema.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pandas as pd

from tracker import scoring, store

K_COURSES = "school_courses"
K_WEEKS = "school_weeks"
K_EXAMS = "school_exams"
K_SESSIONS = "school_sessions"

EXAM_KINDS = [
    "Quiz",
    "Test",
    "Midterm",
    "Final",
    "Assignment",
    "Project",
    "Presentation",
    "Lab",
]
# How many days ahead each kind usually wants you to start.
LEAD_DAYS = {
    "Quiz": 3,
    "Test": 7,
    "Midterm": 14,
    "Final": 21,
    "Assignment": 7,
    "Project": 14,
    "Presentation": 7,
    "Lab": 3,
}
EXAM_STATUS = ["Upcoming", "Done"]

COLORS = [
    "#6366f1", "#0ea5e9", "#14b8a6", "#22c55e", "#f59e0b",
    "#f43f5e", "#a855f7", "#ec4899", "#64748b", "#0891b2",
]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# --- courses ----------------------------------------------------------------


def _course(r: dict) -> dict:
    slots = []
    for s in r.get("lectures") or []:
        if not isinstance(s, dict):
            continue
        try:
            slots.append(
                {
                    "day": int(s.get("day", 0)) % 7,
                    "start": store.hhmm(s.get("start")) or "09:00",
                    "end": store.hhmm(s.get("end")) or "10:00",
                    "room": str(s.get("room", "")),
                }
            )
        except (TypeError, ValueError):
            continue
    return {
        "id": int(r.get("id", 0)),
        "name": str(r.get("name", "")),
        "code": str(r.get("code", "")),
        "units": float(r.get("units", 3) or 0),
        "instructor": str(r.get("instructor", "")),
        "color": str(r.get("color") or COLORS[0]),
        "chapters": int(r.get("chapters", 12) or 0),
        "term_start": store.as_date(r.get("term_start")),
        "term_end": store.as_date(r.get("term_end")),
        "lectures": slots,
        "notes": str(r.get("notes", "")),
        "archived": bool(r.get("archived", False)),
    }


def courses(include_archived: bool = False) -> list[dict]:
    out = [_course(r) for r in store.rows(K_COURSES)]
    if not include_archived:
        out = [c for c in out if not c["archived"]]
    return sorted(out, key=lambda c: (c["archived"], c["name"].lower()))


def course(course_id: int) -> dict | None:
    r = store.get(K_COURSES, course_id)
    return _course(r) if r else None


def course_names() -> dict[int, str]:
    return {c["id"]: c["name"] for c in courses(include_archived=True)}


def add_course(
    name: str,
    code: str = "",
    units: float = 3,
    chapters: int = 12,
    instructor: str = "",
    color: str | None = None,
    term_start: date | None = None,
    term_end: date | None = None,
    lectures: list[dict] | None = None,
    notes: str = "",
) -> int:
    used = {c["color"] for c in courses(include_archived=True)}
    if not color:
        color = next((c for c in COLORS if c not in used), COLORS[len(used) % len(COLORS)])
    return store.add(
        K_COURSES,
        {
            "name": name.strip(),
            "code": code.strip(),
            "units": float(units),
            "chapters": int(chapters),
            "instructor": instructor.strip(),
            "color": color,
            "term_start": term_start.isoformat() if term_start else None,
            "term_end": term_end.isoformat() if term_end else None,
            "lectures": lectures or [],
            "notes": notes,
            "archived": False,
        },
    )


def update_course(course_id: int, **fields) -> None:
    for k in ("term_start", "term_end"):
        if k in fields and isinstance(fields[k], date):
            fields[k] = fields[k].isoformat()
    store.update(K_COURSES, course_id, **fields)


def delete_course(course_id: int) -> None:
    store.remove_where(K_WEEKS, course_id=int(course_id))
    store.remove_where(K_SESSIONS, course_id=int(course_id))
    store.remove_where(K_EXAMS, course_id=int(course_id))
    store.remove(K_COURSES, course_id)


def total_units() -> float:
    return float(sum(c["units"] for c in courses()))


# --- weekly log -------------------------------------------------------------


def _week(r: dict) -> dict:
    return {
        "id": int(r.get("id", 0)),
        "course_id": int(r.get("course_id", 0)),
        "week_start": store.as_date(r.get("week_start")),
        "lecture_chapters": float(r.get("lecture_chapters", 0) or 0),
        "study_chapters": float(r.get("study_chapters", 0) or 0),
        "study_hours": float(r.get("study_hours", 0) or 0),
        "notes": str(r.get("notes", "")),
    }


def weeks(course_id: int | None = None) -> list[dict]:
    out = [_week(r) for r in store.rows(K_WEEKS)]
    if course_id is not None:
        out = [w for w in out if w["course_id"] == int(course_id)]
    return sorted(out, key=lambda w: (w["week_start"] or date.min, w["id"]))


def week_entry(course_id: int, monday: date) -> dict | None:
    for w in weeks(course_id):
        if w["week_start"] == monday:
            return w
    return None


def log_week(
    course_id: int,
    monday: date,
    lecture_chapters: float,
    study_chapters: float,
    study_hours: float,
    notes: str = "",
) -> None:
    """One row per course per week — writing it twice updates it."""
    monday = scoring.week_start(monday)
    cur = week_entry(course_id, monday)
    payload = {
        "course_id": int(course_id),
        "week_start": monday.isoformat(),
        "lecture_chapters": float(lecture_chapters),
        "study_chapters": float(study_chapters),
        "study_hours": float(study_hours),
        "notes": notes,
    }
    if cur:
        store.update(K_WEEKS, cur["id"], **payload)
    else:
        store.add(K_WEEKS, payload)


def delete_week(week_id: int) -> None:
    store.remove(K_WEEKS, week_id)


def progress(course_id: int) -> dict:
    """Where the lecture is, where you are, and the gap between the two."""
    c = course(course_id)
    ws = weeks(course_id)
    lecture = sum(w["lecture_chapters"] for w in ws)
    studied = sum(w["study_chapters"] for w in ws)
    hours = sum(w["study_hours"] for w in ws)
    total = c["chapters"] if c and c["chapters"] else 0
    return {
        "lecture": lecture,
        "studied": studied,
        "hours": hours,
        "total": total,
        "backlog": max(lecture - studied, 0.0),
        "lecture_pct": (lecture / total) if total else 0.0,
        "studied_pct": (studied / total) if total else 0.0,
        "weeks": len(ws),
        "hours_per_week": (hours / len(ws)) if ws else 0.0,
    }


def week_frame(course_id: int) -> pd.DataFrame:
    """Week by week, with running totals — the shape the charts want."""
    ws = weeks(course_id)
    if not ws:
        return pd.DataFrame(
            columns=[
                "week_start", "lecture_chapters", "study_chapters", "study_hours",
                "lecture_cum", "study_cum", "backlog", "label",
            ]
        )
    df = pd.DataFrame(ws).sort_values("week_start")
    df["lecture_cum"] = df["lecture_chapters"].cumsum()
    df["study_cum"] = df["study_chapters"].cumsum()
    df["backlog"] = (df["lecture_cum"] - df["study_cum"]).clip(lower=0)
    df["label"] = df["week_start"].map(lambda d: f"{d:%d %b}")
    return df


def all_weeks_frame() -> pd.DataFrame:
    names = course_names()
    ws = weeks()
    if not ws:
        return pd.DataFrame(columns=["week_start", "course", "study_hours", "label"])
    df = pd.DataFrame(ws)
    df["course"] = df["course_id"].map(lambda i: names.get(i, "?"))
    df["label"] = df["week_start"].map(lambda d: f"{d:%d %b}")
    return df


# --- exams ------------------------------------------------------------------


def _exam(r: dict) -> dict:
    return {
        "id": int(r.get("id", 0)),
        "course_id": int(r.get("course_id", 0)),
        "kind": r.get("kind") if r.get("kind") in EXAM_KINDS else "Test",
        "title": str(r.get("title", "")),
        "day": store.as_date(r.get("day")),
        "time": store.hhmm(r.get("time")),
        "minutes": int(r.get("minutes", 90) or 0),
        "location": str(r.get("location", "")),
        "weight": float(r.get("weight", 0) or 0),
        "topics": str(r.get("topics", "")),
        "start_study": store.as_date(r.get("start_study")),
        "status": r.get("status") if r.get("status") in EXAM_STATUS else "Upcoming",
        "score": r.get("score"),
        "notes": str(r.get("notes", "")),
    }


def exams(course_id: int | None = None) -> list[dict]:
    out = [_exam(r) for r in store.rows(K_EXAMS)]
    if course_id is not None:
        out = [e for e in out if e["course_id"] == int(course_id)]
    return sorted(out, key=lambda e: (e["day"] is None, e["day"] or date.max, e["time"] or ""))


def exam(exam_id: int) -> dict | None:
    r = store.get(K_EXAMS, exam_id)
    return _exam(r) if r else None


def suggested_start(kind: str, day: date | None) -> date | None:
    if day is None:
        return None
    return day - timedelta(days=LEAD_DAYS.get(kind, 7))


def add_exam(
    course_id: int,
    kind: str,
    title: str,
    day: date | None,
    at: time | str | None,
    minutes: int = 90,
    location: str = "",
    weight: float = 0.0,
    topics: str = "",
    start_study: date | None = None,
    notes: str = "",
) -> int:
    if start_study is None:
        start_study = suggested_start(kind, day)
    return store.add(
        K_EXAMS,
        {
            "course_id": int(course_id),
            "kind": kind if kind in EXAM_KINDS else "Test",
            "title": title.strip() or kind,
            "day": day.isoformat() if day else None,
            "time": store.hhmm(at),
            "minutes": int(minutes),
            "location": location.strip(),
            "weight": float(weight),
            "topics": topics,
            "start_study": start_study.isoformat() if start_study else None,
            "status": "Upcoming",
            "notes": notes,
        },
    )


def update_exam(exam_id: int, **fields) -> None:
    for k in ("day", "start_study"):
        if k in fields:
            v = fields[k]
            fields[k] = v.isoformat() if isinstance(v, date) else (v or None)
    if "time" in fields:
        fields["time"] = store.hhmm(fields["time"])
    store.update(K_EXAMS, exam_id, **fields)


def delete_exam(exam_id: int) -> None:
    store.remove_where(K_SESSIONS, exam_id=int(exam_id))
    store.remove(K_EXAMS, exam_id)


def upcoming_exams(days: int = 30, today: date | None = None) -> list[dict]:
    today = today or date.today()
    names = course_names()
    out = []
    for e in exams():
        if e["status"] != "Upcoming" or e["day"] is None:
            continue
        left = (e["day"] - today).days
        if left <= days:
            out.append({**e, "days_left": left, "course": names.get(e["course_id"], "?")})
    return sorted(out, key=lambda e: e["days_left"])


# --- study sessions (the plan) ----------------------------------------------


def _session(r: dict) -> dict:
    return {
        "id": int(r.get("id", 0)),
        "course_id": int(r.get("course_id", 0)),
        "exam_id": int(r["exam_id"]) if r.get("exam_id") else None,
        "day": store.as_date(r.get("day")),
        "time": store.hhmm(r.get("time")) or "18:00",
        "minutes": int(r.get("minutes", 60) or 60),
        "topic": str(r.get("topic", "")),
        "done": bool(r.get("done", False)),
    }


def sessions(course_id: int | None = None, exam_id: int | None = None) -> list[dict]:
    out = [_session(r) for r in store.rows(K_SESSIONS)]
    if course_id is not None:
        out = [s for s in out if s["course_id"] == int(course_id)]
    if exam_id is not None:
        out = [s for s in out if s["exam_id"] == int(exam_id)]
    return sorted(out, key=lambda s: (s["day"] or date.max, s["time"]))


def session(session_id: int) -> dict | None:
    r = store.get(K_SESSIONS, session_id)
    return _session(r) if r else None


def add_session(
    course_id: int,
    day: date,
    at: time | str,
    minutes: int = 60,
    topic: str = "",
    exam_id: int | None = None,
) -> int:
    return store.add(
        K_SESSIONS,
        {
            "course_id": int(course_id),
            "exam_id": int(exam_id) if exam_id else None,
            "day": day.isoformat(),
            "time": store.hhmm(at) or "18:00",
            "minutes": int(minutes),
            "topic": topic.strip(),
            "done": False,
        },
    )


def update_session(session_id: int, **fields) -> None:
    if "day" in fields and isinstance(fields["day"], date):
        fields["day"] = fields["day"].isoformat()
    if "time" in fields:
        fields["time"] = store.hhmm(fields["time"]) or "18:00"
    store.update(K_SESSIONS, session_id, **fields)


def toggle_session(session_id: int, done: bool | None = None) -> None:
    s = session(session_id)
    if s is None:
        return
    store.update(K_SESSIONS, session_id, done=(not s["done"]) if done is None else bool(done))


def delete_session(session_id: int) -> None:
    store.remove(K_SESSIONS, session_id)


def plan_days(start: date, end: date, weekdays: set[int]) -> list[date]:
    """Every date from ``start`` to ``end`` inclusive that falls on one of
    the chosen weekdays (0 = Monday)."""
    out, cur = [], start
    while cur <= end:
        if cur.weekday() in weekdays:
            out.append(cur)
        cur += timedelta(days=1)
    return out


def build_plan(
    exam_id: int,
    start: date,
    weekdays: set[int],
    at: time | str,
    minutes: int,
    topics: list[str] | None = None,
    replace: bool = True,
) -> int:
    """Lay study sessions down from ``start`` to the day before the exam, on
    the chosen weekdays. Topics, if given, are dealt out across the sessions
    in order so each sitting knows what it is for. Returns how many."""
    e = exam(exam_id)
    if e is None or e["day"] is None:
        return 0
    end = e["day"] - timedelta(days=1)
    if replace:
        store.remove_where(K_SESSIONS, exam_id=int(exam_id))
    days = plan_days(start, end, weekdays or set(range(7)))
    topics = [t.strip() for t in (topics or []) if t.strip()]
    for i, d in enumerate(days):
        topic = topics[i * len(topics) // len(days)] if topics else f"{e['kind']} prep"
        add_session(e["course_id"], d, at, minutes, topic, exam_id=exam_id)
    update_exam(exam_id, start_study=start)
    return len(days)


def plan_summary(exam_id: int) -> dict:
    ss = sessions(exam_id=exam_id)
    done = [s for s in ss if s["done"]]
    return {
        "sessions": len(ss),
        "done": len(done),
        "minutes": sum(s["minutes"] for s in ss),
        "minutes_done": sum(s["minutes"] for s in done),
        "first": ss[0]["day"] if ss else None,
        "last": ss[-1]["day"] if ss else None,
    }


# --- lectures as calendar events ---------------------------------------------


def lecture_occurrences(start: date, end: date) -> list[dict]:
    """Every lecture slot that lands between ``start`` and ``end``, kept
    inside the course's term when one is set."""
    out = []
    for c in courses():
        for slot in c["lectures"]:
            cur = start
            while cur <= end:
                if cur.weekday() == slot["day"]:
                    if (c["term_start"] is None or cur >= c["term_start"]) and (
                        c["term_end"] is None or cur <= c["term_end"]
                    ):
                        s, e = store.as_time(slot["start"]), store.as_time(slot["end"])
                        mins = 60
                        if s and e:
                            mins = max(
                                int(
                                    (
                                        datetime.combine(cur, e) - datetime.combine(cur, s)
                                    ).total_seconds()
                                    // 60
                                ),
                                15,
                            )
                        out.append(
                            {
                                "course_id": c["id"],
                                "course": c["name"],
                                "color": c["color"],
                                "day": cur,
                                "time": slot["start"],
                                "minutes": mins,
                                "room": slot["room"],
                            }
                        )
                cur += timedelta(days=1)
    return out


def this_week_hours(monday: date | None = None) -> float:
    monday = monday or scoring.week_start(date.today())
    return float(sum(w["study_hours"] for w in weeks() if w["week_start"] == monday))
