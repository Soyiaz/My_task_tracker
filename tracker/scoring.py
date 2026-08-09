"""Turning the log into an answer to "how am I actually doing?".

Three numbers carry the app:

* **Goal completion** — how much of the whole plan is finished, weighted so
  that the tracks meant to matter most count for most. Distance to the
  ultimate goal; it only goes up.
* **On pace** — whether that progress, and the hours behind it, are where they
  should be *today*. The number that can fall, and the one that says which
  track needs the next block of work.
* **Domain coverage** — how the hours split across robotics, AI, computer
  vision and personal growth, regardless of which track they were logged
  under. The lens the whole summer is measured by.

Because the week's split "depends on the week", the hours a track is *expected*
to have by now are the sum of the budgets actually set for the weeks that have
elapsed. Only weeks that were never planned fall back to the standing share in
Settings.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

import pandas as pd

from tracker import db, structure

STATUS_CREDIT = {"todo": 0.0, "doing": 0.5, "done": 1.0}
STATUS_LABELS = {"todo": "Not started", "doing": "In progress", "done": "Done"}


# --- the plan window --------------------------------------------------------


def plan_window() -> tuple[date, date, float]:
    start = date.fromisoformat(db.get_setting("start_date"))
    end = date.fromisoformat(db.get_setting("end_date"))
    weekly = float(db.get_setting("weekly_hours"))
    return start, end, weekly


def today() -> date:
    return date.today()


def elapsed(as_of: date | None = None) -> dict:
    """Where we are in the summer. Clamped to the window at both ends so the
    numbers stay sane before it starts and after it ends."""
    start, end, weekly = plan_window()
    as_of = as_of or today()
    total_days = max((end - start).days + 1, 1)
    days_done = min(max((as_of - start).days + 1, 0), total_days)
    return {
        "start": start,
        "end": end,
        "weekly_hours": weekly,
        "total_days": total_days,
        "days_done": days_done,
        "days_left": max(total_days - days_done, 0),
        "fraction": days_done / total_days,
        "weeks_done": days_done / 7,
        "weeks_left": max(total_days - days_done, 0) / 7,
        "planned_hours": weekly * total_days / 7,
    }


# --- calendar helpers -------------------------------------------------------


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_label(monday: date) -> str:
    start, _, _ = plan_window()
    n = (monday - week_start(start)).days // 7
    span = f"{monday:%b %d} – {monday + timedelta(days=6):%b %d}"
    return f"Week {n} · {span}"


def plan_weeks() -> list[date]:
    """Every Monday touched by the plan, oldest first."""
    start, end, _ = plan_window()
    mondays, cur = [], week_start(start)
    while cur <= end:
        mondays.append(cur)
        cur += timedelta(days=7)
    return mondays


def plan_months() -> list[tuple[int, int]]:
    start, end, _ = plan_window()
    months, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


# --- raw pulls --------------------------------------------------------------


def tracks() -> pd.DataFrame:
    return db.query(
        "SELECT id, key, name, icon, color, goal, target_share, sort "
        "FROM tracks ORDER BY sort"
    )


def track_colors() -> dict[str, str]:
    """Track name to hex colour, so every chart in the app agrees."""
    return {r["name"]: r["color"] for r in tracks().to_dict("records")}


def milestones() -> pd.DataFrame:
    """Items, projects and books in one shape, so a single weighted
    completion can be worked out per track."""
    items = db.query(
        "SELECT id, track_id, section, name, kind, weight, status, notes, "
        "done_on, sort FROM items"
    )
    projects = db.query(
        "SELECT id, track_id, 'Projects' AS section, name, 'project' AS kind, "
        "weight, status, notes, done_on, 900 AS sort FROM projects"
    )
    personal = db.query("SELECT id FROM tracks WHERE key = 'personal'")
    books = db.query(
        "SELECT id, ? AS track_id, 'Book club' AS section, "
        "(month || ': ' || CASE WHEN title = '' THEN '(book not chosen)' "
        "ELSE title END) AS name, 'book' AS kind, 2.0 AS weight, status, "
        "reflection AS notes, NULL AS done_on, 800 AS sort FROM books",
        (int(personal.iloc[0]["id"]) if len(personal) else 0,),
    )
    frames = [f for f in (items, projects, books) if len(f)]
    if not frames:
        return items
    out = pd.concat(frames, ignore_index=True)
    out["credit"] = out["status"].map(STATUS_CREDIT).fillna(0.0) * out["weight"]
    return out


def time_log() -> pd.DataFrame:
    """Every entry, with the whole path it was filed under."""
    df = db.query(
        "SELECT t.id, t.day, t.track_id, t.category_id, t.subcategory_id, "
        "t.task_id, tr.key AS track_key, tr.name AS track, tr.color, "
        "c.name AS category, s.name AS subcategory, t.minutes, t.title, "
        "t.purpose, t.detail, t.link, t.domains, t.focus, t.notes, t.source "
        "FROM time_log t "
        "JOIN tracks tr ON tr.id = t.track_id "
        "LEFT JOIN categories c ON c.id = t.category_id "
        "LEFT JOIN subcategories s ON s.id = t.subcategory_id "
        "ORDER BY t.day DESC, t.id DESC"
    )
    if len(df):
        df["day"] = pd.to_datetime(df["day"]).dt.date
        df["hours"] = df["minutes"] / 60.0
        df["category"] = df["category"].fillna("")
        df["subcategory"] = df["subcategory"].fillna("")
        df["what"] = [
            structure.path_label(r["track"], r["category"] or None, r["subcategory"] or None)
            for r in df.to_dict("records")
        ]
    else:
        df["hours"] = pd.Series(dtype="float")
        df["what"] = pd.Series(dtype="object")
    return df


# --- what the plan expected --------------------------------------------------


def expected_hours_by_track(as_of: date | None = None) -> pd.Series:
    """Hours each track should have by now.

    Built week by week from the budgets actually set, prorated for a week that
    is only part over. Weeks that were never planned fall back to the standing
    share, because something has to stand in for an unplanned week.
    """
    start, end, weekly = plan_window()
    as_of = as_of or today()
    trk = tracks()
    saved = db.query("SELECT week_start, track_id, hours FROM week_hours")
    planned = set(
        db.query(
            "SELECT week_start FROM week_plan WHERE planned_on IS NOT NULL"
        )["week_start"]
    )

    totals = {int(t["id"]): 0.0 for t in trk.to_dict("records")}
    for monday in plan_weeks():
        first = max(monday, start)
        last = min(monday + timedelta(days=6), end, as_of)
        days = (last - first).days + 1
        if days <= 0:
            continue
        fraction = days / 7
        key = monday.isoformat()
        week_rows = saved[saved["week_start"] == key] if len(saved) else saved
        if key in planned and len(week_rows):
            for r in week_rows.to_dict("records"):
                if int(r["track_id"]) in totals:
                    totals[int(r["track_id"])] += r["hours"] * fraction
        else:
            for t in trk.to_dict("records"):
                totals[int(t["id"])] += t["target_share"] * weekly * fraction
    return pd.Series(totals, dtype="float")


# --- the report -------------------------------------------------------------


def track_report(as_of: date | None = None) -> pd.DataFrame:
    """One row per track: hours against plan, milestones against pace, and the
    blended health score."""
    e = elapsed(as_of)
    trk = tracks()
    ms = milestones()
    log = time_log()
    if len(log):
        log = log[log["day"] <= (as_of or today())]

    expected = expected_hours_by_track(as_of)
    hours = log.groupby("track_id")["hours"].sum() if len(log) else pd.Series(dtype="float")
    recent_from = (as_of or today()) - timedelta(days=6)
    recent = (
        log[log["day"] >= recent_from].groupby("track_id")["hours"].sum()
        if len(log)
        else pd.Series(dtype="float")
    )

    rows = []
    total_hours = float(hours.sum()) if len(hours) else 0.0
    for t in trk.to_dict("records"):
        mine = ms[ms["track_id"] == t["id"]] if len(ms) else ms
        total_w = float(mine["weight"].sum()) if len(mine) else 0.0
        done_w = float(mine["credit"].sum()) if len(mine) else 0.0
        finished = int((mine["status"] == "done").sum()) if len(mine) else 0
        count = int(len(mine))

        h = float(hours.get(t["id"], 0.0))
        expected_h = float(expected.get(t["id"], 0.0))
        progress = done_w / total_w if total_w else 0.0
        expected_progress = e["fraction"]

        time_score = min(h / expected_h, 1.0) if expected_h > 0 else 1.0
        milestone_score = (
            min(progress / expected_progress, 1.0) if expected_progress > 0 else 1.0
        )
        health = 0.5 * time_score + 0.5 * milestone_score

        rows.append(
            {
                "track_id": t["id"],
                "key": t["key"],
                "track": t["name"],
                "icon": t["icon"],
                "color": t["color"],
                "goal": t["goal"],
                "target_share": t["target_share"],
                "hours": h,
                "hours_7d": float(recent.get(t["id"], 0.0)),
                "expected_hours": expected_h,
                "hour_gap": h - expected_h,
                "actual_share": (h / total_hours) if total_hours else 0.0,
                "done": finished,
                "count": count,
                "progress": progress,
                "expected_progress": expected_progress,
                "time_score": time_score,
                "milestone_score": milestone_score,
                "health": health,
            }
        )

    df = pd.DataFrame(rows)
    df["status"] = df["health"].apply(health_label)
    return df


def health_label(h: float) -> str:
    if h >= 0.85:
        return "On track"
    if h >= 0.6:
        return "Slipping"
    if h > 0.0:
        return "Behind"
    return "Untouched"


def headline(as_of: date | None = None) -> dict:
    """The headline numbers, plus the context around them."""
    e = elapsed(as_of)
    rep = track_report(as_of)
    shares = rep["target_share"].sum() or 1.0
    goal_completion = float((rep["target_share"] * rep["progress"]).sum() / shares)
    on_pace = float((rep["target_share"] * rep["health"]).sum() / shares)
    logged = float(rep["hours"].sum())
    expected = float(rep["expected_hours"].sum())
    weeks_left = max(e["weeks_left"], 1e-9)
    return {
        **e,
        "goal_completion": goal_completion,
        "on_pace": on_pace,
        "hours_logged": logged,
        "hours_expected": expected,
        "hours_behind": expected - logged,
        "needed_per_week": max(e["planned_hours"] - logged, 0.0) / weeks_left,
        "milestones_done": int(rep["done"].sum()),
        "milestones_total": int(rep["count"].sum()),
    }


# --- domains ----------------------------------------------------------------


def domain_report(start: date | None = None, end: date | None = None) -> pd.DataFrame:
    """Hours by lens rather than by track. An hour spent on a club robotics
    project and an hour spent on a FloLabs robot are the same hour here."""
    log = time_log()
    if len(log):
        if start:
            log = log[log["day"] >= start]
        if end:
            log = log[log["day"] <= end]

    doms = structure.domains()
    if len(log):
        ex = structure.explode_domains(log[["id", "hours", "domains", "day"]])
        agg = ex.groupby(["domain_key", "domain"], as_index=False).agg(
            hours=("hours", "sum"), sessions=("id", "nunique")
        )
    else:
        agg = pd.DataFrame(columns=["domain_key", "domain", "hours", "sessions"])

    out = doms[["key", "name", "color", "target_share"]].rename(
        columns={"key": "domain_key", "name": "domain"}
    )
    out = out.merge(agg[["domain_key", "hours", "sessions"]], on="domain_key", how="left")
    out["hours"] = out["hours"].fillna(0.0)
    out["sessions"] = out["sessions"].fillna(0).astype(int)

    unassigned = agg[agg["domain_key"] == "__none__"] if len(agg) else agg
    if len(unassigned):
        out = pd.concat(
            [
                out,
                pd.DataFrame(
                    [
                        {
                            "domain_key": "__none__",
                            "domain": "Unassigned",
                            "color": "#94a3b8",
                            "target_share": 0.0,
                            "hours": float(unassigned.iloc[0]["hours"]),
                            "sessions": int(unassigned.iloc[0]["sessions"]),
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )

    total = float(out["hours"].sum())
    out["coverage"] = out["hours"] / total if total else 0.0
    out["gap"] = out["coverage"] - out["target_share"]
    return out


def thinnest_domain() -> dict | None:
    """The lens least served so far, ignoring the unassigned bucket."""
    rep = domain_report()
    real = rep[rep["domain_key"] != "__none__"]
    if not len(real) or real["hours"].sum() == 0:
        return None
    worst = real.sort_values("gap").iloc[0]
    return worst.to_dict()


# --- next up and advice -----------------------------------------------------


def next_up(track_id: int, limit: int = 4) -> list[str]:
    """The first few unfinished things in a track, in plan order."""
    df = milestones()
    if not len(df):
        return []
    mine = df[(df["track_id"] == track_id) & (df["status"] != "done")].copy()
    if not len(mine):
        return []
    # Half-finished things come first — they are the cheapest to close out.
    mine["rank"] = (mine["status"] != "doing").astype(int)
    mine = mine.sort_values(["rank", "sort"])
    return [f"{r['section']} · {r['name']}" for r in mine.head(limit).to_dict("records")]


def advice(as_of: date | None = None, limit: int = 3) -> list[dict]:
    """What to work on next week, worst-served track first."""
    e = elapsed(as_of)
    rep = track_report(as_of).sort_values(["health", "hour_gap"])
    out = []
    for r in rep.head(limit).to_dict("records"):
        if r["health"] >= 0.95:
            continue
        catch_up = max(-r["hour_gap"], 0.0)
        base = r["target_share"] * e["weekly_hours"]
        if r["hours"] == 0:
            why = "nothing logged here yet"
        elif r["time_score"] < r["milestone_score"]:
            why = (
                f"{catch_up:.1f} h behind the {r['expected_hours']:.0f} h budgeted "
                "so far"
            )
        else:
            why = (
                f"hours are going in, but only {r['progress']:.0%} of the track is "
                f"finished against {r['expected_progress']:.0%} expected"
            )
        out.append(
            {
                "track": r["track"],
                "icon": r["icon"],
                "color": r["color"],
                "status": r["status"],
                "why": why,
                "suggest_hours": base + min(catch_up, base),
                "next_up": next_up(int(r["track_id"])),
            }
        )
    return out


# --- period reports ---------------------------------------------------------


def period_report(start: date, end: date, as_of: date | None = None) -> dict:
    """Everything a week or month review needs, for any date span.

    A period that has not finished yet is judged on the days that have
    actually happened — otherwise the second of the month always looks like a
    disaster. ``full_target_hours`` keeps the whole-period figure for context.
    """
    p_start, p_end, weekly = plan_window()
    as_of = as_of or today()
    days = (end - start).days + 1

    overlap_start, overlap_end = max(start, p_start), min(end, p_end)
    in_plan_days = max((overlap_end - overlap_start).days + 1, 0)
    full_target_hours = weekly * in_plan_days / 7

    elapsed_end = min(overlap_end, as_of)
    elapsed_days = max((elapsed_end - overlap_start).days + 1, 0)
    target_hours = weekly * elapsed_days / 7
    in_progress = end > as_of and elapsed_days > 0

    log = time_log()
    if len(log):
        log = log[(log["day"] >= start) & (log["day"] <= end)]

    trk = tracks()
    by_track = (
        log.groupby(["track_id", "track"], as_index=False).agg(
            hours=("hours", "sum"), sessions=("id", "count")
        )
        if len(log)
        else pd.DataFrame(columns=["track_id", "track", "hours", "sessions"])
    )
    by_track = trk[["id", "name", "icon", "color", "target_share"]].merge(
        by_track, left_on="id", right_on="track_id", how="left"
    )
    by_track["hours"] = by_track["hours"].fillna(0.0)
    by_track["sessions"] = by_track["sessions"].fillna(0).astype(int)
    by_track["track"] = by_track["name"]
    by_track["target_hours"] = by_track["target_share"] * target_hours
    by_track["gap"] = by_track["hours"] - by_track["target_hours"]
    total = float(by_track["hours"].sum())
    by_track["actual_share"] = by_track["hours"] / total if total else 0.0

    by_category = (
        log[log["category"] != ""]
        .groupby(["track", "category", "subcategory"], as_index=False)
        .agg(hours=("hours", "sum"), sessions=("id", "count"))
        .sort_values("hours", ascending=False)
        if len(log)
        else pd.DataFrame(columns=["track", "category", "subcategory", "hours", "sessions"])
    )

    by_day = (
        log.groupby("day", as_index=False)["hours"].sum()
        if len(log)
        else pd.DataFrame(columns=["day", "hours"])
    )
    all_days = pd.DataFrame({"day": pd.date_range(start, end).date})
    by_day = all_days.merge(by_day, on="day", how="left").fillna({"hours": 0.0})

    finished = db.query(
        "SELECT i.name, i.section, tr.name AS track, i.done_on "
        "FROM items i JOIN tracks tr ON tr.id = i.track_id "
        "WHERE i.status = 'done' AND i.done_on BETWEEN ? AND ? "
        "UNION ALL "
        "SELECT p.name, 'Projects', tr.name, p.done_on "
        "FROM projects p JOIN tracks tr ON tr.id = p.track_id "
        "WHERE p.status = 'done' AND p.done_on BETWEEN ? AND ? ",
        (start.isoformat(), end.isoformat(), start.isoformat(), end.isoformat()),
    )

    active_days = int((by_day["hours"] > 0).sum())
    focus = log["focus"].dropna() if len(log) else pd.Series(dtype="float")

    return {
        "start": start,
        "end": end,
        "days": days,
        "elapsed_days": elapsed_days,
        "in_progress": in_progress,
        "hours": total,
        "target_hours": target_hours,
        "full_target_hours": full_target_hours,
        "gap": total - target_hours,
        "attainment": (total / target_hours) if target_hours else 0.0,
        "by_track": by_track[
            [
                "track",
                "icon",
                "color",
                "hours",
                "target_hours",
                "gap",
                "target_share",
                "actual_share",
                "sessions",
            ]
        ],
        "by_category": by_category,
        "by_domain": domain_report(start, end),
        "by_day": by_day,
        "log": log,
        "finished": finished,
        "active_days": active_days,
        "best_day": (
            by_day.loc[by_day["hours"].idxmax()] if len(by_day) and total else None
        ),
        "avg_focus": float(focus.mean()) if len(focus) else None,
        "avg_hours_per_active_day": (total / active_days) if active_days else 0.0,
    }


def week_report(monday: date) -> dict:
    r = period_report(monday, monday + timedelta(days=6))
    r["label"] = week_label(monday)
    return r


def month_report(year: int, month: int) -> dict:
    start, end = month_bounds(year, month)
    r = period_report(start, end)
    r["label"] = f"{calendar.month_name[month]} {year}"
    return r


# --- running timer ----------------------------------------------------------


def running_timer() -> dict | None:
    row = db.one(
        "SELECT t.track_id, t.category_id, t.subcategory_id, t.task_id, "
        "tr.name AS track, tr.color, c.name AS category, s.name AS subcategory, "
        "t.activity, t.domains, t.started_at FROM timer t "
        "JOIN tracks tr ON tr.id = t.track_id "
        "LEFT JOIN categories c ON c.id = t.category_id "
        "LEFT JOIN subcategories s ON s.id = t.subcategory_id WHERE t.id = 1"
    )
    if row is None:
        return None
    started = datetime.fromisoformat(row["started_at"])
    elapsed_s = max((datetime.now() - started).total_seconds(), 0)
    return {
        "track_id": row["track_id"],
        "category_id": row["category_id"],
        "subcategory_id": row["subcategory_id"],
        "task_id": row["task_id"],
        "track": row["track"],
        "color": row["color"],
        "category": row["category"] or "",
        "subcategory": row["subcategory"] or "",
        "activity": row["activity"],
        "domains": row["domains"] or "",
        "started_at": started,
        "minutes": int(elapsed_s // 60),
        "seconds": int(elapsed_s),
    }


def start_timer(
    track_id: int,
    activity: str = "",
    task_id: int | None = None,
    category_id: int | None = None,
    subcategory_id: int | None = None,
    domains: str = "",
) -> None:
    db.execute(
        "INSERT INTO timer(id, track_id, category_id, subcategory_id, task_id, "
        "activity, domains, started_at) VALUES (1, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET track_id = excluded.track_id, "
        "category_id = excluded.category_id, "
        "subcategory_id = excluded.subcategory_id, task_id = excluded.task_id, "
        "activity = excluded.activity, domains = excluded.domains, "
        "started_at = excluded.started_at",
        (
            int(track_id),
            int(category_id) if category_id else None,
            int(subcategory_id) if subcategory_id else None,
            int(task_id) if task_id else None,
            activity,
            domains,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )


def stop_timer(focus: int | None = None, notes: str = "", **extra) -> int:
    """Bank the running stopwatch as a log entry. Returns minutes saved."""
    t = running_timer()
    if t is None:
        return 0
    db.execute("DELETE FROM timer WHERE id = 1")
    minutes = t["minutes"]
    if minutes <= 0:
        return 0
    log_time(
        day=t["started_at"].date(),
        track_id=t["track_id"],
        minutes=minutes,
        category_id=t["category_id"],
        subcategory_id=t["subcategory_id"],
        title=extra.pop("title", "") or t["activity"],
        domains=extra.pop("domains", "") or t["domains"],
        focus=focus,
        notes=notes,
        source="timer",
        task_id=t["task_id"],
        **extra,
    )
    return minutes


def log_time(
    day: date,
    track_id: int,
    minutes: int,
    category_id: int | None = None,
    subcategory_id: int | None = None,
    title: str = "",
    purpose: str = "",
    detail: str = "",
    link: str = "",
    domains: str = "",
    focus: int | None = None,
    notes: str = "",
    source: str = "manual",
    task_id: int | None = None,
) -> int:
    """Record an entry. Returns its row id, so a file can be hung off it."""
    return db.execute(
        "INSERT INTO time_log(day, track_id, category_id, subcategory_id, "
        "task_id, minutes, title, purpose, detail, link, domains, focus, notes, "
        "source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            day.isoformat(),
            int(track_id),
            int(category_id) if category_id else None,
            int(subcategory_id) if subcategory_id else None,
            int(task_id) if task_id else None,
            int(minutes),
            title,
            purpose,
            detail,
            link,
            domains,
            focus,
            notes,
            source,
        ),
    )
