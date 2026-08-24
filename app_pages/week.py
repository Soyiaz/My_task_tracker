"""Plan the week, then review it.

Sunday evening you sit here twice: once to decide what the next seven days are
for, and once to tell the truth about the seven that just went.
"""

from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from tracker import planning, scoring, structure, taskedit, ui

ui.page_header(
    "The week",
    "Budget the hours, name the work, then come back on Sunday and say how it went.",
    ":material/date_range:",
)
ui.require_tracks()

mondays = scoring.plan_weeks()
this_monday = scoring.week_start(date.today())
default = mondays.index(this_monday) if this_monday in mondays else len(mondays) - 1

monday = st.selectbox(
    "Week", mondays, index=default, format_func=scoring.week_label, key="week_page_pick"
)
sunday = monday + timedelta(days=6)
week = planning.get_week(monday)
adh = planning.week_adherence(monday)
_, _, weekly_target = scoring.plan_window()

with st.container(horizontal=True, vertical_alignment="center"):
    st.markdown(f"**{monday:%d %b} – {sunday:%d %b}**")
    if week["planned_on"]:
        st.badge("Planned", icon=":material/event_available:", color="green")
    else:
        st.badge("Not planned yet", icon=":material/event_busy:", color="orange")
    if week["reviewed_on"]:
        st.badge("Reviewed", icon=":material/rate_review:", color="blue")
    if adh["in_progress"]:
        st.badge("Current week", icon=":material/play_circle:", color="violet")

with st.container(horizontal=True):
    st.metric(
        "Hours budgeted",
        ui.hours_text(adh["planned_hours"] * 60),
        delta=f"{adh['planned_hours'] - weekly_target:+.1f} h vs standing target",
        border=True,
    )
    st.metric(
        "Hours logged",
        ui.hours_text(adh["actual_hours"] * 60),
        delta=f"{adh['actual_hours'] - adh['planned_hours']:+.1f} h vs budget",
        border=True,
    )
    st.metric(
        "Tasks done",
        f"{adh['tasks_done']} / {adh['tasks_planned']}",
        border=True,
        help="Dropped tasks are not counted against you.",
    )
    st.metric("Plan hit rate", f"{adh['hit_rate']:.0%}", border=True)

plan_tab, work_tab, review_tab = st.tabs(
    ["Budget", "The work", "Review"],
)


# --- budget -----------------------------------------------------------------

with plan_tab:
    st.markdown("#### What this week is for")
    intention = st.text_area(
        "Intention",
        value=week["intention"],
        placeholder="e.g. Get the first KiCad board to Gerbers and finish the CAIPO doc.",
        height=80,
        key=f"intention_{monday}",
        label_visibility="collapsed",
    )

    st.markdown("#### Hours per track")
    st.caption(
        "Starts from your standing split. Move them around for the week you "
        "actually have — a week with an exam in it is not a normal week."
    )
    bud = adh["budget"]
    values = {}
    with st.container(horizontal=True):
        for row in bud.to_dict("records"):
            values[int(row["id"])] = st.number_input(
                row["name"],
                min_value=0.0,
                max_value=80.0,
                value=float(row["planned_hours"]),
                step=0.5,
                key=f"bud_{monday}_{row['id']}",
            )
    total = sum(values.values())
    st.progress(
        min(total / max(weekly_target, 1), 1.0),
        text=f"{total:.1f} h budgeted · standing target is {weekly_target:.0f} h",
    )
    if total > weekly_target * 1.15:
        st.warning(
            f"That is {total - weekly_target:.1f} h over your standing target. "
            "Fine for a heavy week, but it has to come from somewhere.",
            icon=":material/warning:",
        )

    with st.container(horizontal=True):
        if st.button("Save the plan", type="primary", icon=":material/save:"):
            planning.save_budget(monday, values)
            planning.save_week(
                monday,
                intention=intention,
                planned_on=date.today().isoformat(),
            )
            st.toast("Week planned")
            st.rerun()
        if st.button("Reset to standing split", icon=":material/restart_alt:"):
            planning.save_budget(
                monday,
                {
                    int(r["id"]): r["target_share"] * weekly_target
                    for r in bud.to_dict("records")
                },
            )
            st.rerun()

    prev_monday = monday - timedelta(days=7)
    if prev_monday in mondays:
        prev = planning.week_adherence(prev_monday)
        with st.container(border=True):
            st.markdown(f"**Last week — {scoring.week_label(prev_monday)}**")
            with st.container(horizontal=True):
                st.metric(
                    "Logged",
                    ui.hours_text(prev["actual_hours"] * 60),
                    delta=f"{prev['actual_hours'] - prev['planned_hours']:+.1f} h vs budget",
                    border=True,
                )
                st.metric(
                    "Tasks", f"{prev['tasks_done']} / {prev['tasks_planned']}", border=True
                )
                st.metric("Hit rate", f"{prev['hit_rate']:.0%}", border=True)
            leftover = int(
                (prev["tasks"]["status"].isin(["todo", "doing"])).sum()
                if len(prev["tasks"])
                else 0
            )
            if leftover:
                if st.button(
                    f"Carry {leftover} unfinished task(s) into this week",
                    icon=":material/move_down:",
                ):
                    moved = planning.copy_unfinished(prev_monday, monday)
                    st.toast(f"{moved} carried over")
                    st.rerun()
            prev_week = planning.get_week(prev_monday)
            if prev_week["next_focus"]:
                st.info(
                    f"Last week you wrote: *{prev_week['next_focus']}*",
                    icon=":material/history:",
                )


