"""Registered time, read back as a week and as a month."""

from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from tracker import planning, scoring, structure, ui

ui.page_header(
    "Reports",
    "Time as it was actually registered — for the week, then the month — "
    "against what the plan asked for.",
    ":material/calendar_month:",
)
ui.require_tracks()

FOCUS = ui.FOCUS


def verdict(attainment: float) -> tuple[str, str]:
    if attainment >= 1.0:
        return "Target met", "success"
    if attainment >= 0.8:
        return "Close", "info"
    if attainment >= 0.5:
        return "Short", "warning"
    return "Well short", "error"


def render(r: dict, prev: dict | None, adh: dict | None = None) -> None:
    label, tone = verdict(r["attainment"])
    delta = None
    if prev is not None:
        delta = f"{r['hours'] - prev['hours']:+.1f} h vs previous"

    with st.container(horizontal=True):
        st.metric("Hours registered", f"{r['hours']:.1f} h", delta=delta, border=True)
        st.metric(
            "Against target",
            f"{r['attainment']:.0%}",
            delta=f"{r['gap']:+.1f} h",
            border=True,
            help=f"Target so far: {r['target_hours']:.1f} h of "
            f"{r['full_target_hours']:.1f} h for the whole period.",
        )
        st.metric(
            "Days worked",
            f"{r['active_days']} / {r['elapsed_days'] or r['days']}",
            border=True,
            help=f"{r['avg_hours_per_active_day']:.1f} h on the days you worked",
        )
        st.metric(
            "Average focus",
            FOCUS.get(round(r["avg_focus"]), "—") if r["avg_focus"] else "—",
            border=True,
            help="From the focus rating on each entry.",
        )

    getattr(st, tone)(
        f"**{label}** — {r['hours']:.1f} h registered against a "
        f"{r['target_hours']:.1f} h target"
        + (
            f", finishing {len(r['finished'])} milestone(s)."
            if len(r["finished"])
            else ", with no milestones finished."
        )
    )
    if r["in_progress"]:
        st.caption(
            f"This period is still running: judged on the {r['elapsed_days']} "
            f"day(s) so far, not the full {r['full_target_hours']:.0f} h."
        )

    if adh is not None:
        with st.container(border=True):
            with st.container(horizontal=True, vertical_alignment="center"):
                st.markdown("**Against the plan you wrote**")
                if adh["is_planned"]:
                    st.badge("Planned", icon=":material/event_available:", color="green")
                else:
                    st.badge(
                        "This week was never planned",
                        icon=":material/event_busy:",
                        color="orange",
                    )
            if adh["is_planned"] or adh["tasks_planned"]:
                with st.container(horizontal=True):
                    st.metric(
                        "Budgeted",
                        ui.hours_text(adh["planned_hours"] * 60),
                        delta=f"{adh['actual_hours'] - adh['planned_hours']:+.1f} h logged",
                        border=True,
                    )
                    st.metric(
                        "Budget attainment",
                        f"{adh['hours_attainment']:.0%}",
                        border=True,
                    )
                    st.metric(
                        "Tasks",
                        f"{adh['tasks_done']} / {adh['tasks_planned']}",
                        border=True,
                        help=f"{adh['tasks_dropped']} dropped.",
                    )
                    st.metric("Hit rate", f"{adh['hit_rate']:.0%}", border=True)
                bud = adh["budget"].rename(columns={"name": "track"})
                st.altair_chart(
                    ui.planned_vs_actual_chart(
                        bud, "track", "planned_hours", "actual_hours", height=200
                    )
                )
                week_row = planning.get_week(adh["monday"])
                if week_row["intention"]:
                    st.caption(f"The intention was: *{week_row['intention']}*")
            else:
                st.caption(
                    "No budget and no tasks were set for this week, so there is "
                    "nothing to compare against."
                )

    left, right = st.columns([3, 2])

    with left:
        with st.container(border=True):
            st.markdown("**By track**")
            view = r["by_track"].copy()
            st.dataframe(
                view[
                    [
                        "track",
                        "hours",
                        "target_hours",
                        "gap",
                        "target_share",
                        "actual_share",
                        "sessions",
                    ]
                ],
                hide_index=True,
                column_config={
                    "track": st.column_config.TextColumn("Track", pinned=True),
                    "hours": st.column_config.NumberColumn("Hours", format="%.1f h"),
                    "target_hours": st.column_config.NumberColumn(
                        "Target", format="%.1f h"
                    ),
                    "gap": st.column_config.NumberColumn("Gap", format="%+.1f h"),
                    "target_share": st.column_config.NumberColumn(
                        "Planned share", format="percent"
                    ),
                    "actual_share": st.column_config.NumberColumn(
                        "Actual share", format="percent"
                    ),
                    "sessions": st.column_config.NumberColumn("Sessions"),
                },
            )
            worst = view.sort_values("gap").head(1)
            best = view.sort_values("gap", ascending=False).head(1)
            if len(worst) and r["hours"] > 0:
                st.caption(
                    f"Most under-served: **{worst.iloc[0]['track']}** "
                    f"({worst.iloc[0]['gap']:+.1f} h). "
                    f"Most over-served: **{best.iloc[0]['track']}** "
                    f"({best.iloc[0]['gap']:+.1f} h)."
                )

    with right:
        with st.container(border=True):
            st.markdown("**Day by day**")
            if len(r["log"]):
                daily = r["log"].groupby(["day", "track"], as_index=False)["hours"].sum()
                chart = (
                    alt.Chart(daily)
                    .mark_bar(cornerRadiusEnd=2)
                    .encode(
                        x=alt.X("day:T", title=None),
                        y=alt.Y("hours:Q", title="Hours"),
                        color=ui.track_color_field(),
                        tooltip=["day:T", "track", alt.Tooltip("hours:Q", format=".1f")],
                    )
                    .properties(height=220)
                )
            else:
                chart = (
                    alt.Chart(r["by_day"])
                    .mark_bar()
                    .encode(
                        x=alt.X("day:T", title=None),
                        y=alt.Y("hours:Q", title="Hours"),
                    )
                    .properties(height=220)
                )
            st.altair_chart(chart)

    col_a, col_b = st.columns(2)
    with col_a:
        with st.container(border=True):
            st.markdown("**Milestones finished**")
            if len(r["finished"]):
                st.dataframe(
                    r["finished"][["track", "section", "name", "done_on"]],
                    hide_index=True,
                    column_config={
                        "track": st.column_config.TextColumn("Track"),
                        "section": st.column_config.TextColumn("Section"),
                        "name": st.column_config.TextColumn("Milestone", width="medium"),
                        "done_on": st.column_config.TextColumn("Done"),
                    },
                )
            else:
                st.caption("None closed out in this period.")

    with col_b:
        with st.container(border=True):
            st.markdown("**What the time went on**")
            if len(r["by_category"]):
                st.dataframe(
                    r["by_category"].head(14),
                    hide_index=True,
                    column_config={
                        "track": st.column_config.TextColumn("Track"),
                        "category": st.column_config.TextColumn("Category"),
                        "subcategory": st.column_config.TextColumn("Subcategory"),
                        "hours": st.column_config.NumberColumn("Hours", format="%.1f h"),
                        "sessions": st.column_config.NumberColumn("Sessions"),
                    },
                )
            else:
                st.caption("Nothing registered in this period.")

    doms = r["by_domain"]
    if doms["hours"].sum() > 0:
        with st.container(border=True):
            st.markdown("**What it fed**")
            live = doms[doms["hours"] > 0]
            with st.container(horizontal=True):
                for d in live.to_dict("records"):
                    st.metric(
                        d["domain"],
                        f"{d['coverage']:.0%}",
                        delta=f"{d['hours']:.1f} h",
                        delta_color="off",
                        border=True,
                    )
            st.altair_chart(
                alt.Chart(live)
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
                .properties(height=max(len(live) * 34, 90))
            )

    with st.expander("Every entry in this period"):
        log = r["log"]
        if len(log):
            names = structure.domain_names()
            view = log[
                ["day", "what", "title", "hours", "domains", "focus", "notes"]
            ].copy()
            view["domains"] = log["domains"].map(
                lambda v: ", ".join(names.get(k, k) for k in structure.split(v)) or "—"
            )
            view["focus"] = view["focus"].map(
                lambda v: FOCUS.get(v, "—") if pd.notna(v) else "—"
            )
            st.dataframe(
                view,
                hide_index=True,
                column_config={
                    "day": st.column_config.TextColumn("Day"),
                    "what": st.column_config.TextColumn("Filed under", width="medium"),
                    "title": st.column_config.TextColumn("What exactly", width="medium"),
                    "hours": st.column_config.NumberColumn("Hours", format="%.2f h"),
                    "domains": st.column_config.TextColumn("Fed"),
                    "notes": st.column_config.TextColumn("Notes", width="medium"),
                },
            )
        else:
            st.caption("Nothing registered.")


