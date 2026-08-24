"""The week you intended, and the day you intended.

The tracker on its own only answers "what did I do?". This module adds the
other half: what you said you would do, so the reports can put the two side by
side. A week gets an hour budget per track and a list of tasks; each task can
be scheduled onto a day, and time logged against it.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd

from tracker import db, scoring

TASK_STATUS = ("todo", "doing", "done", "dropped")
STATUS_UI = {
    "todo": "To do",
    "doing": "In progress",
    "done": "Done",
    "dropped": "Dropped",
}
UI_STATUS = {v: k for k, v in STATUS_UI.items()}


# --- the week's shell -------------------------------------------------------


def get_week(monday: date) -> dict:
    row = db.one("SELECT * FROM week_plan WHERE week_start = ?", (monday.isoformat(),))
    if row is None:
        return {
            "week_start": monday.isoformat(),
            "intention": "",
            "wins": "",
            "blockers": "",
            "next_focus": "",
            "planned_on": None,
            "reviewed_on": None,
        }
    return dict(row)


def save_week(monday: date, **fields) -> None:
    db.execute(
        "INSERT INTO week_plan(week_start) VALUES (?) ON CONFLICT DO NOTHING",
        (monday.isoformat(),),
    )
    if fields:
        sets = ", ".join(f"{k} = ?" for k in fields)
        db.execute(
            f"UPDATE week_plan SET {sets} WHERE week_start = ?",
            list(fields.values()) + [monday.isoformat()],
        )


def is_planned(monday: date) -> bool:
    return get_week(monday)["planned_on"] is not None


# --- hour budget ------------------------------------------------------------


def budget(monday: date) -> pd.DataFrame:
    """Hours promised to each track this week. Falls back to the standing
    split from Settings until the week is planned."""
    trk = scoring.tracks()
    _, _, weekly = scoring.plan_window()
    saved = db.query(
        "SELECT track_id, hours FROM week_hours WHERE week_start = ?",
        (monday.isoformat(),),
    )
    out = trk[["id", "key", "name", "icon", "color", "target_share"]].copy()
    out = out.merge(saved, left_on="id", right_on="track_id", how="left")
    out["default_hours"] = out["target_share"] * weekly
    out["planned_hours"] = out["hours"].fillna(out["default_hours"])
    out["is_saved"] = out["hours"].notna()
    return out.drop(columns=["hours", "track_id"])


def save_budget(monday: date, hours_by_track: dict[int, float]) -> None:
    for track_id, hours in hours_by_track.items():
        db.execute(
            "INSERT INTO week_hours(week_start, track_id, hours) VALUES (?, ?, ?) "
            "ON CONFLICT(week_start, track_id) DO UPDATE SET hours = excluded.hours",
            (monday.isoformat(), int(track_id), float(hours)),
        )


# --- tasks ------------------------------------------------------------------


def milestone_kind(kind: str) -> str:
    """``milestones()`` reports what a thing *is* (skill, tool, output, book,
    project); a task only needs to know which table to write back to."""
    return kind if kind in ("project", "book") else "item"


def tasks(
    monday: date | None = None, day: date | None = None, unscheduled_only: bool = False
) -> pd.DataFrame:
    where, params = ["1 = 1"], []
    if monday is not None:
        where.append("t.week_start = ?")
        params.append(monday.isoformat())
    if day is not None:
        where.append("t.day = ?")
        params.append(day.isoformat())
    if unscheduled_only:
        where.append("t.day IS NULL")

    df = db.query(
        "SELECT t.*, tr.name AS track, tr.icon, tr.color, tr.key AS track_key, "
        "c.name AS category, s.name AS subcategory "
        "FROM tasks t JOIN tracks tr ON tr.id = t.track_id "
        "LEFT JOIN categories c ON c.id = t.category_id "
        "LEFT JOIN subcategories s ON s.id = t.subcategory_id "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY t.day IS NULL, t.day, t.sort, t.id",
        params,
    )
    if len(df):
        # An unscheduled task must read as None, not NaN — pages compare it
        # straight against an ISO date string.
        df["day"] = df["day"].astype(object).where(df["day"].notna(), None)
        df["category"] = df["category"].fillna("")
        df["subcategory"] = df["subcategory"].fillna("")
        df["planned_hours"] = df["planned_minutes"] / 60.0
        logged = db.query(
            "SELECT task_id, SUM(minutes) AS logged_minutes FROM time_log "
            "WHERE task_id IS NOT NULL GROUP BY task_id"
        )
        df = df.merge(logged, left_on="id", right_on="task_id", how="left").drop(
            columns=["task_id"]
        )
        df["logged_minutes"] = df["logged_minutes"].fillna(0).astype(int)
        df["logged_hours"] = df["logged_minutes"] / 60.0
    else:
        for col in ("planned_hours", "logged_minutes", "logged_hours"):
            df[col] = pd.Series(dtype="float")
        for col in ("category", "subcategory"):
            df[col] = pd.Series(dtype="object")
    return df


def add_task(
    monday: date,
    track_id: int,
    title: str,
    planned_minutes: int = 60,
    day: date | None = None,
    milestone_kind: str | None = None,
    milestone_id: int | None = None,
    category_id: int | None = None,
    subcategory_id: int | None = None,
    domains: str = "",
    urgent: bool = False,
) -> int:
    # The day decides the week. Pick any date you like and the task files
    # itself under the week that date belongs to, so budgets and reviews
    # always count it where it actually happened.
    if day is not None:
        monday = scoring.week_start(day)
    nxt = db.one(
        "SELECT COALESCE(MAX(sort), 0) + 1 AS n FROM tasks WHERE week_start = ?",
        (monday.isoformat(),),
    )["n"]
    return db.execute(
        "INSERT INTO tasks(week_start, day, track_id, category_id, "
        "subcategory_id, title, domains, planned_minutes, milestone_kind, "
        "milestone_id, urgent, sort) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            monday.isoformat(),
            day.isoformat() if day else None,
            int(track_id),
            int(category_id) if category_id else None,
            int(subcategory_id) if subcategory_id else None,
            title,
            domains,
            int(planned_minutes),
            milestone_kind,
            int(milestone_id) if milestone_id else None,
            1 if urgent else 0,
            nxt,
        ),
    )


def get_task(task_id: int) -> dict | None:
    row = db.one(
        "SELECT t.*, tr.name AS track, tr.color, c.name AS category, "
        "s.name AS subcategory FROM tasks t "
        "JOIN tracks tr ON tr.id = t.track_id "
        "LEFT JOIN categories c ON c.id = t.category_id "
        "LEFT JOIN subcategories s ON s.id = t.subcategory_id WHERE t.id = ?",
        (int(task_id),),
    )
    return dict(row) if row else None


def _cascade_milestone(task_id: int, stamp: str) -> str | None:
    """Finishing a task finishes the milestone behind it — that is the point
    of linking them. Returns the milestone's name if one was closed."""
    row = db.one(
        "SELECT milestone_kind, milestone_id FROM tasks WHERE id = ?", (int(task_id),)
    )
    if row is None or not row["milestone_kind"] or not row["milestone_id"]:
        return None
    kind, mid = row["milestone_kind"], int(row["milestone_id"])
    if kind == "project":
        db.execute("UPDATE projects SET status='done', done_on=? WHERE id=?", (stamp, mid))
        got = db.one("SELECT name FROM projects WHERE id = ?", (mid,))
    elif kind == "book":
        db.execute("UPDATE books SET status='done' WHERE id=?", (mid,))
        got = db.one("SELECT title AS name FROM books WHERE id = ?", (mid,))
    else:
        db.execute("UPDATE items SET status='done', done_on=? WHERE id=?", (stamp, mid))
        got = db.one("SELECT name FROM items WHERE id = ?", (mid,))
    return got["name"] if got else None