# --- the work ---------------------------------------------------------------

with work_tab:
    trk = scoring.tracks()
    name_to_id = {r["name"]: int(r["id"]) for r in trk.to_dict("records")}

    ms = scoring.milestones()
    already = (
        {
            (r["milestone_kind"], int(r["milestone_id"]))
            for r in adh["tasks"].to_dict("records")
            if r["milestone_kind"] and pd.notna(r["milestone_id"])
        }
        if len(adh["tasks"])
        else set()
    )
    open_by_track = {}
    for tid in trk["id"]:
        mine = ms[(ms["track_id"] == tid) & (ms["status"] != "done")] if len(ms) else ms
        open_by_track[int(tid)] = mine

    with st.container(border=True):
        st.markdown("**Add work to this week**")
        st.caption(
            "Walk down the same tree you log against: track, then the kind of "
            "work, then what exactly."
        )

        # 1 — track
        track_name = st.pills(
            "Track",
            list(name_to_id),
            default=list(name_to_id)[0],
            key=f"wk_track_{monday}",
        )
        if not track_name:
            track_name = list(name_to_id)[0]
        track = trk[trk["name"] == track_name].iloc[0]
        track_id = int(track["id"])
        track_open = open_by_track[track_id]

        with st.container(horizontal=True, vertical_alignment="center"):
            ui.chip(track["name"], track["color"])
            st.caption(track["goal"])
            budget_row = adh["budget"][adh["budget"]["id"] == track_id].iloc[0]
            planned_here = (
                adh["tasks"][
                    (adh["tasks"]["track_id"] == track_id)
                    & (adh["tasks"]["status"] != "dropped")
                ]["planned_minutes"].sum()
                if len(adh["tasks"])
                else 0
            )
            st.badge(
                f"{ui.hours_text(planned_here)} planned of "
                f"{budget_row['planned_hours']:.1f} h budget",
                icon=":material/schedule:",
                color="blue" if planned_here / 60 <= budget_row["planned_hours"] else "orange",
            )

        # 2 — category
        cats = structure.categories(track_id)
        cat_names = list(cats["name"])
        category = None
        if cat_names:
            cat_name = st.pills(
                "Kind of work",
                cat_names,
                default=cat_names[0],
                key=f"wk_cat_{monday}_{track_id}",
            )
            if not cat_name:
                cat_name = cat_names[0]
            category = cats[cats["name"] == cat_name].iloc[0]

        category_id = int(category["id"]) if category is not None else None

        # 3 — subcategory
        subcategory_id = None
        if category is not None:
            subs = structure.subcategories(category_id)
            if len(subs):
                sub_name = st.pills(
                    "Which one",
                    list(subs["name"]),
                    key=f"wk_sub_{monday}_{category_id}",
                )
                if sub_name:
                    subcategory_id = int(
                        subs[subs["name"] == sub_name].iloc[0]["id"]
                    )
            reqs = structure.split(category["requires"])
            if reqs:
                st.caption(
                    "Logging against this needs "
                    + ", ".join(structure.FIELD_LABELS.get(r, r) for r in reqs).lower()
                    + "."
                )

        # 4 — the milestones filed under this branch, plus a free-text option
        section = category["name"] if category is not None else None
        here = (
            track_open[track_open["section"] == section]
            if section is not None and len(track_open)
            else track_open
        )
        elsewhere = (
            track_open[track_open["section"] != section]
            if section is not None and len(track_open)
            else track_open.iloc[0:0]
        )

        domains_default = structure.suggested_domains(category_id, subcategory_id)
        dom_names = structure.domain_names()
        domains = st.pills(
            "What will it feed?",
            list(dom_names),
            format_func=lambda k: dom_names[k],
            selection_mode="multi",
            default=domains_default,
            key=f"wk_dom_{monday}_{category_id}_{subcategory_id}",
        )
        domain_str = ",".join(domains or [])

        day_values = taskedit.days_picker(
            f"wk_when_{monday}",
            max(monday, min(date.today(), monday + timedelta(days=6))),
        )
        batch_start = None
        if day_values:
            batch_start = taskedit.start_time_question(f"wk_start_{monday}")
            if batch_start and len(day_values) > 1:
                st.caption(
                    f"Each day's copy starts at {batch_start:%H:%M} — nudge "
                    "individual days later on the Calendar page."
                )
        batch_urgent = taskedit.urgent_toggle(f"wk_urgent_{monday}")
        st.caption(
            "Unscheduled work waits in this week's list; pull it into a day "
            "from the Today page when you get there."
        )

        def add_milestone_rows(rows, prefix: str) -> list[tuple]:
            """Checkbox plus its own estimate, one line per milestone."""
            chosen = []
            for r in rows.to_dict("records"):
                mkind = planning.milestone_kind(r["kind"])
                on_week = (mkind, int(r["id"])) in already
                with st.container(horizontal=True, vertical_alignment="center"):
                    picked = st.checkbox(
                        r["name"],
                        key=f"{prefix}_{mkind}_{r['id']}",
                        disabled=on_week,
                        width="stretch",
                    )
                    if r["kind"] in ("output", "project"):
                        st.badge(
                            r["kind"],
                            icon=":material/inventory_2:",
                            color="violet",
                        )
                    if r["status"] == "doing":
                        st.badge("in progress", color="blue")
                    if on_week:
                        st.badge("already this week", icon=":material/check:", color="green")
                    mins = st.number_input(
                        "Minutes",
                        min_value=15,
                        max_value=600,
                        value=90 if r["kind"] not in ("output", "project") else 150,
                        step=15,
                        key=f"{prefix}_min_{mkind}_{r['id']}",
                        label_visibility="collapsed",
                        width=110,
                    )
                if picked and not on_week:
                    chosen.append((r, mkind, int(mins)))
            return chosen

        st.markdown("**Milestones here**")
        selected = []
        if len(here):
            selected += add_milestone_rows(here, f"wk_ms_{monday}")
        else:
            st.caption(
                "No open milestones filed under this one — add the work as a "
                "task below."
            )

        if len(elsewhere):
            with st.expander(
                f"Other open milestones in {track['name']} ({len(elsewhere)})",
                icon=":material/more_horiz:",
            ):
                selected += add_milestone_rows(elsewhere, f"wk_msx_{monday}")

        st.markdown("**Or something not on the list**")
        with st.container(horizontal=True):
            free_title = st.text_input(
                "Task",
                key=f"wk_free_{monday}",
                placeholder="e.g. Draw the buck converter schematic",
                label_visibility="collapsed",
            )
            free_minutes = st.number_input(
                "Minutes",
                min_value=15,
                max_value=600,
                value=90,
                step=15,
                key=f"wk_freemin_{monday}",
                label_visibility="collapsed",
                width=110,
            )

        # No day chosen means one unscheduled copy; several days mean one task
        # per day, so "Tuesday, Wednesday and Friday" becomes three sessions.
        target_days = day_values or [None]
        per_day = len(selected) + (1 if free_title.strip() else 0)
        total_new = per_day * len(target_days)
        minutes_each = sum(m for _, _, m in selected) + (
            int(free_minutes) if free_title.strip() else 0
        )
        added_minutes = minutes_each * len(target_days)

        if per_day and len(target_days) > 1:
            st.caption(
                f"{per_day} item(s) × {len(target_days)} day(s) = "
                f"{total_new} tasks, {ui.hours_text(added_minutes)} in total."
            )

        if st.button(
            f"Add {total_new} task(s) · {ui.hours_text(added_minutes)}"
            if total_new
            else "Add to the week",
            type="primary",
            icon=":material/playlist_add:",
            disabled=not total_new,
            key=f"wk_add_{monday}",
        ):
            for when in target_days:
                made = []
                for r, mkind, mins in selected:
                    made.append(
                        planning.add_task(
                            monday,
                            track_id,
                            r["name"],
                            mins,
                            day=when,
                            milestone_kind=mkind,
                            milestone_id=int(r["id"]),
                            category_id=category_id,
                            subcategory_id=subcategory_id,
                            domains=domain_str,
                            urgent=batch_urgent,
                        )
                    )
                if free_title.strip():
                    made.append(
                        planning.add_task(
                            monday,
                            track_id,
                            free_title.strip(),
                            int(free_minutes),
                            day=when,
                            category_id=category_id,
                            subcategory_id=subcategory_id,
                            domains=domain_str,
                            urgent=batch_urgent,
                        )
                    )
                if when is not None and batch_start is not None:
                    for tid in made:
                        planning.set_task_time(tid, batch_start.strftime("%H:%M"))
            st.toast(f"{total_new} added")
            st.rerun()

        st.caption(
            "Finishing a task linked to a milestone ticks the milestone off "
            "too — that is what moves goal completion."
        )

    tsk = adh["tasks"]

    if len(tsk):
        live = tsk[tsk["status"] != "dropped"]
        by_track = (
            live.groupby("track", as_index=False)["planned_hours"]
            .sum()
            .merge(
                adh["budget"][["name", "planned_hours"]].rename(
                    columns={"name": "track", "planned_hours": "budget_hours"}
                ),
                on="track",
                how="right",
            )
            .fillna({"planned_hours": 0.0})
        )
        over = by_track[by_track["planned_hours"] > by_track["budget_hours"] + 0.01]
        if len(over):
            st.warning(
                "More task time than budget in: "
                + ", ".join(
                    f"**{r['track']}** ({r['planned_hours']:.1f} h of "
                    f"{r['budget_hours']:.1f} h)"
                    for r in over.to_dict("records")
                ),
                icon=":material/schedule:",
            )

    st.markdown("#### This week's work")
    if not len(tsk):
        st.caption("Nothing planned yet. Add work above.")
    else:
        days = [monday + timedelta(days=i) for i in range(7)]
        groups = [(None, "Unscheduled")] + [
            (d, f"{ui.DAY_NAMES[d.weekday()]} {d:%d %b}") for d in days
        ]
        for day, heading in groups:
            if day is None:
                chunk = tsk[tsk["day"].isna()]
            else:
                chunk = tsk[tsk["day"] == day.isoformat()]
            if not len(chunk):
                continue
            planned = chunk[chunk["status"] != "dropped"]["planned_minutes"].sum()
            with st.container(border=True):
                with st.container(horizontal=True, vertical_alignment="center"):
                    st.markdown(f"**{heading}**")
                    st.badge(ui.hours_text(planned), color="gray")
                    if day == date.today():
                        st.badge("Today", icon=":material/today:", color="violet")
                for t in chunk.to_dict("records"):
                    with st.container(horizontal=True, vertical_alignment="center"):
                        # Status and day are in the widget keys so a change
                        # made in the editor rebuilds these controls instead
                        # of a stale value quietly undoing it.
                        done = st.checkbox(
                            t["title"],
                            value=t["status"] == "done",
                            key=f"wk_done_{t['id']}_{t['status']}",
                            width="stretch",
                        )
                        if done != (t["status"] == "done"):
                            planning.set_task_status(
                                int(t["id"]), "done" if done else "todo"
                            )
                            st.rerun()
                        taskedit.badges(t, date.today())
                        ui.chip(
                            structure.path_label(
                                t["track"],
                                t["category"] or None,
                                t["subcategory"] or None,
                            ),
                            t["color"],
                        )
                        st.caption(
                            f"{ui.hours_text(t['planned_minutes'])} planned"
                            + (
                                f" · {ui.hours_text(t['logged_minutes'])} logged"
                                if t["logged_minutes"]
                                else ""
                            )
                        )
                        moved = st.selectbox(
                            "Move to",
                            ["Unscheduled"] + days,
                            index=0 if day is None else days.index(day) + 1,
                            format_func=lambda d: "Unscheduled"
                            if isinstance(d, str)
                            else f"{ui.DAY_NAMES[d.weekday()][:3]} {d:%d}",
                            key=f"wk_day_{t['id']}_{t['day']}",
                            label_visibility="collapsed",
                        )
                        target = None if moved == "Unscheduled" else moved
                        if (target.isoformat() if target else None) != t["day"]:
                            planning.schedule_task(int(t["id"]), target)
                            st.rerun()
                        taskedit.urgent_button(t, "wk")
                        taskedit.edit_button(t, "wk")


