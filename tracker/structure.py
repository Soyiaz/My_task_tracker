"""Reading the tree, checking what an entry owes, and keeping the files.

The taxonomy lives in the database once planted, so everything here reads from
there rather than from ``taxonomy.py`` — the tree is editable, and the app has
to follow whatever it currently says.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pandas as pd

from tracker import db, taxonomy

FIELD_LABELS = taxonomy.FIELD_LABELS


# --- the tree ---------------------------------------------------------------


def categories(track_id: int | None = None) -> pd.DataFrame:
    sql = (
        "SELECT c.id, c.track_id, c.key, c.name, c.requires, c.domains, c.sort, "
        "tr.name AS track, tr.color FROM categories c "
        "JOIN tracks tr ON tr.id = c.track_id "
    )
    params: tuple = ()
    if track_id is not None:
        sql += "WHERE c.track_id = ? "
        params = (int(track_id),)
    return db.query(sql + "ORDER BY tr.sort, c.sort", params)


def subcategories(category_id: int | None = None) -> pd.DataFrame:
    sql = "SELECT id, category_id, key, name, domains, sort FROM subcategories "
    params: tuple = ()
    if category_id is not None:
        sql += "WHERE category_id = ? "
        params = (int(category_id),)
    return db.query(sql + "ORDER BY sort", params)


def domains() -> pd.DataFrame:
    return db.query(
        "SELECT id, key, name, color, target_share, sort FROM domains ORDER BY sort"
    )


def domain_names() -> dict[str, str]:
    return {r["key"]: r["name"] for r in domains().to_dict("records")}


def domain_colors() -> dict[str, str]:
    return {r["name"]: r["color"] for r in domains().to_dict("records")}


def split(value: str | None) -> list[str]:
    """Domain and requirement lists live as comma-separated keys."""
    if not value or (isinstance(value, float) and pd.isna(value)):
        return []
    return [p.strip() for p in str(value).split(",") if p.strip()]


def required_fields(category_id: int | None) -> list[str]:
    if not category_id:
        return []
    row = db.one("SELECT requires FROM categories WHERE id = ?", (int(category_id),))
    return split(row["requires"]) if row else []


def suggested_domains(
    category_id: int | None, subcategory_id: int | None = None
) -> list[str]:
    """What this branch of the tree is usually for. A starting point for the
    picker, never the last word — the person logging decides."""
    out: list[str] = []
    if category_id:
        row = db.one("SELECT domains FROM categories WHERE id = ?", (int(category_id),))
        if row:
            out += split(row["domains"])
    if subcategory_id:
        row = db.one(
            "SELECT domains FROM subcategories WHERE id = ?", (int(subcategory_id),)
        )
        if row:
            out += split(row["domains"])
    seen, uniq = set(), []
    for d in out:
        if d not in seen:
            seen.add(d)
            uniq.append(d)
    return uniq


def missing_fields(category_id: int | None, values: dict) -> list[str]:
    """Which of this category's demands have not been met yet, by label."""
    missing = []
    for field in required_fields(category_id):
        value = values.get(field)
        if field == "file":
            if not value:
                missing.append(FIELD_LABELS[field])
        elif not str(value or "").strip():
            missing.append(FIELD_LABELS[field])
    return missing


def path_label(
    track: str | None, category: str | None, subcategory: str | None
) -> str:
    """Where an entry sits, as one line. Empty levels are simply left out —
    a list already grouped by track passes an empty track and gets back just
    the part that still says something."""
    return " · ".join(p for p in (track, category, subcategory) if p)


# --- editing the tree -------------------------------------------------------
#
# The taxonomy in taxonomy.py is one person's summer, not a rule. These write
# the structure editors on the Settings page back to the database, so anyone
# can delete the stock tracks and categories and grow their own — no code.