weekly, monthly, whole = st.tabs(["Week", "Month", "Whole summer"])

with weekly:
    mondays = scoring.plan_weeks()
    current = scoring.week_start(date.today())
    default = mondays.index(current) if current in mondays else len(mondays) - 1
    monday = st.selectbox(
        "Week",
        mondays,
        index=default,
        format_func=scoring.week_label,
        key="week_pick",
    )
    prev_monday = monday - timedelta(days=7)
    render(
        scoring.week_report(monday),
        scoring.week_report(prev_monday) if prev_monday in mondays else None,
        adh=planning.week_adherence(monday),
    )
    review = planning.get_week(monday)
    if any(review[k] for k in ("wins", "blockers", "next_focus")):
        with st.container(border=True):
            st.markdown("**Your review of this week**")
            for label, key, icon in (
                ("What went well", "wins", ":material/thumb_up:"),
                ("What got in the way", "blockers", ":material/report:"),
                ("One thing to change", "next_focus", ":material/arrow_forward:"),
            ):
                if review[key]:
                    st.markdown(f"{icon} **{label}** — {review[key]}")

with monthly:
    months = scoring.plan_months()
    now = (date.today().year, date.today().month)
    default = months.index(now) if now in months else len(months) - 1
    ym = st.selectbox(
        "Month",
        months,
        index=default,
        format_func=lambda t: f"{date(t[0], t[1], 1):%B %Y}",
        key="month_pick",
    )
    idx = months.index(ym)
    render(
        scoring.month_report(*ym),
        scoring.month_report(*months[idx - 1]) if idx > 0 else None,
    )