def set_task_status(task_id: int, status: str, cascade: bool = True) -> None:
    stamp = date.today().isoformat() if status == "done" else None
    db.execute(
        "UPDATE tasks SET status = ?, done_on = ? WHERE id = ?",
        (status, stamp, int(task_id)),
    )
    if cascade and status == "done":
        _cascade_milestone(task_id, stamp)


def update_task(task_id: int, **fields) -> None:
    """Write whichever task columns the caller names.

    ``day`` accepts a date or None, ``urgent`` a bool. Setting the status to
    done stamps the completion date — but keeps an existing one, so editing a
    finished task does not quietly move when it was finished.
    """
    if not fields:
        return
    task_id = int(task_id)
    current = db.one("SELECT status, done_on FROM tasks WHERE id = ?", (task_id,))
    if current is None:
        return

    if "day" in fields:
        d = fields["day"]
        if isinstance(d, str) and d:
            d = date.fromisoformat(d)
        fields["day"] = d.isoformat() if isinstance(d, date) else None
        # Moving a task to a date in another week moves the task with it.
        if isinstance(d, date):
            fields["week_start"] = scoring.week_start(d).isoformat()
    if "urgent" in fields:
        fields["urgent"] = 1 if fields["urgent"] else 0
    for key in ("category_id", "subcategory_id", "milestone_id"):
        if key in fields:
            fields[key] = int(fields[key]) if fields[key] else None

    newly_done = False
    if "status" in fields:
        if fields["status"] == "done":
            fields["done_on"] = current["done_on"] or date.today().isoformat()
            newly_done = current["status"] != "done"
        else:
            fields["done_on"] = None

    sets = ", ".join(f"{k} = ?" for k in fields)
    db.execute(
        f"UPDATE tasks SET {sets} WHERE id = ?", list(fields.values()) + [task_id]
    )
    if newly_done:
        _cascade_milestone(task_id, fields["done_on"])