def _slugify(name: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", str(name or "").lower()).strip("_") or "x"
    key, n = base, 2
    while key in used:
        key = f"{base}_{n}"
        n += 1
    used.add(key)
    return key


def _fill_keys(edited: pd.DataFrame, used: set[str]) -> pd.DataFrame:
    """Rows freshly typed into an editor have no key yet; grow one from the
    name. Existing keys are kept — entries already point at them."""
    out = edited.copy()
    keys = []
    for r in out.to_dict("records"):
        k = r.get("key")
        if k is None or (isinstance(k, float) and pd.isna(k)) or not str(k).strip():
            k = _slugify(r.get("name", ""), used)
        keys.append(str(k))
    out["key"] = keys
    return out


def _clean_tokens(value, allowed: set[str]) -> str:
    """Keep only tokens the app knows; silently dropping a typo beats storing
    a requirement no form will ever render."""
    return ",".join(t for t in split(value) if t in allowed)


def tracks_editable() -> pd.DataFrame:
    return db.query("SELECT id, key, name, icon, sort FROM tracks ORDER BY sort")


def categories_editable(track_id: int) -> pd.DataFrame:
    return db.query(
        "SELECT id, key, name, requires, domains, sort FROM categories "
        "WHERE track_id = ? ORDER BY sort",
        (int(track_id),),
    )


def subcategories_editable(category_id: int) -> pd.DataFrame:
    return db.query(
        "SELECT id, key, name, domains, sort FROM subcategories "
        "WHERE category_id = ? ORDER BY sort",
        (int(category_id),),
    )


def track_impact() -> pd.DataFrame:
    """What deleting each track would take with it — shown before it happens."""
    return db.query(
        "SELECT tr.id, tr.name, "
        "(SELECT COUNT(*) FROM tasks t WHERE t.track_id = tr.id) AS tasks, "
        "(SELECT COALESCE(SUM(minutes), 0) / 60.0 FROM time_log l "
        " WHERE l.track_id = tr.id) AS hours, "
        "(SELECT COUNT(*) FROM items i WHERE i.track_id = tr.id) "
        "+ (SELECT COUNT(*) FROM projects p WHERE p.track_id = tr.id) AS milestones "
        "FROM tracks tr ORDER BY tr.sort"
    )


def save_tracks(edited: pd.DataFrame, allow_delete: bool = False) -> dict:
    """Write the tracks editor back. Deleting a track cascades to everything
    filed under it — categories, milestones, tasks and logged hours — so it
    only happens when explicitly allowed."""
    original = tracks_editable()
    kept = {int(v) for v in edited["id"].dropna()} if "id" in edited.columns else set()
    removed = {int(v) for v in original["id"].dropna()} - kept
    if removed and not allow_delete:
        raise ValueError("Deleting a track has to be confirmed first.")
    out = _fill_keys(edited, set(original["key"]))
    return db.sync_table(
        "tracks",
        original,
        out,
        {
            "icon": ":material/flag:",
            "color": "#6366f1",
            "goal": "",
            "target_share": 0.10,
            "sort": 999,
        },
    )


def save_categories(track_id: int, edited: pd.DataFrame) -> dict:
    """Write one track's categories back. Deleting a category keeps the tasks
    and hours filed under it — they only lose the label."""
    original = categories_editable(int(track_id))
    out = _fill_keys(edited, set(original["key"]))
    out["requires"] = out["requires"].map(lambda v: _clean_tokens(v, set(FIELD_LABELS)))
    known = set(domains()["key"])
    out["domains"] = out["domains"].map(lambda v: _clean_tokens(v, known))
    return db.sync_table(
        "categories", original, out, {"track_id": int(track_id), "sort": 999}
    )


def save_subcategories(category_id: int, edited: pd.DataFrame) -> dict:
    original = subcategories_editable(int(category_id))
    out = _fill_keys(edited, set(original["key"]))
    known = set(domains()["key"])
    out["domains"] = out["domains"].map(lambda v: _clean_tokens(v, known))
    return db.sync_table(
        "subcategories", original, out, {"category_id": int(category_id), "sort": 999}
    )


# --- domains on entries -----------------------------------------------------


def explode_domains(df: pd.DataFrame, value_col: str = "hours") -> pd.DataFrame:
    """One row per (entry, domain), so a session that fed both robotics and
    computer vision counts under each. Entries with no domain land under
    'Unassigned' — deliberately visible, because a summer measured by domains
    should show what it could not classify."""
    names = domain_names()
    rows = []
    for r in df.to_dict("records"):
        keys = split(r.get("domains")) or ["__none__"]
        for k in keys:
            rows.append(
                {
                    **{c: r[c] for c in df.columns if c != "domains"},
                    "domain_key": k,
                    "domain": names.get(k, "Unassigned"),
                }
            )
    out = pd.DataFrame(rows)
    if not len(out):
        out = pd.DataFrame(columns=list(df.columns) + ["domain_key", "domain"])
    return out


# --- files ------------------------------------------------------------------

SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def save_attachment(owner_kind: str, owner_id: int, uploaded) -> int:
    """Copy a Streamlit upload onto disk and record it. Returns the row id."""
    db.FILES_DIR.mkdir(exist_ok=True)
    safe = SAFE.sub("_", uploaded.name)[-80:]
    stored = f"{uuid.uuid4().hex[:12]}_{safe}"
    data = uploaded.getvalue()
    (db.FILES_DIR / stored).write_bytes(data)
    return db.execute(
        "INSERT INTO attachments(owner_kind, owner_id, filename, stored_name, size) "
        "VALUES (?, ?, ?, ?, ?)",
        (owner_kind, int(owner_id), uploaded.name, stored, len(data)),
    )


def attachments_for(owner_kind: str, owner_id: int) -> pd.DataFrame:
    return db.query(
        "SELECT id, filename, stored_name, size, uploaded_at FROM attachments "
        "WHERE owner_kind = ? AND owner_id = ? ORDER BY id",
        (owner_kind, int(owner_id)),
    )


def attachment_counts(owner_kind: str) -> pd.Series:
    df = db.query(
        "SELECT owner_id, COUNT(*) AS n FROM attachments WHERE owner_kind = ? "
        "GROUP BY owner_id",
        (owner_kind,),
    )
    return df.set_index("owner_id")["n"] if len(df) else pd.Series(dtype="int")


def attachment_path(stored_name: str) -> Path:
    return db.FILES_DIR / stored_name


def delete_attachment(attachment_id: int) -> None:
    row = db.one("SELECT stored_name FROM attachments WHERE id = ?", (int(attachment_id),))
    if row:
        path = attachment_path(row["stored_name"])
        if path.exists():
            path.unlink()
    db.execute("DELETE FROM attachments WHERE id = ?", (int(attachment_id),))
