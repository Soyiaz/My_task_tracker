"""Editing a task, the same way, wherever you happen to be looking at it.

Today, The week and To do all show the same rows, so they all get the same
two controls: a flag for urgency, and a dialog that can change anything else
about it. Keeping both here means a fix lands on all three pages at once.
"""

from __future__ import annotations

from datetime import date, time, timedelta

import pandas as pd
import streamlit as st

from tracker import entryform, planning, scoring, structure, ui

STATUS_UI = {
    "todo": "Not started",
    "doing": "In progress",
    "done": "Done",
    "dropped": "Dropped",
}
UI_STATUS = {v: k for k, v in STATUS_UI.items()}


def urgent_button(task: dict, key_prefix: str) -> None:
    """The flag. Urgent and still open floats to the top of the To do page."""
    is_urgent = bool(task.get("urgent"))
    if st.button(
        "Urgent" if is_urgent else "Flag",
        icon=":material/priority_high:" if is_urgent else ":material/flag:",
        key=f"{key_prefix}_urgent_{task['id']}",
        type="primary" if is_urgent else "tertiary",
        help="Urgent and still open sits at the top of the To do page."
        if not is_urgent
        else "Flagged urgent. Click to clear.",
    ):
        planning.set_task_urgent(int(task["id"]), not is_urgent)
        st.rerun()


def day_picker(key: str, current: date | None, default: date | None = None) -> date | None:
    """Any date at all, or none.

    Weeks are worked out from the day rather than the other way round, so
    there is no reason to pen you into the seven days of whichever week the
    task happens to sit in — pick the date, and the task files itself under
    the matching week.
    """
    scheduled = st.segmented_control(
        "When",
        ["A day", "Unscheduled"],
        default="A day" if current else "Unscheduled",
        key=f"{key}_mode",
    )
    if scheduled == "Unscheduled":
        return None
    chosen = st.date_input(
        "Day",
        value=current or default or date.today(),
        format="YYYY-MM-DD",
        key=f"{key}_date",
    )
    if isinstance(chosen, (list, tuple)):
        chosen = chosen[0] if chosen else None
    if chosen:
        monday = scoring.week_start(chosen)
        if monday != scoring.week_start(date.today()):
            st.caption(f"Files under {scoring.week_label(monday)}.")
    return chosen


def days_picker(key: str, default: date | None = None) -> list[date]:
    """One day, a span of days, or none at all.

    Planning a week you often mean "work on this Tuesday, Wednesday and
    Friday". Pick the span on the calendar and then drop any day inside it you
    did not mean — the result is whatever set of dates you actually want, and
    one task is created for each.
    """
    mode = st.segmented_control(
        "When",
        ["A day", "Several days", "Unscheduled"],
        default="Unscheduled",
        key=f"{key}_mode",
    )
    if not mode or mode == "Unscheduled":
        return []

    if mode == "A day":
        chosen = st.date_input(
            "Day",
            value=default or date.today(),
            format="YYYY-MM-DD",
            key=f"{key}_date",
        )
        return [chosen] if isinstance(chosen, date) else []

    span_value = st.date_input(
        "From and to",
        value=(),
        format="YYYY-MM-DD",
        key=f"{key}_range",
        help="Click the first day, then the last. Uncheck any day inside the "
        "span you did not mean.",
    )
    picked = list(span_value) if isinstance(span_value, (list, tuple)) else [span_value]
    picked = [d for d in picked if isinstance(d, date)]
    if len(picked) == 2:
        first, last = sorted(picked)
        span = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    else:
        span = picked

    if not span:
        st.caption("Pick a first and a last day on the calendar.")
        return []

    keep = st.pills(
        "Days",
        span,
        format_func=lambda d: f"{ui.DAY_NAMES[d.weekday()][:3]} {d:%d %b}",
        selection_mode="multi",
        default=span,
        key=f"{key}_days",
    )
    keep = sorted(keep or [])
    weeks = {scoring.week_start(d) for d in keep}
    if len(weeks) > 1:
        st.caption(
            f"That spans {len(weeks)} weeks — each task files under the week "
            "of its own day."
        )
    return keep


