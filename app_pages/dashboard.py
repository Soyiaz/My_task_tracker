"""How the summer is going, at a glance."""

from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from tracker import planning, scoring, structure, ui

h = scoring.headline()
rep = scoring.track_report()
log = scoring.time_log()
history = planning.plan_history()
doms = scoring.domain_report()

ui.page_header(
    "Dashboard",
    f"{h['start']:%d %b} – {h['end']:%d %b} · day {h['days_done']} of "
    f"{h['total_days']} · {h['days_left']} days left",
    ":material/speed:",
)
ui.require_tracks()


# --- the two numbers --------------------------------------------------------

weekly_hours = []
for monday in scoring.plan_weeks():
    if monday > scoring.week_start(date.today()):
        break
    sunday = monday + timedelta(days=6)
    weekly_hours.append(
        float(log[(log["day"] >= monday) & (log["day"] <= sunday)]["hours"].sum())
        if len(log)
        else 0.0
    )

with st.container(horizontal=True):
    st.metric(
        "Goal completion",
        f"{h['goal_completion']:.0%}",
        delta=f"{h['goal_completion'] - h['fraction']:+.0%} vs elapsed time",
        border=True,
        help="Weighted share of the whole plan that is finished. This is your "
        "distance to the ultimate goal, and it only goes up.",
    )
    st.metric(
        "On pace",
        f"{h['on_pace']:.0%}",
        border=True,
        help="Half hours-against-plan, half milestones-against-pace. 100% "
        "means today looks exactly like the plan said it would.",
    )
    st.metric(
        "Hours logged",
        f"{h['hours_logged']:.0f} h",
        delta=f"{-h['hours_behind']:+.0f} h vs plan",
        border=True,
        chart_data=weekly_hours or None,
        chart_type="bar",
        help=f"The plan expected {h['hours_expected']:.0f} h by now. "
        "Sparkline is hours per week.",
    )
    st.metric(
        "Milestones done",
        f"{h['milestones_done']} / {h['milestones_total']}",
        border=True,
    )

with st.container(border=True):
    st.markdown("**Progress toward the ultimate goal**")
    st.progress(
        min(h["goal_completion"], 1.0),
        text=f"{h['goal_completion']:.0%} of the plan complete · "
        f"{h['fraction']:.0%} of the summer gone",
    )
    if h["days_left"] > 0:
        st.caption(
            f"To land the full {h['planned_hours']:.0f} planned hours you need "
            f"**{h['needed_per_week']:.1f} h/week** for the remaining "
            f"{h['weeks_left']:.1f} weeks."
        )
    else:
        st.caption("The window has closed — this is the final standing.")


# --- the lenses -------------------------------------------------------------

with st.container(border=True):
    st.markdown("**Measured by domain**")
    st.caption(
        "Robotics, AI, computer vision and personal growth cut across every "
        "track. A club project, a PCB board and a FloLabs robot can all be "
        "feeding robotics — this is the summer seen through what the work was "
        "*for*, not where it was filed."
    )

    real = doms[doms["domain_key"] != "__none__"]
    if doms["hours"].sum() == 0:
        st.caption("Nothing logged yet, so nothing to measure.")
    else:
        with st.container(horizontal=True):
            for d in doms.to_dict("records"):
                if d["domain_key"] == "__none__" and d["hours"] == 0:
                    continue
                st.metric(
                    d["domain"],
                    f"{d['coverage']:.0%}",
                    delta=(
                        f"{d['gap']:+.0%} vs target"
                        if d["domain_key"] != "__none__"
                        else None
                    ),
                    border=True,
                    help=f"{d['hours']:.1f} h across {d['sessions']} session(s).",
                )

        left, right = st.columns([3, 2])
        with left:
            st.altair_chart(
                ui.planned_vs_actual_chart(
                    real.assign(
                        target_hours=real["target_share"] * doms["hours"].sum()
                    ).rename(columns={"domain": "track"}),
                    "track",
                    "target_hours",
                    "hours",
                    height=200,
                )
            )
            st.caption("Pale bar is the target share of your hours; solid is actual.")
        with right:
            if len(log):
                ex = structure.explode_domains(log[["id", "hours", "domains", "day"]])
                ex["week"] = ex["day"].map(
                    lambda d: scoring.week_start(d).isoformat()
                )
                weekly_dom = ex.groupby(["week", "domain"], as_index=False)["hours"].sum()
                st.altair_chart(
                    alt.Chart(weekly_dom)
                    .mark_area(opacity=0.85)
                    .encode(
                        x=alt.X("week:T", title=None),
                        y=alt.Y("hours:Q", title="Hours", stack="normalize"),
                        color=ui.domain_color_field(),
                        tooltip=["week", "domain", alt.Tooltip("hours:Q", format=".1f")],
                    )
                    .properties(height=200)
                )
                st.caption("How the mix has shifted week to week.")

        thin = scoring.thinnest_domain()
        if thin and thin["gap"] < -0.02:
            st.warning(
                f"**{thin['domain']}** is the thinnest lens — {thin['coverage']:.0%} "
                f"of your hours against a {thin['target_share']:.0%} target. "
                "Anything in any track that feeds it will close the gap.",
                icon=":material/lens_blur:",
            )
        unassigned = doms[doms["domain_key"] == "__none__"]
        if len(unassigned) and unassigned.iloc[0]["coverage"] > 0.15:
            st.caption(
                f"{unassigned.iloc[0]['coverage']:.0%} of your hours are not "
                "tagged with a domain, which blunts this whole view."
            )


