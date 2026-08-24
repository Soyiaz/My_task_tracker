"""The day on a clock face: each scheduled task placed at an actual time.

The task's *day* is decided on the week page; this page decides *when* within
that day. Times live in the settings table as JSON (``planning.task_times``),
so the database schema stays exactly as it is.
"""

from datetime import date, datetime, time, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from tracker import planning, scoring, ui

ui.page_header(
    "Calendar",
    "Pick the hour each task happens. The day is chosen on the week page; "
    "the clock is chosen here.",
    ":material/calendar_clock:",
)
ui.require_tracks()

# Every block is drawn on this one throwaway date so the y-axis is purely a
# clock — the real day only decides which column a block stands in.
ANCHOR = date(2000, 1, 1)

if "cal_day" not in st.session_state:
    st.session_state.cal_day = date.today()


def _shift(days: int) -> None:
    st.session_state.cal_day = st.session_state.cal_day + timedelta(days=days)


def _today() -> None:
    st.session_state.cal_day = date.today()


bar = st.container(horizontal=True, vertical_alignment="bottom")
with bar:
    st.button(":material/chevron_left:", key="cal_prev", on_click=_shift, args=(-1,))
    st.date_input("Day", key="cal_day", width=170)
    st.button(":material/chevron_right:", key="cal_next", on_click=_shift, args=(1,))
    st.button("Today", key="cal_today", on_click=_today)

picked: date = st.session_state.cal_day
monday = scoring.week_start(picked)


# --- widget callbacks write BEFORE the rerun, so the chart is never ---------
# --- one interaction behind -------------------------------------------------


def _set_time(task_id: int, wkey: str) -> None:
    v = st.session_state.get(wkey)
    planning.set_task_time(task_id, v.strftime("%H:%M") if v else None)


def _clear_time(task_id: int, wkey: str) -> None:
    planning.set_task_time(task_id, None)
    st.session_state.pop(wkey, None)


def _pull_onto_day(task_id: int, day: date) -> None:
    planning.update_task(task_id, day=day)


def _parse(hhmm: str | None) -> time | None:
    try:
        return time.fromisoformat(hhmm) if hhmm else None
    except ValueError:
        return None


def _day_label(d: date) -> str:
    return f"{ui.DAY_NAMES[d.weekday()][:3]} {d.day}"


def _blocks(tasks: pd.DataFrame, times: dict[int, str], on: dict[int, date]) -> pd.DataFrame:
    rows = []
    for t in tasks.to_dict("records"):
        at = _parse(times.get(int(t["id"])))
        if at is None:
            continue
        start = datetime.combine(ANCHOR, at)
        end = start + timedelta(minutes=int(t["planned_minutes"]))
        end = min(end, datetime.combine(ANCHOR, time(23, 59)))  # clamp to the day
        minutes = int(t["planned_minutes"])
        title = t["title"] if len(t["title"]) <= 26 else t["title"][:25] + "…"
        rows.append(
            {
                "id": int(t["id"]),
                "task": t["title"],
                # a 15-minute sliver has no room for a caption; the tooltip has it
                "label": f"{title} · {at:%H:%M}" if minutes >= 30 else "",
                "track": t["track"],
                "category": t["category"] or "—",
                "col": _day_label(on[int(t["id"])]),
                "start": start,
                "end": end,
                "when": f"{start:%H:%M} – {end:%H:%M}",
                "planned": ui.hours_text(minutes),
                "status": planning.STATUS_UI[t["status"]],
                "is_done": t["status"] == "done",
            }
        )
    return pd.DataFrame(rows)


def _lanes(df: pd.DataFrame) -> pd.DataFrame:
    """Overlapping blocks in one column step sideways into their own lane
    instead of hiding one another."""
    parts = []
    for _, col in df.groupby("col", sort=False):
        col = col.sort_values(["start", "end"]).copy()
        ends: list[datetime] = []
        lanes = []
        for r in col.itertuples():
            for i, e in enumerate(ends):
                if r.start >= e:
                    lanes.append(i)
                    ends[i] = r.end
                    break
            else:
                lanes.append(len(ends))
                ends.append(r.end)
        col["lane"] = lanes
        parts.append(col)
    return pd.concat(parts, ignore_index=True)


def _clock_chart(blocks: pd.DataFrame, x_sort: list[str], legend: bool):
    lo = min([7] + [b.hour for b in blocks["start"]])
    hi = max([22] + [b.hour + 2 for b in blocks["end"]])
    domain = [
        datetime.combine(ANCHOR, time(hour=lo)).isoformat(),
        (datetime.combine(ANCHOR, time.min) + timedelta(hours=min(hi, 24))).isoformat(),
    ]

    base = alt.Chart(blocks)
    bars = base.mark_bar(cornerRadius=5).encode(
        x=alt.X(
            "col:N",
            sort=x_sort,
            axis=alt.Axis(title=None, labelAngle=0, orient="top"),
            scale=alt.Scale(domain=x_sort),
        ),
        xOffset=alt.XOffset("lane:N"),
        y=alt.Y(
            "start:T",
            axis=alt.Axis(format="%H:%M", title=None, grid=True),
            scale=alt.Scale(domain=domain),
        ),
        y2="end:T",
        color=ui.track_color_field(legend=legend),
        opacity=alt.condition(alt.datum.is_done, alt.value(0.45), alt.value(0.92)),
        tooltip=[
            alt.Tooltip("task:N", title="Task"),
            alt.Tooltip("track:N", title="Track"),
            alt.Tooltip("category:N", title="Category"),
            alt.Tooltip("when:N", title="When"),
            alt.Tooltip("planned:N", title="Planned"),
            alt.Tooltip("status:N", title="Status"),
        ],
    )
    text = base.mark_text(
        align="left", baseline="top", dx=4, dy=3, color="white", limit=150
    ).encode(
        x=alt.X("col:N", sort=x_sort, scale=alt.Scale(domain=x_sort)),
        xOffset=alt.XOffset("lane:N"),
        y=alt.Y("start:T", scale=alt.Scale(domain=domain)),
        text="label:N",
        opacity=alt.condition(alt.datum.is_done, alt.value(0.7), alt.value(1.0)),
    )
    return (bars + text).properties(height=560)