def start_time_question(key: str, current: str | None = None) -> time | None:
    """The optional 'when on the clock?' — feeds the Calendar page.

    Times live in settings-JSON (``planning.task_times``), not on the task
    row, so this stays an optional extra rather than a schema change.
    """
    value = None
    if current:
        try:
            value = time.fromisoformat(current)
        except ValueError:
            value = None
    return st.time_input(
        "Start time (optional)",
        value=value,
        key=key,
        step=timedelta(minutes=15),
        help="Puts the task on the Calendar page's clock. Leave it empty to "
        "decide later — the task still shows on its day.",
    )


def urgent_toggle(key: str, value: bool = False) -> bool:
    return st.toggle(
        "Urgent",
        value=value,
        key=key,
        help="Sits at the top of the To do page until it is done.",
    )


def new_task_form(
    key_prefix: str,
    fallback_monday: date,
    default_day: date | None = None,
    button_label: str = "Add task",
) -> int | None:
    """Create one task, filed properly, from anywhere.

    The same control on Today, The week and To do, so a task made in one place
    is not thinner than one made in another.
    """
    entry = entryform.picker(key_prefix, {"always_title": True})
    with st.container(horizontal=True):
        minutes = st.number_input(
            "Planned minutes",
            min_value=15,
            max_value=600,
            value=60,
            step=15,
            key=f"{key_prefix}_minutes",
        )
        urgent = urgent_toggle(f"{key_prefix}_urgent")
    day = day_picker(f"{key_prefix}_when", default_day, default_day)
    start = None
    if day is not None:
        start = start_time_question(f"{key_prefix}_start")

    if st.button(
        button_label,
        icon=":material/add_task:",
        type="primary",
        key=f"{key_prefix}_add",
    ):
        if not entry["title"].strip():
            st.warning("Give it a name.")
            return None
        task_id = planning.add_task(
            fallback_monday,
            entry["track_id"],
            entry["title"].strip(),
            int(minutes),
            day=day,
            category_id=entry["category_id"],
            subcategory_id=entry["subcategory_id"],
            domains=entry["domains"],
            urgent=urgent,
        )
        if day is not None and start is not None:
            planning.set_task_time(task_id, start.strftime("%H:%M"))
        st.toast("Task added" + (" · urgent" if urgent else ""))
        st.rerun()
    return None


def edit_button(task: dict, key_prefix: str) -> None:
    """Everything about a task, behind one control.

    A popover rather than a modal: it stays in the ordinary script flow, so it
    behaves the same on every page and survives a rerun the way the rest of
    the app does.
    """
    with st.popover(
        "Edit", icon=":material/edit:", key=f"{key_prefix}_edit_{task['id']}"
    ):
        edit_form(int(task["id"]))