# --- where to put the next block of work ------------------------------------

tips = scoring.advice()
with st.container(border=True):
    st.markdown("**Work on this next**")
    if not tips:
        st.success("Every track is on pace. Keep the rhythm.", icon=":material/check:")
    cols = st.columns(len(tips)) if tips else []
    for col, tip in zip(cols, tips):
        with col, st.container(border=True):
            with st.container(horizontal=True, vertical_alignment="center"):
                st.markdown(f"{tip['icon']} **{tip['track']}**")
                ui.status_badge(tip["status"])
            st.caption(tip["why"].capitalize())
            st.markdown(f"Give it **{tip['suggest_hours']:.1f} h** next week:")
            for nxt in tip["next_up"][:3]:
                st.markdown(f"- {nxt}")


# --- how the planning habit is holding --------------------------------------

with st.container(border=True):
    st.markdown("**The planning habit**")
    if not len(history):
        st.caption("No weeks yet.")
    else:
        planned_weeks = int(history["planned"].sum())
        reviewed_weeks = int(history["reviewed"].sum())
        with_tasks = history[history["tasks_planned"] > 0]
        with st.container(horizontal=True):
            st.metric(
                "Weeks planned",
                f"{planned_weeks} / {len(history)}",
                border=True,
                help="Weeks where you set a budget before they started.",
            )
            st.metric(
                "Weeks reviewed",
                f"{reviewed_weeks} / {len(history)}",
                border=True,
            )
            st.metric(
                "Average hit rate",
                f"{with_tasks['hit_rate'].mean():.0%}" if len(with_tasks) else "—",
                border=True,
                help="Tasks finished out of tasks planned, averaged across weeks.",
            )
            st.metric(
                "Budget attainment",
                f"{history['hours_attainment'].mean():.0%}",
                border=True,
                help="Hours logged against hours budgeted, averaged across weeks.",
            )

        chart_df = history.melt(
            id_vars="week",
            value_vars=["planned_hours", "actual_hours"],
            var_name="kind",
            value_name="hours",
        )
        chart_df["kind"] = chart_df["kind"].map(
            {"planned_hours": "Budgeted", "actual_hours": "Logged"}
        )
        st.altair_chart(
            alt.Chart(chart_df)
            .mark_bar(cornerRadiusEnd=3)
            .encode(
                x=alt.X("week:N", title=None, sort=list(history["week"])),
                xOffset=alt.XOffset("kind:N"),
                y=alt.Y("hours:Q", title="Hours"),
                color=alt.Color(
                    "kind:N",
                    title=None,
                    scale=alt.Scale(
                        domain=["Budgeted", "Logged"], range=["#94a3b8", "#6366f1"]
                    ),
                    legend=alt.Legend(orient="bottom"),
                ),
                tooltip=["week", "kind", alt.Tooltip("hours:Q", format=".1f")],
            )
            .properties(height=220)
        )


# --- track health -----------------------------------------------------------

with st.container(border=True):
    st.markdown("**Track by track**")
    view = rep[
        [
            "track",
            "status",
            "progress",
            "hours",
            "expected_hours",
            "hour_gap",
            "target_share",
            "actual_share",
            "health",
        ]
    ].copy()
    st.dataframe(
        view,
        hide_index=True,
        column_config={
            "track": st.column_config.TextColumn("Track", pinned=True),
            "status": st.column_config.TextColumn("Status"),
            "progress": st.column_config.ProgressColumn(
                "Milestones", min_value=0, max_value=1, format="percent"
            ),
            "hours": st.column_config.NumberColumn("Hours", format="%.1f h"),
            "expected_hours": st.column_config.NumberColumn("Expected", format="%.1f h"),
            "hour_gap": st.column_config.NumberColumn("Gap", format="%+.1f h"),
            "target_share": st.column_config.NumberColumn(
                "Planned share", format="percent"
            ),
            "actual_share": st.column_config.NumberColumn("Actual share", format="percent"),
            "health": st.column_config.ProgressColumn(
                "Health", min_value=0, max_value=1, format="percent"
            ),
        },
    )