times = planning.task_times()
day_tab, week_tab = st.tabs(
    [":material/wb_sunny: The day", ":material/date_range: The whole week"]
)

with day_tab:
    tasks = planning.tasks(day=picked)
    if not len(tasks):
        st.info(
            f"Nothing is scheduled on {picked:%A %d %B}. Tasks get their day "
            "on **The week** page — once one lands here, you can give it a time.",
            icon=":material/event_available:",
        )
    else:
        on = {int(t): picked for t in tasks["id"]}
        blocks = _blocks(tasks, times, on)

        # the editor: one row per task, timed ones first, in clock order
        tasks = tasks.copy()
        tasks["_at"] = [times.get(int(i)) or "zz" for i in tasks["id"]]
        tasks = tasks.sort_values(["_at", "sort"])
        for t in tasks.to_dict("records"):
            tid = int(t["id"])
            wkey = f"cal_time_{tid}"
            row = st.container(horizontal=True, vertical_alignment="center")
            with row:
                st.time_input(
                    "Start",
                    value=_parse(times.get(tid)),
                    key=wkey,
                    step=timedelta(minutes=15),
                    on_change=_set_time,
                    args=(tid, wkey),
                    label_visibility="collapsed",
                    width=110,
                )
                done = t["status"] == "done"
                flag = ":material/check_circle: " if done else ""
                urgent = " :material/priority_high:" if t["urgent"] and not done else ""
                st.markdown(
                    f"{flag}**{t['title']}**{urgent}  \n"
                    f":small[{t['track']}"
                    + (f" · {t['category']}" if t["category"] else "")
                    + f" · {ui.hours_text(int(t['planned_minutes']))}]",
                    width="stretch",
                )
                if times.get(tid):
                    st.button(
                        ":material/backspace:",
                        key=f"cal_clear_{tid}",
                        on_click=_clear_time,
                        args=(tid, wkey),
                        help="Take the time off — the task stays on this day",
                    )

        untimed = len(tasks) - len(blocks)
        if untimed:
            st.caption(
                f"{untimed} task{'s' if untimed != 1 else ''} on this day "
                "still without a time — set one on the left to see "
                f"{'them' if untimed != 1 else 'it'} on the clock."
            )

        if len(blocks):
            blocks = _lanes(blocks)
            if (blocks["lane"] > 0).any():
                st.warning(
                    "Some tasks overlap — they sit side by side on the clock.",
                    icon=":material/stacks:",
                )
            st.altair_chart(
                _clock_chart(blocks, [_day_label(picked)], legend=False),
                width="stretch",
            )

    # tasks this week that have no day yet can be pulled onto this one
    loose = planning.tasks(monday=monday, unscheduled_only=True)
    if len(loose):
        with st.expander(
            f"This week's tasks without a day ({len(loose)})",
            icon=":material/move_down:",
        ):
            for t in loose.to_dict("records"):
                tid = int(t["id"])
                row = st.container(horizontal=True, vertical_alignment="center")
                with row:
                    st.markdown(
                        f"**{t['title']}**  \n"
                        f":small[{t['track']}"
                        + (f" · {t['category']}" if t["category"] else "")
                        + f" · {ui.hours_text(int(t['planned_minutes']))}]",
                        width="stretch",
                    )
                    st.button(
                        f"Do it {picked:%a %d}",
                        key=f"cal_pull_{tid}",
                        icon=":material/today:",
                        on_click=_pull_onto_day,
                        args=(tid, picked),
                    )

with week_tab:
    st.caption(f"{scoring.week_label(monday)} · times are set per day on the first tab.")
    week_tasks = planning.tasks(monday=monday)
    scheduled = week_tasks[week_tasks["day"].notna()] if len(week_tasks) else week_tasks
    if not len(scheduled):
        st.info(
            "No tasks have a day yet this week — give them one on **The week** "
            "page and they appear here.",
            icon=":material/event_available:",
        )
    else:
        on = {
            int(t["id"]): date.fromisoformat(t["day"])
            for t in scheduled.to_dict("records")
        }
        blocks = _blocks(scheduled, times, on)
        labels = [_day_label(monday + timedelta(days=i)) for i in range(7)]
        if len(blocks):
            blocks = _lanes(blocks)
            st.altair_chart(_clock_chart(blocks, labels, legend=True), width="stretch")
        left = len(scheduled) - len(blocks)
        if left:
            st.caption(
                f"{left} scheduled task{'s' if left != 1 else ''} this week "
                f"still {'have' if left != 1 else 'has'} no time of day."
            )
