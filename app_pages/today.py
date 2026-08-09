"""The page you open in the morning and again in the evening.

Morning: what is on for today. Evening: what actually happened, filed properly
enough that the summer can be read back by track *and* by domain.
"""

from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from tracker import db, entryform, planning, scoring, structure, taskedit, ui

TODAY = date.today()
MONDAY = scoring.week_start(TODAY)

e = scoring.elapsed()
ui.page_header(
    "Today",
    f"{TODAY:%A %d %B} · {scoring.week_label(MONDAY)} · day {e['days_done']} of "
    f"{e['total_days']}, {e['days_left']} left",
    ":material/wb_sunny:",
)

trk = scoring.tracks()
if not len(trk):
    st.warning("No tracks yet. Open Settings and rebuild the plan.")
    st.stop()

name_to_id = {r["name"]: int(r["id"]) for r in trk.to_dict("records")}
day = planning.day_adherence(TODAY)
week = planning.week_adherence(MONDAY)


# --- the running stopwatch, front and centre --------------------------------


@st.fragment(run_every="5s")
def stopwatch():
    running = scoring.running_timer()
    with st.container(border=True):
        if running:
            secs = running["seconds"]
            with st.container(horizontal=True, vertical_alignment="center"):
                st.metric(
                    running["activity"] or "Working",
                    f"{secs // 3600}:{(secs % 3600) // 60:02d}:{secs % 60:02d}",
                    border=False,
                )
                with st.container():
                    ui.chip(
                        structure.path_label(
                            running["track"],
                            running["category"] or None,
                            running["subcategory"] or None,
                        ),
                        running["color"],
                    )
                    ui.domain_pills(running["domains"])
                    st.caption(f"Running since {running['started_at']:%H:%M}")
            focus = st.segmented_control(
                "How was the focus?",
                options=list(ui.FOCUS),
                format_func=lambda k: ui.FOCUS[k],
                key="stop_focus",
            )
            notes = st.text_input(
                "Notes", key="stop_notes", placeholder="What came out of it?"
            )
            with st.container(horizontal=True):
                if st.button("Stop and save", type="primary", icon=":material/stop:"):
                    saved = scoring.stop_timer(focus=focus, notes=notes)
                    st.toast(
                        f"Logged {ui.hours_text(saved)} to {running['track']}"
                        if saved
                        else "Under a minute — nothing logged"
                    )
                    st.rerun()
                if st.button("Discard", icon=":material/delete:"):
                    db.execute("DELETE FROM timer WHERE id = 1")
                    st.rerun()
        else:
            st.markdown("**Stopwatch**")
            st.caption(
                "Start it from a task below and the time lands on that task, "
                "already filed. This is for everything else."
            )
            with st.container(horizontal=True):
                track = st.selectbox(
                    "Track", list(name_to_id), key="timer_track", width=200
                )
                cats = structure.categories(name_to_id[track])
                cat_names = {r["name"]: int(r["id"]) for r in cats.to_dict("records")}
                cat = (
                    st.selectbox("Category", list(cat_names), key="timer_cat", width=200)
                    if cat_names
                    else None
                )
                cat_id = cat_names.get(cat) if cat else None
                subs = structure.subcategories(cat_id) if cat_id else None
                sub_names = (
                    {r["name"]: int(r["id"]) for r in subs.to_dict("records")}
                    if subs is not None and len(subs)
                    else {}
                )
                sub = (
                    st.selectbox(
                        "Subcategory", list(sub_names), key="timer_sub", width=200
                    )
                    if sub_names
                    else None
                )
                activity = st.text_input(
                    "What exactly",
                    key="timer_activity",
                    placeholder="e.g. routing the power rails",
                )
            if st.button("Start", type="primary", icon=":material/play_arrow:"):
                scoring.start_timer(
                    name_to_id[track],
                    activity,
                    category_id=cat_id,
                    subcategory_id=sub_names.get(sub) if sub else None,
                    domains=",".join(
                        structure.suggested_domains(cat_id, sub_names.get(sub) if sub else None)
                    ),
                )
                st.rerun()


