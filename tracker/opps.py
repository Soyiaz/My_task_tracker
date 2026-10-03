"""Opportunities with a deadline: scholarships, internships, programmes.

Each one knows what it is, when it closes, when applications open, when you
mean to apply, and what it asks for. The calendar draws the dates, the
dashboard nags about the near ones, and the list ticks requirements off one
by one. Stored as one JSON collection under the ``opportunity_deadlines``
settings key (see ``store.py``) — no schema change.
"""

from __future__ import annotations

from datetime import date, datetime, time

import pandas as pd

from tracker import store

KEY = "opportunity_deadlines"

CATEGORIES = [
    "Scholarship",
    "Internship",
    "Job",
    "Fellowship",
    "Competition",
    "Grant",
    "Conference",
    "Programme",
    "Research",
    "Volunteering",
    "Other",
]

STATUS = [
    "Watching",
    "Preparing",
    "Applied",
    "Interview",
    "Accepted",
    "Rejected",
    "Missed",
    "Withdrawn",
]
OPEN = {"Watching", "Preparing"}  # still asking something of you
WON = {"Accepted"}

STATUS_COLOR = {
    "Watching": "gray",
    "Preparing": "blue",
    "Applied": "violet",
    "Interview": "orange",
    "Accepted": "green",
    "Rejected": "red",
    "Missed": "red",
    "Withdrawn": "gray",
}


# --- reading ----------------------------------------------------------------


def _norm(r: dict) -> dict:
    """One row with the dates parsed and every field present."""
    reqs = r.get("requirements") or []
    reqs = [
        {"text": str(q.get("text", "")), "done": bool(q.get("done"))}
        if isinstance(q, dict)
        else {"text": str(q), "done": False}
        for q in reqs
    ]
    return {
        "id": int(r.get("id", 0)),
        "name": str(r.get("name", "")),
        "organisation": str(r.get("organisation", "")),
        "category": r.get("category") or "Other",
        "link": str(r.get("link", "")),
        "deadline": store.as_date(r.get("deadline")),
        "deadline_time": store.hhmm(r.get("deadline_time")),
        "apply_from": store.as_date(r.get("apply_from")),
        "apply_on": store.as_date(r.get("apply_on")),
        "apply_time": store.hhmm(r.get("apply_time")),
        "requirements": reqs,
        "notes": str(r.get("notes", "")),
        "status": r.get("status") if r.get("status") in STATUS else "Watching",
        "applied_on": store.as_date(r.get("applied_on")),
        "created_at": r.get("created_at"),
    }


def all_rows() -> list[dict]:
    """Every opportunity, soonest deadline first; the ones without a date last."""
    out = [_norm(r) for r in store.rows(KEY)]
    out.sort(key=lambda r: (r["deadline"] is None, r["deadline"] or date.max, r["id"]))
    return out


def get(row_id: int) -> dict | None:
    r = store.get(KEY, row_id)
    return _norm(r) if r else None


def frame() -> pd.DataFrame:
    rows = all_rows()
    if not rows:
        return pd.DataFrame(
            columns=[
                "id", "name", "organisation", "category", "link", "deadline",
                "deadline_time", "apply_from", "apply_on", "requirements",
                "notes", "status", "days_left", "is_open", "reqs_done", "reqs_total",
            ]
        )
    df = pd.DataFrame(rows)
    today = date.today()
    df["days_left"] = df["deadline"].map(lambda d: (d - today).days if d else None)
    df["is_open"] = df["status"].isin(OPEN)
    df["reqs_total"] = df["requirements"].map(len)
    df["reqs_done"] = df["requirements"].map(lambda q: sum(1 for x in q if x["done"]))
    return df


# --- writing ----------------------------------------------------------------


def add(
    name: str,
    category: str,
    deadline: date | None,
    deadline_time: time | str | None = None,
    apply_from: date | None = None,
    apply_on: date | None = None,
    apply_time: time | str | None = None,
    requirements: list[str] | None = None,
    link: str = "",
    organisation: str = "",
    notes: str = "",
    status: str = "Watching",
) -> int:
    return store.add(
        KEY,
        {
            "name": name.strip(),
            "organisation": organisation.strip(),
            "category": category if category in CATEGORIES else "Other",
            "link": link.strip(),
            "deadline": deadline.isoformat() if deadline else None,
            "deadline_time": store.hhmm(deadline_time),
            "apply_from": apply_from.isoformat() if apply_from else None,
            "apply_on": apply_on.isoformat() if apply_on else None,
            "apply_time": store.hhmm(apply_time),
            "requirements": [
                {"text": q.strip(), "done": False} for q in (requirements or []) if q.strip()
            ],
            "notes": notes,
            "status": status if status in STATUS else "Watching",
        },
    )


def update(row_id: int, **fields) -> None:
    for k in ("deadline", "apply_from", "apply_on", "applied_on"):
        if k in fields:
            v = fields[k]
            fields[k] = v.isoformat() if isinstance(v, date) else (v or None)
    for k in ("deadline_time", "apply_time"):
        if k in fields:
            fields[k] = store.hhmm(fields[k])
    if "requirements" in fields:
        fields["requirements"] = [
            q if isinstance(q, dict) else {"text": str(q), "done": False}
            for q in fields["requirements"]
            if (q.get("text", "").strip() if isinstance(q, dict) else str(q).strip())
        ]
    if "status" in fields:
        if fields["status"] == "Applied" and "applied_on" not in fields:
            cur = get(row_id)
            if cur and not cur["applied_on"]:
                fields["applied_on"] = date.today().isoformat()
    store.update(KEY, row_id, **fields)


def delete(row_id: int) -> None:
    store.remove(KEY, row_id)


def set_requirement(row_id: int, index: int, done: bool) -> None:
    cur = get(row_id)
    if cur is None or index >= len(cur["requirements"]):
        return
    reqs = cur["requirements"]
    reqs[index]["done"] = bool(done)
    store.update(KEY, row_id, requirements=reqs)


# --- what is near ------------------------------------------------------------


def urgency(days_left: int | None) -> tuple[str, str]:
    """Badge colour and a short word for how close a deadline is."""
    if days_left is None:
        return "gray", "no date"
    if days_left < 0:
        return "red", f"{-days_left} d overdue"
    if days_left == 0:
        return "red", "today"
    if days_left == 1:
        return "red", "tomorrow"
    if days_left <= 7:
        return "orange", f"{days_left} days"
    if days_left <= 30:
        return "blue", f"{days_left} days"
    return "gray", f"{days_left} days"


def upcoming(days: int = 14, today: date | None = None) -> list[dict]:
    """Open opportunities closing within ``days`` (or already past), plus the
    ones whose planned application day is within the same window."""
    today = today or date.today()
    out = []
    for r in all_rows():
        if r["status"] not in OPEN:
            continue
        if r["deadline"] is not None:
            left = (r["deadline"] - today).days
            if left <= days:
                out.append({**r, "days_left": left, "what": "deadline"})
                continue
        if r["apply_on"] is not None:
            left = (r["apply_on"] - today).days
            if 0 <= left <= days:
                out.append({**r, "days_left": left, "what": "apply"})
    out.sort(key=lambda r: r["days_left"])
    return out


def deadline_dt(r: dict) -> datetime | None:
    if r["deadline"] is None:
        return None
    t = store.as_time(r["deadline_time"]) or time(23, 59)
    return datetime.combine(r["deadline"], t)
