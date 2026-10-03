"""Every task from every week, in one list.

The week page is where work gets planned and the day page is where it gets
done; this is where you see all of it at once when you have lost the thread.
Urgent and still open floats to the top — that is the only thing the flag
does, and it is enough. A task tapped on the Calendar lands here, first.
"""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from tracker import agenda, planning, scoring, structure, taskedit, ui

TODAY = date.today()
MONDAY = scoring.week_start(TODAY)

ui.page_header(
    "To do",
    "Everything planned across every week. Flag what is urgent and it comes "
    "to the top.",
    ":material/checklist_rtl:",
)
ui.require_tracks()

STATUS_UI = {"todo": "Not started", "doing": "In progress", "done": "Done"}
UI_STATUS = {v: k for k, v in STATUS_UI.items()}

board = planning.board()
jump = agenda.take_jump("task")

with st.expander("Add a task", icon=":material/add_task:"):
    st.caption(
        "Same fields as anywhere else — it lands on the day you pick, at the "
        "next free time on that day's calendar."
    )
    taskedit.new_task_form("todo_new", MONDAY, default_day=TODAY)

if not len(board):
    st.info(
        "Nothing on the list yet. Add a task above, or plan a week and they "
        "will all show up here.",
        icon=":material/event_note:",
    )
    if st.button("Plan the week", type="primary", icon=":material/date_range:"):
        st.switch_page("app_pages/week.py")
    st.stop()


# --- the state of the list --------------------------------------------------

open_tasks = board[board["is_open"]]
urgent_open = open_tasks[open_tasks["urgent"]]
overdue = open_tasks[open_tasks["overdue"]]

with st.container(horizontal=True):
    st.metric(
        "Urgent",
        len(urgent_open),
        border=True,
        help="Flagged and still open.",
    )
    st.metric(
        "In progress",
        int((board["status"] == "doing").sum()),
        border=True,
    )
    st.metric(
        "Not started",
        int((board["status"] == "todo").sum()),
        border=True,
    )
    st.metric(
        "Overdue",
        len(overdue),
        border=True,
        help="Scheduled for a day that has passed and not finished.",
    )
    st.metric(
        "Done",
        f"{int((board['status'] == 'done').sum())} / {len(board[board['status'] != 'dropped'])}",
        border=True,
    )


# --- one row ----------------------------------------------------------------


def row(t: dict, show_track: bool = True, highlight: bool = False) -> None:
    with st.container(border=True):
        if highlight:
            st.caption(":material/arrow_back: From the calendar — this is the one you tapped.")
        with st.container(horizontal=True, vertical_alignment="center"):
            taskedit.urgent_button(t, "todo")

            # The status is in the key so that a change made anywhere else —
            # the editor, another page — rebuilds this control instead of a
            # stale widget value quietly reverting it.
            picked = st.segmented_control(
                "Status",
                list(UI_STATUS),
                default=STATUS_UI.get(t["status"]),
                key=f"todo_status_{t['id']}_{t['status']}",
                label_visibility="collapsed",
            )
            if picked and UI_STATUS[picked] != t["status"]:
                planning.set_task_status(int(t["id"]), UI_STATUS[picked])
                st.rerun()

            st.markdown(
                f"~~{t['title']}~~" if t["status"] == "done" else f"**{t['title']}**",
                width="stretch",
            )
            taskedit.edit_button(t, "todo")

        with st.container(horizontal=True, vertical_alignment="center"):
            # Under a track heading the track's name would just repeat, so the
            # chip drops to the part of the path that still says something.
            path = structure.path_label(
                t["track"] if show_track else None,
                t["category"] or None,
                t["subcategory"] or None,
            )
            if path:
                ui.chip(path, t["color"])
            if t["overdue"]:
                st.badge(
                    f"overdue since {t['day_date']:%d %b}",
                    icon=":material/schedule:",
                    color="red",
                )
            elif t["day_date"] == TODAY:
                st.badge("today", icon=":material/today:", color="violet")
            elif t["day_date"]:
                st.badge(f"{t['day_date']:%a %d %b}", icon=":material/event:")
            else:
                st.badge("no day yet", icon=":material/event_busy:", color="orange")
            at = times.get(int(t["id"]))
            if at:
                st.badge(at, icon=":material/schedule:", color="blue")
            elif t["is_open"]:
                st.badge("no time yet", icon=":material/more_time:", color="orange")
            if t["week_start"] != MONDAY.isoformat():
                st.badge(t["week"], color="gray")
            if t["milestone_kind"] and pd.notna(t["milestone_id"]):
                st.badge("milestone", icon=":material/flag:", color="violet")
            if t["status"] == "dropped":
                st.badge("dropped", color="gray")
            st.caption(
                f"{ui.hours_text(t['logged_minutes'])} of "
                f"{ui.hours_text(t['planned_minutes'])}"
            )
            ui.domain_pills(t["domains"])

        with st.container(horizontal=True):
            if t["day"] != TODAY.isoformat() and t["is_open"]:
                if st.button(
                    "Do it today",
                    icon=":material/event_available:",
                    key=f"todo_today_{t['id']}",
                    type="tertiary",
                ):
                    planning.schedule_task(int(t["id"]), TODAY)
                    planning.set_task_time(
                        int(t["id"]),
                        agenda.next_free_time(TODAY, int(t["planned_minutes"])).strftime("%H:%M"),
                    )
                    st.rerun()
            if t["is_open"]:
                if st.button(
                    "Tomorrow",
                    icon=":material/redo:",
                    key=f"todo_tmrw_{t['id']}",
                    type="tertiary",
                ):
                    tomorrow = TODAY + timedelta(days=1)
                    planning.schedule_task(int(t["id"]), tomorrow)
                    planning.set_task_time(
                        int(t["id"]),
                        agenda.next_free_time(tomorrow, int(t["planned_minutes"])).strftime("%H:%M"),
                    )
                    st.rerun()
                if st.button(
                    "Drop",
                    icon=":material/block:",
                    key=f"todo_drop_{t['id']}",
                    type="tertiary",
                    help="Not happening — keeps it out of the hit rate.",
                ):
                    planning.set_task_status(int(t["id"]), "dropped")
                    st.rerun()
            if st.button(
                "Delete",
                icon=":material/delete:",
                key=f"todo_del_{t['id']}",
                type="tertiary",
            ):
                planning.delete_task(int(t["id"]))
                st.rerun()