stopwatch()


# --- how today stands -------------------------------------------------------

log = scoring.time_log()
today_log = log[log["day"] == TODAY] if len(log) else log

streak = 0
if len(log):
    logged_days = set(log["day"])
    cursor = TODAY
    while cursor in logged_days:
        streak += 1
        cursor -= timedelta(days=1)

last7 = [
    float(log[log["day"] == TODAY - timedelta(days=i)]["hours"].sum()) if len(log) else 0.0
    for i in range(6, -1, -1)
]

with st.container(horizontal=True):
    st.metric(
        "Logged today",
        ui.hours_text(day["actual_minutes"]),
        delta=(
            f"{(day['actual_minutes'] - day['planned_minutes']) / 60:+.1f} h vs plan"
            if day["planned_minutes"]
            else None
        ),
        border=True,
        chart_data=last7,
        chart_type="bar",
    )
    st.metric(
        "Today's tasks",
        f"{day['tasks_done']} / {day['tasks_planned']}",
        border=True,
        help="Tick them off as you finish.",
    )
    st.metric(
        "This week",
        ui.hours_text(week["actual_hours"] * 60),
        delta=f"{week['actual_hours'] - week['planned_hours']:+.1f} h vs budget",
        border=True,
    )
    st.metric(
        "Logging streak",
        f"{streak} d",
        border=True,
        help="Consecutive days with something logged.",
    )

if day["planned_minutes"]:
    st.progress(
        min(day["attainment"], 1.0),
        text=f"{ui.hours_text(day['actual_minutes'])} of "
        f"{ui.hours_text(day['planned_minutes'])} planned for today",
    )


# --- today's plan -----------------------------------------------------------

st.markdown("### Today's plan")

tasks_today = day["tasks"]
if not len(tasks_today):
    with st.container(border=True):
        st.markdown("**Nothing planned for today.**")
        st.caption(
            "Pull something in from the week below, or add a task — a day with "
            "a plan is the whole point."
        )
        if st.button("Go and plan the week", icon=":material/date_range:"):
            st.switch_page("app_pages/week.py")