def set_task_urgent(task_id: int, urgent: bool) -> None:
    db.execute(
        "UPDATE tasks SET urgent = ? WHERE id = ?", (1 if urgent else 0, int(task_id))
    )


def schedule_task(task_id: int, day: date | None) -> None:
    """Put a task on a day. Pushing it past Sunday moves it into next week's
    plan rather than leaving it counted against the week it came from."""
    if day is None:
        db.execute("UPDATE tasks SET day = NULL WHERE id = ?", (int(task_id),))
        return
    db.execute(
        "UPDATE tasks SET day = ?, week_start = ? WHERE id = ?",
        (day.isoformat(), scoring.week_start(day).isoformat(), int(task_id)),
    )


def delete_task(task_id: int) -> None:
    db.execute("UPDATE time_log SET task_id = NULL WHERE task_id = ?", (int(task_id),))
    db.execute("DELETE FROM tasks WHERE id = ?", (int(task_id),))


def copy_unfinished(from_monday: date, to_monday: date) -> int:
    """Roll last week's loose ends into this week rather than losing them."""
    open_tasks = db.query(
        "SELECT track_id, category_id, subcategory_id, title, domains, "
        "planned_minutes, milestone_kind, milestone_id "
        "FROM tasks WHERE week_start = ? AND status IN ('todo', 'doing')",
        (from_monday.isoformat(),),
    )
    for row in open_tasks.to_dict("records"):
        add_task(
            to_monday,
            row["track_id"],
            row["title"],
            row["planned_minutes"],
            milestone_kind=row["milestone_kind"],
            milestone_id=row["milestone_id"],
            category_id=row["category_id"],
            subcategory_id=row["subcategory_id"],
            domains=row["domains"] or "",
        )
    return len(open_tasks)


# --- how the plan held ------------------------------------------------------


def week_adherence(monday: date, as_of: date | None = None) -> dict:
    """Planned against actual, for a week."""
    as_of = as_of or scoring.today()
    sunday = monday + timedelta(days=6)
    bud = budget(monday)
    tsk = tasks(monday)

    log = scoring.time_log()
    if len(log):
        log = log[(log["day"] >= monday) & (log["day"] <= sunday)]
    actual = (
        log.groupby("track_id")["hours"].sum() if len(log) else pd.Series(dtype="float")
    )

    bud["actual_hours"] = bud["id"].map(actual).fillna(0.0)
    bud["gap"] = bud["actual_hours"] - bud["planned_hours"]
    bud["attainment"] = bud.apply(
        lambda r: (r["actual_hours"] / r["planned_hours"]) if r["planned_hours"] else 0.0,
        axis=1,
    )

    live = tsk[tsk["status"] != "dropped"] if len(tsk) else tsk
    done = live[live["status"] == "done"] if len(live) else live
    planned_h = float(bud["planned_hours"].sum())
    actual_h = float(bud["actual_hours"].sum())

    return {
        "monday": monday,
        "sunday": sunday,
        "label": scoring.week_label(monday),
        "budget": bud,
        "tasks": tsk,
        "planned_hours": planned_h,
        "actual_hours": actual_h,
        "hours_attainment": (actual_h / planned_h) if planned_h else 0.0,
        "tasks_planned": int(len(live)),
        "tasks_done": int(len(done)),
        "tasks_dropped": int(len(tsk) - len(live)) if len(tsk) else 0,
        "hit_rate": (len(done) / len(live)) if len(live) else 0.0,
        "in_progress": monday <= as_of <= sunday,
        "is_planned": is_planned(monday),
    }