# --- charts -----------------------------------------------------------------

left, right = st.columns(2)

with left:
    with st.container(border=True):
        st.markdown("**Hours: planned vs actual**")
        st.altair_chart(
            ui.planned_vs_actual_chart(rep, "track", "expected_hours", "hours")
        )
        st.caption("Pale bar is what the plan expected by today.")

with right:
    with st.container(border=True):
        st.markdown("**Time share vs the plan**")
        share = pd.concat(
            [
                pd.DataFrame(
                    {"track": rep["track"], "share": rep["target_share"], "kind": "Planned"}
                ),
                pd.DataFrame(
                    {"track": rep["track"], "share": rep["actual_share"], "kind": "Actual"}
                ),
            ]
        )
        st.altair_chart(
            alt.Chart(share)
            .mark_bar(cornerRadiusEnd=3)
            .encode(
                y=alt.Y("track:N", title=None, sort=list(rep["track"])),
                x=alt.X(
                    "share:Q",
                    title="Share of logged time",
                    axis=alt.Axis(format="%"),
                ),
                yOffset=alt.YOffset("kind:N"),
                color=alt.Color(
                    "kind:N",
                    title=None,
                    scale=alt.Scale(
                        domain=["Planned", "Actual"], range=["#94a3b8", "#6366f1"]
                    ),
                    legend=alt.Legend(orient="bottom"),
                ),
                tooltip=["track", "kind", alt.Tooltip("share:Q", format=".0%")],
            )
            .properties(height=260)
        )


with st.container(border=True):
    st.markdown("**Daily hours**")
    window_start = max(h["start"], date.today() - timedelta(days=27))
    if len(log):
        daily = (
            log[log["day"] >= window_start]
            .groupby(["day", "track"], as_index=False)["hours"]
            .sum()
        )
    else:
        daily = pd.DataFrame(columns=["day", "track", "hours"])
    if len(daily):
        chart = (
            alt.Chart(daily)
            .mark_bar(cornerRadiusEnd=2)
            .encode(
                x=alt.X("day:T", title=None),
                y=alt.Y("hours:Q", title="Hours"),
                color=ui.track_color_field(),
                tooltip=["day:T", "track", alt.Tooltip("hours:Q", format=".1f")],
            )
            .properties(height=240)
        )
        target = (
            alt.Chart(pd.DataFrame({"y": [h["weekly_hours"] / 7]}))
            .mark_rule(strokeDash=[4, 4], color="#94a3b8")
            .encode(y="y:Q")
        )
        st.altair_chart(chart + target)
        st.caption("Dashed line is the daily average the weekly target implies.")
    else:
        st.caption("Nothing logged in the last four weeks.")


with st.container(border=True):
    st.markdown("**Cumulative hours against the plan**")
    span = pd.DataFrame({"day": pd.date_range(h["start"], h["end"]).date})
    span["planned"] = [(i + 1) * h["weekly_hours"] / 7 for i in range(len(span))]
    if len(log):
        span = span.merge(log.groupby("day", as_index=False)["hours"].sum(), on="day", how="left")
    else:
        span["hours"] = 0.0
    span["hours"] = span["hours"].fillna(0.0)
    span["actual"] = span["hours"].cumsum()
    span.loc[span["day"] > date.today(), "actual"] = None

    curve = span.melt(
        id_vars="day", value_vars=["planned", "actual"], var_name="line", value_name="h"
    ).dropna()
    curve["line"] = curve["line"].map({"planned": "Plan", "actual": "Actual"})
    st.altair_chart(
        alt.Chart(curve)
        .mark_line(strokeWidth=2.5)
        .encode(
            x=alt.X("day:T", title=None),
            y=alt.Y("h:Q", title="Cumulative hours"),
            color=alt.Color(
                "line:N",
                title=None,
                scale=alt.Scale(domain=["Plan", "Actual"], range=["#94a3b8", "#6366f1"]),
                legend=alt.Legend(orient="bottom"),
            ),
            strokeDash=alt.StrokeDash(
                "line:N",
                scale=alt.Scale(domain=["Plan", "Actual"], range=[[5, 4], [1, 0]]),
                legend=None,
            ),
            tooltip=["day:T", "line", alt.Tooltip("h:Q", format=".0f")],
        )
        .properties(height=260)
    )