else:
    for t in tasks_today.to_dict("records"):
        dropped = t["status"] == "dropped"
        with st.container(border=True):
            with st.container(horizontal=True, vertical_alignment="center"):
                # The status is in the key: a change made in the editor or on
                # another page rebuilds this box rather than being reverted by
                # a stale widget value.
                done = st.checkbox(
                    t["title"],
                    value=t["status"] == "done",
                    key=f"td_done_{t['id']}_{t['status']}",
                    disabled=dropped,
                )
                if not dropped and done != (t["status"] == "done"):
                    planning.set_task_status(int(t["id"]), "done" if done else "todo")
                    st.rerun()
                ui.chip(
                    structure.path_label(
                        t["track"], t["category"] or None, t["subcategory"] or None
                    ),
                    t["color"],
                )
                taskedit.badges(t, TODAY)
                taskedit.urgent_button(t, "td")
                taskedit.edit_button(t, "td")
            ui.domain_pills(t["domains"])

            with st.container(horizontal=True, vertical_alignment="center"):
                target = int(t["planned_minutes"])
                got = int(t["logged_minutes"])
                st.caption(
                    f"{ui.hours_text(got)} of {ui.hours_text(target)}"
                    + (" · over" if got > target else "")
                )
                st.progress(min(got / target, 1.0) if target else 0.0)

            with st.container(horizontal=True):
                if st.button(
                    "Start timer",
                    icon=":material/play_arrow:",
                    key=f"td_start_{t['id']}",
                    disabled=dropped or t["status"] == "done",
                ):
                    scoring.start_timer(
                        int(t["track_id"]),
                        t["title"],
                        task_id=int(t["id"]),
                        category_id=int(t["category_id"])
                        if pd.notna(t["category_id"])
                        else None,
                        subcategory_id=int(t["subcategory_id"])
                        if pd.notna(t["subcategory_id"])
                        else None,
                        domains=t["domains"] or "",
                    )
                    st.rerun()
                with st.popover("Log time", icon=":material/add:"):
                    mins = st.number_input(
                        "Minutes",
                        min_value=5,
                        max_value=600,
                        value=min(target, 120),
                        step=15,
                        key=f"td_min_{t['id']}",
                    )
                    focus = st.segmented_control(
                        "Focus",
                        options=list(ui.FOCUS),
                        format_func=lambda k: ui.FOCUS[k],
                        key=f"td_focus_{t['id']}",
                    )
                    extra = {}
                    required = structure.required_fields(
                        int(t["category_id"]) if pd.notna(t["category_id"]) else None
                    )
                    for field in ("purpose", "detail", "link"):
                        if field in required:
                            extra[field] = st.text_input(
                                structure.FIELD_LABELS[field],
                                key=f"td_{field}_{t['id']}",
                            )
                    upload = (
                        st.file_uploader(
                            structure.FIELD_LABELS["file"],
                            key=f"td_file_{t['id']}",
                            accept_multiple_files=True,
                        )
                        if "file" in required
                        else None
                    )
                    note = st.text_input("Note", key=f"td_note_{t['id']}")
                    missing = structure.missing_fields(
                        int(t["category_id"]) if pd.notna(t["category_id"]) else None,
                        {"title": t["title"], **extra, "file": upload},
                    )
                    entryform.show_missing(missing)
                    if st.button(
                        "Log it",
                        type="primary",
                        key=f"td_log_{t['id']}",
                        disabled=bool(missing),
                    ):
                        entry_id = scoring.log_time(
                            TODAY,
                            int(t["track_id"]),
                            int(mins),
                            category_id=int(t["category_id"])
                            if pd.notna(t["category_id"])
                            else None,
                            subcategory_id=int(t["subcategory_id"])
                            if pd.notna(t["subcategory_id"])
                            else None,
                            title=t["title"],
                            domains=t["domains"] or "",
                            focus=focus,
                            notes=note,
                            task_id=int(t["id"]),
                            **extra,
                        )
                        entryform.commit_uploads(entry_id, upload)
                        st.toast(f"Logged {ui.hours_text(int(mins))}")
                        st.rerun()
                if not dropped and st.button(
                    "Drop",
                    icon=":material/block:",
                    key=f"td_drop_{t['id']}",
                    type="tertiary",
                    help="Not happening today — keeps it out of the hit rate.",
                ):
                    planning.set_task_status(int(t["id"]), "dropped")
                    st.rerun()
                if st.button(
                    "Push to tomorrow",
                    icon=":material/redo:",
                    key=f"td_push_{t['id']}",
                    type="tertiary",
                ):
                    planning.schedule_task(int(t["id"]), TODAY + timedelta(days=1))
                    st.rerun()


# --- build today ------------------------------------------------------------

with st.container(border=True):
    st.markdown("**Add to today**")
    spare = planning.tasks(MONDAY, unscheduled_only=True)
    spare = spare[spare["status"].isin(["todo", "doing"])] if len(spare) else spare
    left, right = st.columns(2)

    with left:
        st.caption("From this week's list")
        if len(spare):
            labels = {
                f"{r['title']}  ·  {r['track']}  ·  {ui.hours_text(r['planned_minutes'])}": int(
                    r["id"]
                )
                for r in spare.to_dict("records")
            }
            picked = st.multiselect("Unscheduled tasks", list(labels))
            if st.button(
                "Schedule for today",
                icon=":material/event:",
                disabled=not picked,
                type="primary",
            ):
                for label in picked:
                    planning.schedule_task(labels[label], TODAY)
                st.rerun()
        else:
            st.caption("Nothing unscheduled left this week.")

    with right:
        st.caption("Something new")
        taskedit.new_task_form(
            "newtask", MONDAY, default_day=TODAY, button_label="Add task"
        )