def edit_form(task_id: int) -> None:
    t = planning.get_task(task_id)
    if t is None:
        st.error("That task is gone.")
        return

    monday = date.fromisoformat(t["week_start"])

    title = st.text_input("Task", value=t["title"], key=f"ed_title_{task_id}")

    # Track → category → subcategory, prefilled with where it currently sits.
    trk = scoring.tracks()
    track_names = list(trk["name"])
    track_name = st.selectbox(
        "Track",
        track_names,
        index=track_names.index(t["track"]) if t["track"] in track_names else 0,
        key=f"ed_track_{task_id}",
    )
    track_id = int(trk[trk["name"] == track_name].iloc[0]["id"])

    cats = structure.categories(track_id)
    cat_names = ["—"] + list(cats["name"])
    current_cat = t["category"] if t["category"] in cat_names else "—"
    cat_name = st.selectbox(
        "Category",
        cat_names,
        index=cat_names.index(current_cat),
        key=f"ed_cat_{task_id}_{track_id}",
    )
    category_id = (
        int(cats[cats["name"] == cat_name].iloc[0]["id"]) if cat_name != "—" else None
    )

    subcategory_id = None
    if category_id:
        subs = structure.subcategories(category_id)
        if len(subs):
            sub_names = ["—"] + list(subs["name"])
            current_sub = t["subcategory"] if t["subcategory"] in sub_names else "—"
            sub_name = st.selectbox(
                "Subcategory",
                sub_names,
                index=sub_names.index(current_sub),
                key=f"ed_sub_{task_id}_{category_id}",
            )
            if sub_name != "—":
                subcategory_id = int(subs[subs["name"] == sub_name].iloc[0]["id"])

    dom_names = structure.domain_names()
    current_domains = [d for d in structure.split(t["domains"]) if d in dom_names]
    domains = current_domains
    if dom_names:
        domains = st.pills(
            "What will it feed?",
            list(dom_names),
            format_func=lambda k: dom_names[k],
            selection_mode="multi",
            default=current_domains,
            key=f"ed_dom_{task_id}",
        )
    if category_id and not current_domains:
        suggested = structure.suggested_domains(category_id, subcategory_id)
        if suggested:
            st.caption(
                "This branch usually feeds "
                + ", ".join(dom_names[s] for s in suggested if s in dom_names)
                + "."
            )

    minutes = st.number_input(
        "Planned minutes",
        min_value=5,
        max_value=600,
        value=int(t["planned_minutes"]),
        step=15,
        key=f"ed_min_{task_id}",
    )
    current_day = date.fromisoformat(t["day"]) if t["day"] else None
    when = day_picker(f"ed_day_{task_id}", current_day, monday)
    start = None
    if when is not None:
        start = start_time_question(
            f"ed_start_{task_id}", planning.task_times().get(task_id)
        )
    status_label = st.segmented_control(
        "Status",
        list(UI_STATUS),
        default=STATUS_UI.get(t["status"], "Not started"),
        key=f"ed_status_{task_id}",
    )
    if not status_label:
        status_label = STATUS_UI.get(t["status"], "Not started")

    urgent = urgent_toggle(f"ed_urgent_{task_id}", bool(t["urgent"]))

    unlink = False
    if t["milestone_kind"] and t["milestone_id"]:
        st.caption(
            "Finishing this task also ticks off the milestone it is linked to."
        )
        unlink = st.checkbox(
            "Unlink from that milestone", key=f"ed_unlink_{task_id}"
        )

    logged = planning.tasks(monday)
    mine = logged[logged["id"] == task_id] if len(logged) else logged
    if len(mine) and mine.iloc[0]["logged_minutes"]:
        st.caption(
            f"{ui.hours_text(int(mine.iloc[0]['logged_minutes']))} already logged "
            "against this task. Editing it here leaves those entries alone."
        )

    with st.container(horizontal=True):
        if st.button("Save", type="primary", icon=":material/save:", key=f"ed_save_{task_id}"):
            if not title.strip():
                st.warning("Give it a name.")
            else:
                fields = {
                    "title": title.strip(),
                    "track_id": track_id,
                    "category_id": category_id,
                    "subcategory_id": subcategory_id,
                    "domains": ",".join(domains or []),
                    "planned_minutes": int(minutes),
                    "day": when,
                    "status": UI_STATUS[status_label],
                    "urgent": urgent,
                }
                if unlink:
                    fields["milestone_kind"] = None
                    fields["milestone_id"] = None
                planning.update_task(task_id, **fields)
                # a task taken off its day loses its clock slot too
                planning.set_task_time(
                    task_id,
                    start.strftime("%H:%M") if (when is not None and start) else None,
                )
                st.toast("Task updated")
                st.rerun()
        if st.button(
            "Delete",
            icon=":material/delete:",
            key=f"ed_delete_{task_id}",
            help="Removes the task. Hours already logged against it stay in "
            "the log, unlinked.",
        ):
            planning.delete_task(task_id)
            st.toast("Task deleted")
            st.rerun()


def badges(task: dict, today: date | None = None) -> None:
    """The small flags a task row carries, wherever it is shown."""
    today = today or date.today()
    if task.get("milestone_kind") and pd.notna(task.get("milestone_id")):
        st.badge("milestone", icon=":material/flag:", color="violet")
    if task.get("urgent"):
        st.badge("urgent", icon=":material/priority_high:", color="red")
    day = task.get("day")
    if day and task.get("status") in ("todo", "doing"):
        d = date.fromisoformat(day) if isinstance(day, str) else day
        if d < today:
            st.badge(f"overdue since {d:%d %b}", icon=":material/schedule:", color="red")
    if task.get("status") == "dropped":
        st.badge("dropped", color="gray")