with whole:
    e = scoring.elapsed()
    render(scoring.period_report(e["start"], e["end"]), None)

    st.markdown("### Week by week")
    rows = []
    for monday in scoring.plan_weeks():
        wr = scoring.week_report(monday)
        wa = planning.week_adherence(monday)
        rows.append(
            {
                "week": scoring.week_label(monday),
                "planned": wa["is_planned"],
                "hours": wr["hours"],
                "target": wr["full_target_hours"],
                "attainment": (
                    wr["hours"] / wr["full_target_hours"]
                    if wr["full_target_hours"]
                    else 0.0
                ),
                "days worked": wr["active_days"],
                "tasks": f"{wa['tasks_done']}/{wa['tasks_planned']}"
                if wa["tasks_planned"]
                else "—",
                "hit_rate": wa["hit_rate"] if wa["tasks_planned"] else None,
                "milestones": len(wr["finished"]),
            }
        )
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        column_config={
            "week": st.column_config.TextColumn("Week", pinned=True),
            "planned": st.column_config.CheckboxColumn("Planned"),
            "hours": st.column_config.NumberColumn("Hours", format="%.1f h"),
            "target": st.column_config.NumberColumn("Target", format="%.1f h"),
            "attainment": st.column_config.ProgressColumn(
                "Attainment", min_value=0, max_value=1.5, format="percent"
            ),
            "tasks": st.column_config.TextColumn("Tasks done"),
            "hit_rate": st.column_config.ProgressColumn(
                "Hit rate", min_value=0, max_value=1, format="percent"
            ),
            "milestones": st.column_config.NumberColumn("Milestones done"),
        },
    )
