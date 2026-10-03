"""Notebooks for studying: the index lives in the settings table, the ink
lives on disk.

A notebook's strokes can run to hundreds of kilobytes, which is too much to
keep rewriting inside the settings table on every autosave. So each notebook
is one JSON file under ``files/`` — the same folder uploads live in, parked
in the same cloud bucket the same way — and the settings table only keeps the
list: title, course, paper, page count, when it was last written.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from tracker import cloud, db, store

KEY = "notebooks"
PAPERS = {
    "lined": "Lined",
    "grid": "Grid",
    "dotted": "Dotted",
    "plain": "Plain",
    "cornell": "Cornell",
}
PAPER_COLORS = {"white": "White", "cream": "Cream", "dark": "Dark"}
DOC_VERSION = 1


def _nb(r: dict) -> dict:
    return {
        "id": int(r.get("id", 0)),
        "title": str(r.get("title", "Untitled")),
        "course_id": int(r["course_id"]) if r.get("course_id") else None,
        "paper": r.get("paper") if r.get("paper") in PAPERS else "lined",
        "paper_color": r.get("paper_color") if r.get("paper_color") in PAPER_COLORS else "white",
        "pages": int(r.get("pages", 1) or 1),
        "created_at": r.get("created_at"),
        "updated_at": r.get("updated_at"),
    }


def notebooks(course_id: int | None = None) -> list[dict]:
    out = [_nb(r) for r in store.rows(KEY)]
    if course_id is not None:
        out = [n for n in out if n["course_id"] == int(course_id)]
    return sorted(out, key=lambda n: (n["updated_at"] or n["created_at"] or ""), reverse=True)


def notebook(note_id: int) -> dict | None:
    r = store.get(KEY, note_id)
    return _nb(r) if r else None


def empty_doc(paper: str = "lined", paper_color: str = "white") -> dict:
    return {
        "v": DOC_VERSION,
        "seq": 0,
        "paper": paper,
        "paperColor": paper_color,
        "pages": [{"items": []}],
    }


def create(title: str, course_id: int | None, paper: str = "lined", paper_color: str = "white") -> int:
    nid = store.add(
        KEY,
        {
            "title": title.strip() or "Untitled",
            "course_id": int(course_id) if course_id else None,
            "paper": paper if paper in PAPERS else "lined",
            "paper_color": paper_color if paper_color in PAPER_COLORS else "white",
            "pages": 1,
        },
    )
    save_doc(nid, empty_doc(paper, paper_color))
    return nid


def rename(note_id: int, title: str) -> None:
    store.update(KEY, note_id, title=title.strip() or "Untitled")


def move(note_id: int, course_id: int | None) -> None:
    store.update(KEY, note_id, course_id=int(course_id) if course_id else None)


def delete(note_id: int) -> None:
    name = stored_name(note_id)
    path = db.files_dir() / name
    if path.exists():
        path.unlink()
    cloud.drop_attachment(name)
    store.remove(KEY, note_id)


# --- the ink ----------------------------------------------------------------


def stored_name(note_id: int) -> str:
    return f"note_{int(note_id)}.json"


def doc_path(note_id: int) -> Path:
    path = db.files_dir() / stored_name(note_id)
    if not path.exists():
        # a fresh cloud container has an empty disk; the bucket has the copy
        cloud.fetch_attachment(stored_name(note_id))
    return path


def load_doc(note_id: int) -> dict:
    nb = notebook(note_id)
    path = doc_path(note_id)
    if path.exists():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(doc, dict) and isinstance(doc.get("pages"), list) and doc["pages"]:
                doc.setdefault("seq", 0)
                doc.setdefault("paper", nb["paper"] if nb else "lined")
                doc.setdefault("paperColor", nb["paper_color"] if nb else "white")
                return doc
        except (ValueError, OSError):
            pass
    return empty_doc(nb["paper"] if nb else "lined", nb["paper_color"] if nb else "white")


def save_doc(note_id: int, doc: dict) -> None:
    db.files_dir().mkdir(parents=True, exist_ok=True)
    name = stored_name(note_id)
    path = db.files_dir() / name
    path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    cloud.push_attachment(name)
    pages = doc.get("pages") or []
    store.update(
        KEY,
        note_id,
        pages=max(len(pages), 1),
        paper=doc.get("paper", "lined"),
        paper_color=doc.get("paperColor", "white"),
        updated_at=datetime.now().isoformat(timespec="seconds"),
    )


def ink_count(doc: dict) -> int:
    return sum(len(p.get("items") or []) for p in doc.get("pages") or [])