def day_adherence(day: date, as_of: date | None = None) -> dict:
    """Planned against actual, for a single day."""
    tsk = tasks(day=day)
    live = tsk[tsk["status"] != "dropped"] if len(tsk) else tsk
    done = live[live["status"] == "done"] if len(live) else live

    log = scoring.time_log()
    today_log = log[log["day"] == day] if len(log) else log
    planned_min = int(live["planned_minutes"].sum()) if len(live) else 0
    actual_min = int(today_log["minutes"].sum()) if len(today_log) else 0

    return {
        "day": day,
        "tasks": tsk,
        "planned_minutes": planned_min,
        "actual_minutes": actual_min,
        "planned_hours": planned_min / 60.0,
        "actual_hours": actual_min / 60.0,
        "attainment": (actual_min / planned_min) if planned_min else 0.0,
        "tasks_planned": int(len(live)),
        "tasks_done": int(len(done)),
        "hit_rate": (len(done) / len(live)) if len(live) else 0.0,
        "log": today_log,
    }


def board(as_of: date | None = None) -> pd.DataFrame:
    """Every task there is, in one list, ordered the way the to-do page reads.

    Urgent and still open goes to the very top — that is the whole point of
    the flag. A finished task sinks whether or not it was ever urgent, because
    an urgent thing you have already done is not asking anything of you.
    """
    as_of = as_of or scoring.today()
    df = tasks()
    if not len(df):
        for col in ("urgent", "overdue", "is_open", "day_date", "week"):
            df[col] = pd.Series(dtype="object")
        return df

    df["urgent"] = df["urgent"].fillna(0).astype(int).astype(bool)
    df["day_date"] = df["day"].map(
        lambda d: date.fromisoformat(d) if isinstance(d, str) and d else None
    )
    df["is_open"] = df["status"].isin(["todo", "doing"])
    df["overdue"] = [
        bool(d is not None and d < as_of and o)
        for d, o in zip(df["day_date"], df["is_open"])
    ]
    df["week"] = df["week_start"].map(
        lambda w: scoring.week_label(date.fromisoformat(w))
    )

    df["priority"] = (~(df["urgent"] & df["is_open"])).astype(int)
    df["status_rank"] = df["status"].map(
        {"doing": 0, "todo": 1, "done": 3, "dropped": 4}
    ).fillna(2)
    df["day_rank"] = df["day_date"].map(
        lambda d: d.toordinal() if d is not None else 10**7
    )

    return df.sort_values(
        ["priority", "status_rank", "overdue", "day_rank", "week_start", "sort", "id"],
        ascending=[True, True, False, True, True, True, True],
    ).reset_index(drop=True)


def plan_history(as_of: date | None = None) -> pd.DataFrame:
    """Every planned week so far, so the dashboard can show whether the habit
    of planning is holding."""
    as_of = as_of or scoring.today()
    rows = []
    for monday in scoring.plan_weeks():
        if monday > scoring.week_start(as_of):
            continue
        a = week_adherence(monday, as_of)
        rows.append(
            {
                "week": a["label"],
                "monday": monday,
                "planned": a["is_planned"],
                "planned_hours": a["planned_hours"],
                "actual_hours": a["actual_hours"],
                "hours_attainment": a["hours_attainment"],
                "tasks_planned": a["tasks_planned"],
                "tasks_done": a["tasks_done"],
                "hit_rate": a["hit_rate"],
                "reviewed": get_week(monday)["reviewed_on"] is not None,
            }
        )
    return pd.DataFrame(rows)


# --- time of day ------------------------------------------------------------
# Where on the clock a task sits. Stored as one JSON value in the existing
# settings table ({"<task_id>": "HH:MM"}) precisely so the schema stays
# untouched -- databases already parked in the cloud keep working as they are.


def task_times() -> dict[int, str]:
    raw = db.get_setting("task_times") or "{}"
    try:
        data = json.loads(raw)
    except ValueError:
        data = {}
    out = {}
    for k, v in data.items():
        try:
            out[int(k)] = str(v)
        except (TypeError, ValueError):
            continue
    return out


def set_task_time(task_id: int, hhmm: str | None) -> None:
    times = task_times()
    if hhmm is None:
        times.pop(int(task_id), None)
    else:
        times[int(task_id)] = hhmm
    # Times for tasks that no longer exist are dead weight -- drop them while
    # we are writing anyway.
    alive = {int(r["id"]) for r in db.query("SELECT id FROM tasks").to_dict("records")}
    times = {k: v for k, v in times.items() if k in alive}
    db.set_setting("task_times", json.dumps({str(k): v for k, v in sorted(times.items())}))