# --- log time that was not on the plan --------------------------------------

with st.container(border=True):
    st.markdown("**Log time without a task**")
    st.caption("Backfilling an earlier day, or work that was not on the plan.")

    entry = entryform.picker("manual")

    with st.container(horizontal=True):
        when = st.date_input("Day", value=TODAY, format="YYYY-MM-DD", key="manual_day")
        hours = st.number_input(
            "Hours", min_value=0, max_value=16, step=1, value=1, key="manual_h"
        )
        minutes = st.number_input(
            "Minutes", min_value=0, max_value=59, step=5, value=0, key="manual_m"
        )
        focus = st.segmented_control(
            "Focus",
            options=list(ui.FOCUS),
            format_func=lambda k: ui.FOCUS[k],
            key="manual_focus",
        )
    notes = st.text_area(
        "Notes", placeholder="What you learned, what is next…", key="manual_notes"
    )

    entryform.show_missing(entry["missing"])
    total = int(hours) * 60 + int(minutes)
    if st.button(
        "Save entry",
        type="primary",
        icon=":material/save:",
        disabled=bool(entry["missing"]) or total <= 0,
    ):
        entry_id = scoring.log_time(
            day=when,
            track_id=entry["track_id"],
            minutes=total,
            category_id=entry["category_id"],
            subcategory_id=entry["subcategory_id"],
            title=entry["title"],
            purpose=entry["purpose"],
            detail=entry["detail"],
            link=entry["link"],
            domains=entry["domains"],
            focus=focus,
            notes=notes,
        )
        n = entryform.commit_uploads(entry_id, entry["upload"])
        st.toast(
            f"Logged {ui.hours_text(total)} to {entryform.summary(entry)}"
            + (f" with {n} file(s)" if n else "")
        )
        st.rerun()
    if total <= 0:
        st.caption("Put some time on it first.")


# --- today's entries --------------------------------------------------------


def _delete_entry():
    """Runs on the next rerun, so the row ids come from the list stashed when
    the table was drawn rather than from a stale frame."""
    click = st.session_state.get("today_actions")
    if not click:
        return
    ids = st.session_state.get("today_row_ids", [])
    if click["row"] < len(ids):
        entry_id = ids[click["row"]]
        for a in structure.attachments_for("log", entry_id).to_dict("records"):
            structure.delete_attachment(int(a["id"]))
        db.execute("DELETE FROM time_log WHERE id = ?", (entry_id,))
        st.toast("Entry deleted")


