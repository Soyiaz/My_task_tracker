"""The one place that knows how to ask "what did you just do?".

Track → category → subcategory, then whatever that category demands on top,
then the domains it fed. Used by the Today page for logging, by the week page
for planning a task, and by the stopwatch when it starts.

It is deliberately not a ``st.form``: the fields on show depend on the
category, so the widgets have to react as you pick.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from tracker import scoring, structure


def _domain_picker(key: str, category_id, subcategory_id, current: list[str] | None = None):
    doms = structure.domains()
    names = {r["key"]: r["name"] for r in doms.to_dict("records")}
    suggested = current if current is not None else structure.suggested_domains(
        category_id, subcategory_id
    )
    picked = st.pills(
        "What did it feed?",
        list(names),
        format_func=lambda k: names[k],
        selection_mode="multi",
        default=[d for d in suggested if d in names],
        key=key,
        help="Robotics, AI, computer vision, personal growth — the lenses the "
        "whole summer is measured by. An hour can feed more than one.",
    )
    return picked or []


def picker(key_prefix: str, defaults: dict | None = None) -> dict:
    """Track → category → subcategory → the fields that branch demands.

    Returns everything needed to write an entry, plus ``missing`` (labels of
    unmet requirements) and ``needs_file``.
    """
    defaults = defaults or {}
    trk = scoring.tracks()
    names = {r["name"]: r for r in trk.to_dict("records")}

    with st.container(horizontal=True):
        track_name = st.selectbox(
            "Track",
            list(names),
            index=_index(list(names), defaults.get("track_name")),
            key=f"{key_prefix}_track",
        )
        track = names[track_name]

        cats = structure.categories(int(track["id"]))
        cat_names = {r["name"]: r for r in cats.to_dict("records")}
        category = None
        if cat_names:
            cat_name = st.selectbox(
                "Category",
                list(cat_names),
                index=_index(list(cat_names), defaults.get("category_name")),
                key=f"{key_prefix}_cat",
            )
            category = cat_names[cat_name]

        subcategory = None
        if category is not None:
            subs = structure.subcategories(int(category["id"]))
            sub_names = {r["name"]: r for r in subs.to_dict("records")}
            if sub_names:
                sub_name = st.selectbox(
                    "Subcategory",
                    list(sub_names),
                    index=_index(list(sub_names), defaults.get("subcategory_name")),
                    key=f"{key_prefix}_sub",
                )
                subcategory = sub_names[sub_name]

    category_id = int(category["id"]) if category is not None else None
    subcategory_id = int(subcategory["id"]) if subcategory is not None else None
    required = structure.required_fields(category_id)

    values = {"title": "", "purpose": "", "detail": "", "link": ""}
    labels = structure.FIELD_LABELS

    if "title" in required or defaults.get("always_title"):
        values["title"] = st.text_input(
            labels["title"] + (" *" if "title" in required else ""),
            value=defaults.get("title", ""),
            key=f"{key_prefix}_title",
            placeholder=_placeholder(track["key"], category),
        )
    if "purpose" in required:
        values["purpose"] = st.text_area(
            labels["purpose"] + " *",
            value=defaults.get("purpose", ""),
            key=f"{key_prefix}_purpose",
            height=70,
            placeholder="What you will be able to do afterwards that you could "
            "not do before.",
        )
    if "detail" in required:
        values["detail"] = st.text_area(
            labels["detail"] + " *",
            value=defaults.get("detail", ""),
            key=f"{key_prefix}_detail",
            height=70,
            placeholder="Say what it actually was.",
        )
    if "link" in required:
        values["link"] = st.text_input(
            labels["link"] + " *",
            value=defaults.get("link", ""),
            key=f"{key_prefix}_link",
        )

    upload = None
    if "file" in required:
        upload = st.file_uploader(
            labels["file"] + " * — what you learned, so it is not lost",
            key=f"{key_prefix}_file",
            accept_multiple_files=True,
        )

    # The key carries the branch, so moving to a different category gets that
    # category's suggestion rather than the last one you picked — while
    # staying put keeps whatever you chose.
    domains = _domain_picker(
        f"{key_prefix}_domains_{category_id}_{subcategory_id}",
        category_id,
        subcategory_id,
    )

    missing = structure.missing_fields(category_id, {**values, "file": upload})

    return {
        "track_id": int(track["id"]),
        "track_name": track["name"],
        "track_key": track["key"],
        "category_id": category_id,
        "category_name": category["name"] if category is not None else "",
        "subcategory_id": subcategory_id,
        "subcategory_name": subcategory["name"] if subcategory is not None else "",
        "domains": ",".join(domains),
        "upload": upload,
        "missing": missing,
        "required": required,
        **values,
    }


def show_missing(missing: list[str]) -> None:
    if missing:
        st.warning(
            "This category needs " + ", ".join(f"**{m}**" for m in missing) + ".",
            icon=":material/edit_note:",
        )


def commit_uploads(entry_id: int, upload, owner_kind: str = "log") -> int:
    """Attach whatever the uploader returned to a freshly written row."""
    if not upload:
        return 0
    files = upload if isinstance(upload, list) else [upload]
    for f in files:
        structure.save_attachment(owner_kind, entry_id, f)
    return len(files)


def summary(entry: dict) -> str:
    """A one-line description of where an entry was filed."""
    path = structure.path_label(
        entry["track_name"], entry["category_name"] or None, entry["subcategory_name"] or None
    )
    return f"{path} — {entry['title']}" if entry.get("title") else path


def _index(options: list, value) -> int:
    try:
        return options.index(value)
    except (ValueError, TypeError):
        return 0


def _placeholder(track_key: str, category) -> str:
    if category is None:
        return ""
    key = category["key"]
    return {
        ("pcb", "learning"): "e.g. Impedance control on a 4-layer stackup",
        ("pcb", "projects"): "e.g. Buck converter breakout",
        ("pcb", "exploring"): "e.g. Line-following robot main board",
        ("flolabs", "gtm"): "e.g. CAIPO explainer for LinkedIn",
        ("income", "in_person"): "Job title, e.g. Embedded prototyping",
        ("income", "remote"): "Job title, e.g. ESP32 firmware contract",
        ("club", "project"): "e.g. Traffic-sign classifier",
        ("club", "research"): "e.g. SLAM on cheap hardware",
        ("ethioxplore", "building"): "e.g. Lalibela site model",
        ("personal", "hobbies"): "Which activity, e.g. guitar",
    }.get((track_key, key), "")
