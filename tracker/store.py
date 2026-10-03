"""Small JSON collections kept in the existing ``settings`` table.

The tracker's SQLite schema is deliberately frozen (databases are already
parked in people's cloud buckets), so anything new that needs saving is kept
the same way task times are: one JSON value under one settings key. A
collection is a list of dicts, each with an integer ``id``; this module is
the whole "ORM" for them.

Collections stay small — dozens of courses, hundreds of weekly entries — so
reading the whole list on every call is fine, and far simpler than anything
cleverer.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any

from tracker import db


def _default(o: Any):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if isinstance(o, time):
        return o.strftime("%H:%M")
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


def rows(key: str) -> list[dict]:
    raw = db.get_setting(key) or "[]"
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def save_rows(key: str, data: list[dict]) -> None:
    db.set_setting(key, json.dumps(list(data), default=_default))


def get(key: str, row_id: int) -> dict | None:
    for r in rows(key):
        if int(r.get("id", -1)) == int(row_id):
            return r
    return None


def add(key: str, row: dict) -> int:
    data = rows(key)
    nxt = max([int(r.get("id", 0)) for r in data] + [0]) + 1
    row = {**row, "id": nxt, "created_at": datetime.now().isoformat(timespec="seconds")}
    data.append(row)
    save_rows(key, data)
    return nxt


def update(key: str, row_id: int, **fields) -> None:
    data = rows(key)
    for r in data:
        if int(r.get("id", -1)) == int(row_id):
            r.update(fields)
            r["updated_at"] = datetime.now().isoformat(timespec="seconds")
            break
    save_rows(key, data)


def remove(key: str, row_id: int) -> None:
    save_rows(key, [r for r in rows(key) if int(r.get("id", -1)) != int(row_id)])


def remove_where(key: str, **match) -> int:
    """Delete every row whose fields equal ``match``. Returns how many went."""
    data = rows(key)
    keep = [r for r in data if not all(r.get(k) == v for k, v in match.items())]
    save_rows(key, keep)
    return len(data) - len(keep)


# --- small parsing helpers shared by the collections ------------------------


def as_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def as_time(value) -> time | None:
    if value is None or value == "":
        return None
    if isinstance(value, time):
        return value
    try:
        return time.fromisoformat(str(value)[:5])
    except ValueError:
        return None


def hhmm(value) -> str | None:
    t = as_time(value)
    return t.strftime("%H:%M") if t else None