with st.container(border=True):
    st.markdown("**Today's entries**")
    if not len(today_log):
        st.caption("Nothing logged yet today.")
    else:
        counts = structure.attachment_counts("log")
        st.session_state["today_row_ids"] = [int(i) for i in today_log["id"]]
        view = today_log[
            ["what", "title", "hours", "domains", "focus", "notes"]
        ].copy()
        names = structure.domain_names()
        view["domains"] = today_log["domains"].map(
            lambda v: ", ".join(names.get(k, k) for k in structure.split(v)) or "—"
        )
        view["focus"] = view["focus"].map(
            lambda v: ui.FOCUS.get(v, "—") if pd.notna(v) else "—"
        )
        view["files"] = [int(counts.get(int(i), 0)) for i in today_log["id"]]
        view["actions"] = [":material/delete: Delete"] * len(view)
        st.dataframe(
            view,
            hide_index=True,
            column_config={
                "what": st.column_config.TextColumn("Filed under", pinned=True, width="medium"),
                "title": st.column_config.TextColumn("What exactly", width="medium"),
                "hours": st.column_config.NumberColumn("Hours", format="%.2f h"),
                "domains": st.column_config.TextColumn("Fed"),
                "focus": st.column_config.TextColumn("Focus"),
                "files": st.column_config.NumberColumn("Files"),
                "notes": st.column_config.TextColumn("Notes", width="medium"),
                "actions": st.column_config.ButtonColumn(
                    "", on_click=_delete_entry, key="today_actions", type="tertiary"
                ),
            },
        )

        c1, c2 = st.columns(2)
        with c1:
            by_track = today_log.groupby("track", as_index=False)["hours"].sum()
            st.altair_chart(
                alt.Chart(by_track)
                .mark_bar(cornerRadiusEnd=4, size=18)
                .encode(
                    x=alt.X("hours:Q", title="Hours today"),
                    y=alt.Y("track:N", title=None, sort="-x"),
                    color=ui.track_color_field(legend=False),
                    tooltip=["track", alt.Tooltip("hours:Q", format=".1f")],
                )
                .properties(height=max(len(by_track) * 34, 80))
            )
        with c2:
            ex = structure.explode_domains(today_log[["id", "hours", "domains"]])
            if len(ex):
                by_domain = ex.groupby("domain", as_index=False)["hours"].sum()
                st.altair_chart(
                    alt.Chart(by_domain)
                    .mark_bar(cornerRadiusEnd=4, size=18)
                    .encode(
                        x=alt.X("hours:Q", title="Hours by domain"),
                        y=alt.Y("domain:N", title=None, sort="-x"),
                        color=ui.domain_color_field(legend=False),
                        tooltip=["domain", alt.Tooltip("hours:Q", format=".1f")],
                    )
                    .properties(height=max(len(by_domain) * 34, 80))
                )

        files_today = db.query(
            "SELECT a.id, a.filename, a.stored_name, a.size, t.title "
            "FROM attachments a JOIN time_log t ON t.id = a.owner_id "
            "WHERE a.owner_kind = 'log' AND t.day = ?",
            (TODAY.isoformat(),),
        )
        if len(files_today):
            st.caption("Files uploaded today")
            for f in files_today.to_dict("records"):
                path = structure.attachment_path(f["stored_name"])
                if path.exists():
                    st.download_button(
                        f"{f['filename']}  ·  {f['size'] / 1024:.0f} KB",
                        data=path.read_bytes(),
                        file_name=f["filename"],
                        key=f"dl_{f['id']}",
                        icon=":material/download:",
                    )


# --- tick a milestone off directly ------------------------------------------

with st.expander("Tick a milestone off directly", icon=":material/flag:"):
    st.caption(
        "Usually you would finish a task and let it tick the milestone. This is "
        "for things you finished outside the plan."
    )
    ms = scoring.milestones()
    open_ms = ms[ms["status"] != "done"] if len(ms) else ms
    if not len(open_ms):
        st.success("Everything in the plan is done.")
    else:
        open_ms = open_ms.merge(
            trk[["id", "name"]].rename(columns={"name": "track"}),
            left_on="track_id",
            right_on="id",
            suffixes=("", "_t"),
        )
        labels = {
            f"{r['track']} · {r['section']} · {r['name']}": (r["kind"], int(r["id"]))
            for r in open_ms.to_dict("records")
        }
        picked = st.multiselect("Milestones finished today", list(labels))
        if st.button("Mark done", icon=":material/check:", disabled=not picked):
            stamp = TODAY.isoformat()
            for label in picked:
                kind, row_id = labels[label]
                table = planning.milestone_kind(kind)
                if table == "book":
                    db.execute("UPDATE books SET status='done' WHERE id=?", (row_id,))
                else:
                    db.execute(
                        f"UPDATE {'projects' if table == 'project' else 'items'} "
                        "SET status='done', done_on=? WHERE id=?",
                        (stamp, row_id),
                    )
            st.toast(f"{len(picked)} marked done")
            st.rerun()