# --- review -----------------------------------------------------------------

with review_tab:
    st.markdown("#### How the week actually went")
    bud = adh["budget"].rename(columns={"name": "track"})
    st.altair_chart(
        ui.planned_vs_actual_chart(bud, "track", "planned_hours", "actual_hours")
    )
    st.caption("Pale bar is what you budgeted, solid bar is what you logged.")

    st.dataframe(
        bud[["track", "planned_hours", "actual_hours", "gap", "attainment"]],
        hide_index=True,
        column_config={
            "track": st.column_config.TextColumn("Track", pinned=True),
            "planned_hours": st.column_config.NumberColumn("Budget", format="%.1f h"),
            "actual_hours": st.column_config.NumberColumn("Logged", format="%.1f h"),
            "gap": st.column_config.NumberColumn("Gap", format="%+.1f h"),
            "attainment": st.column_config.ProgressColumn(
                "Attainment", min_value=0, max_value=1.5, format="percent"
            ),
        },
    )

    doms = scoring.domain_report(monday, sunday)
    if doms["hours"].sum() > 0:
        with st.container(border=True):
            st.markdown("**What the week fed**")
            st.altair_chart(
                alt.Chart(doms[doms["hours"] > 0])
                .mark_bar(cornerRadiusEnd=4, size=20)
                .encode(
                    x=alt.X("hours:Q", title="Hours"),
                    y=alt.Y("domain:N", title=None, sort="-x"),
                    color=ui.domain_color_field(legend=False),
                    tooltip=[
                        "domain",
                        alt.Tooltip("hours:Q", format=".1f"),
                        alt.Tooltip("coverage:Q", format=".0%"),
                    ],
                )
                .properties(height=max(len(doms[doms["hours"] > 0]) * 34, 90))
            )
            st.caption(
                "Robotics, AI, computer vision and personal growth cut across "
                "every track — this is the week seen through them."
            )

    tsk = adh["tasks"]
    if len(tsk):
        done = tsk[tsk["status"] == "done"]
        missed = tsk[tsk["status"].isin(["todo", "doing"])]
        c1, c2 = st.columns(2)
        with c1:
            with st.container(border=True):
                st.markdown(f"**Finished ({len(done)})**")
                for t in done.to_dict("records"):
                    st.markdown(f"- {t['title']}  ·  {ui.hours_text(t['logged_minutes'])}")
                if not len(done):
                    st.caption("Nothing yet.")
        with c2:
            with st.container(border=True):
                st.markdown(f"**Still open ({len(missed)})**")
                for t in missed.to_dict("records"):
                    st.markdown(f"- {t['title']}")
                if not len(missed):
                    st.caption("All clear.")

    st.markdown("#### Write it down")
    with st.form(f"review_{monday}", border=False):
        wins = st.text_area(
            "What went well", value=week["wins"], height=90,
            placeholder="The things worth repeating."
        )
        blockers = st.text_area(
            "What got in the way", value=week["blockers"], height=90,
            placeholder="Be specific — vague blockers repeat."
        )
        next_focus = st.text_area(
            "One thing to change next week", value=week["next_focus"], height=90,
            placeholder="This is shown to you when you plan next week.",
        )
        if st.form_submit_button("Save review", type="primary", icon=":material/save:"):
            planning.save_week(
                monday,
                wins=wins,
                blockers=blockers,
                next_focus=next_focus,
                reviewed_on=date.today().isoformat(),
            )
            st.toast("Review saved")
            st.rerun()