times = planning.task_times()

# --- from the calendar: the one that was tapped, first ------------------------

if jump is not None:
    hit = board[board["id"] == int(jump["id"])]
    if len(hit):
        row(hit.iloc[0].to_dict(), highlight=True)
        st.divider()
    else:
        st.info("That task is gone.", icon=":material/search_off:")


# --- filters ----------------------------------------------------------------

with st.container(border=True):
    tracks = scoring.tracks()
    with st.container(horizontal=True):
        track_filter = st.pills(
            "Tracks",
            list(tracks["name"]),
            selection_mode="multi",
            key="todo_tracks",
        )
        status_filter = st.pills(
            "Status",
            list(UI_STATUS),
            selection_mode="multi",
            default=["Not started", "In progress"],
            key="todo_status",
        )
    with st.container(horizontal=True):
        search = st.text_input(
            "Search",
            placeholder="Filter by name…",
            key="todo_search",
            label_visibility="collapsed",
        )
        scope = st.segmented_control(
            "Scope",
            ["Everything", "This week", "Today", "No day or time"],
            default="Everything",
            key="todo_scope",
            label_visibility="collapsed",
        )
        show_dropped = st.checkbox("Show dropped", key="todo_dropped")

view = board.copy()
if track_filter:
    view = view[view["track"].isin(track_filter)]
if status_filter:
    keep = {UI_STATUS[s] for s in status_filter}
    if show_dropped:
        keep.add("dropped")
    view = view[view["status"].isin(keep)]
elif not show_dropped:
    view = view[view["status"] != "dropped"]
if search.strip():
    needle = search.strip().lower()
    view = view[view["title"].str.lower().str.contains(needle, regex=False)]
if scope == "This week":
    view = view[view["week_start"] == MONDAY.isoformat()]
elif scope == "Today":
    view = view[view["day"] == TODAY.isoformat()]
elif scope == "No day or time":
    view = view[view["day"].isna() | ~view["id"].map(lambda i: int(i) in times)]
if jump is not None:
    view = view[view["id"] != int(jump["id"])]

st.caption(f"{len(view)} of {len(board)} tasks")


# --- the list ---------------------------------------------------------------

urgent_rows = view[view["urgent"] & view["is_open"]]
rest = view.drop(urgent_rows.index)

if len(urgent_rows):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown("### Urgent")
        st.badge(f"{len(urgent_rows)}", color="red")
    st.caption("Across every track, because urgent outranks tidiness.")
    for t in urgent_rows.to_dict("records"):
        row(t)

if len(rest):
    if len(urgent_rows):
        st.markdown("### Everything else, by track")
    # Track order follows the plan, not the alphabet, and empty tracks are
    # left out rather than shown as empty headings.
    for tr in tracks.to_dict("records"):
        chunk = rest[rest["track"] == tr["name"]]
        if not len(chunk):
            continue
        open_here = chunk[chunk["is_open"]]
        with st.container(horizontal=True, vertical_alignment="center"):
            ui.chip(tr["name"], tr["color"])
            st.badge(
                f"{len(open_here)} open" if len(open_here) else "all clear",
                color="blue" if len(open_here) else "green",
            )
            if len(chunk) > len(open_here):
                st.badge(f"{len(chunk) - len(open_here)} closed", color="gray")
            planned = int(open_here["planned_minutes"].sum()) if len(open_here) else 0
            if planned:
                st.badge(ui.hours_text(planned), icon=":material/schedule:")
            overdue_here = int(open_here["overdue"].sum()) if len(open_here) else 0
            if overdue_here:
                st.badge(
                    f"{overdue_here} overdue", icon=":material/warning:", color="red"
                )
        for t in chunk.to_dict("records"):
            row(t, show_track=False)
elif not len(urgent_rows):
    st.caption("Nothing matches those filters.")
