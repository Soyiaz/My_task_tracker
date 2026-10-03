"""Everything with a date, on one calendar — and every item is a door.

Tasks, application deadlines, planned application days, exams, lectures and
study sessions are drawn together: a month grid, a week on a clock, a day
in detail, or a plain list. Tap any of them and you land on the page where
it was saved, with that item pulled to the top (``agenda.go``).

Every task carries a day and a time. The ones made before that rule still
missing either are listed at the bottom with a one-click fix.
"""

import calendar as cal
from datetime import date, datetime, time, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from tracker import agenda, planning, scoring, store, ui

ui.page_header(
    "Calendar",
    "Tasks, deadlines, exams, lectures and study sessions, all in one place. "
    "Tap anything to open it where it was saved.",
    ":material/calendar_clock:",
)

# Every block is drawn on this one throwaway date so the y-axis is purely a
# clock — the real day only decides which column a block stands in.
ANCHOR = date(2000, 1, 1)
TODAY = date.today()
NOW = datetime.now()
VIEWS = ["Month", "Week", "Day", "List"]

st.session_state.setdefault("cal_day", TODAY)
st.session_state.setdefault("cal_view", "Week")
st.session_state.setdefault("cal_nonce", 0)


def _shift(n: int) -> None:
    d = st.session_state.cal_day
    v = st.session_state.cal_view
    if v == "Month" or v == "List":
        y, m = d.year + (d.month - 1 + n) // 12, (d.month - 1 + n) % 12 + 1
        st.session_state.cal_day = date(y, m, min(d.day, cal.monthrange(y, m)[1]))
    elif v == "Week":
        st.session_state.cal_day = d + timedelta(days=7 * n)
    else:
        st.session_state.cal_day = d + timedelta(days=n)


def _today() -> None:
    st.session_state.cal_day = TODAY


def _open(key: str) -> None:
    """A block or a button was tapped: go to where that thing lives."""
    st.session_state.cal_nonce += 1
    agenda.go_key(key)


def _open_day(d: date) -> None:
    st.session_state.cal_day = d
    st.session_state.cal_view = "Day"


# --- the bar -----------------------------------------------------------------

top = st.container(horizontal=True, vertical_alignment="bottom")
with top:
    st.segmented_control("View", VIEWS, key="cal_view", label_visibility="collapsed")
    st.button(":material/chevron_left:", key="cal_prev", on_click=_shift, args=(-1,))
    st.date_input("Day", key="cal_day", width=170, label_visibility="collapsed")
    st.button(":material/chevron_right:", key="cal_next", on_click=_shift, args=(1,))
    st.button("Today", key="cal_today", on_click=_today)

view = st.session_state.cal_view or "Week"
picked: date = st.session_state.cal_day
monday = scoring.week_start(picked)

with st.container(horizontal=True, vertical_alignment="center"):
    kinds = st.pills(
        "Show",
        list(agenda.KINDS),
        format_func=lambda k: agenda.KINDS[k]["label"],
        selection_mode="multi",
        default=list(agenda.KINDS),
        key="cal_kinds",
        label_visibility="collapsed",
    )
kinds = set(kinds or agenda.KINDS)
ui.chips([(v["label"], v["color"]) for k, v in agenda.KINDS.items() if k in kinds])


# --- pieces ------------------------------------------------------------------


def _day_label(d: date) -> str:
    return f"{ui.DAY_NAMES[d.weekday()][:3]} {d.day}"


def _blocks(ev: pd.DataFrame, col_of) -> pd.DataFrame:
    """Timed events as clock blocks. ``col_of`` maps a day to its column."""
    rows = []
    for r in ev.to_dict("records"):
        at = store.as_time(r["time"])
        if at is None:
            continue
        minutes = int(r["minutes"])
        start = datetime.combine(ANCHOR, at)
        end = start + timedelta(minutes=max(minutes, 20))
        day_end = datetime.combine(ANCHOR, time(23, 59))
        if end > day_end:
            # a 23:59 deadline still needs a visible block: slide it back
            end = day_end
            start = max(datetime.combine(ANCHOR, time.min), end - timedelta(minutes=max(minutes, 20)))
        title = r["title"] if len(r["title"]) <= 26 else r["title"][:25] + "…"
        rows.append(
            {
                "key": r["key"],
                "kind": agenda.KINDS[r["kind"]]["label"],
                "title": r["title"],
                "label": f"{title} · {at:%H:%M}" if minutes >= 30 else "",
                "subtitle": r["subtitle"] or "",
                "detail": r["detail"] or "",
                "col": col_of(r["day"]),
                "start": start,
                "end": end,
                "when": f"{start:%H:%M} – {end:%H:%M}",
                "length": ui.hours_text(minutes),
                "color": r["color"],
                "is_done": bool(r["done"]),
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


def _clock_chart(blocks: pd.DataFrame, x_sort: list[str], today_col: str | None, height: int = 600):
    lo = min([7] + [b.hour for b in blocks["start"]])
    hi = max([22] + [b.hour + 2 for b in blocks["end"]])
    domain = [
        datetime.combine(ANCHOR, time(hour=lo)).isoformat(),
        (datetime.combine(ANCHOR, time.min) + timedelta(hours=min(hi, 24))).isoformat(),
    ]
    pick = alt.selection_point(name="pick", fields=["key"], on="click", clear=False)
    base = alt.Chart(blocks)
    bars = (
        base.mark_bar(cornerRadius=5, stroke="white", strokeWidth=1)
        .encode(
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
            color=alt.Color("color:N", scale=None, legend=None),
            opacity=alt.condition(alt.datum.is_done, alt.value(0.4), alt.value(0.92)),
            tooltip=[
                alt.Tooltip("title:N", title="What"),
                alt.Tooltip("kind:N", title="Kind"),
                alt.Tooltip("subtitle:N", title="Where"),
                alt.Tooltip("when:N", title="When"),
                alt.Tooltip("length:N", title="Length"),
                alt.Tooltip("detail:N", title="Status"),
            ],
        )
        .add_params(pick)
    )
    text = base.mark_text(
        align="left", baseline="top", dx=4, dy=3, color="white", limit=150, fontSize=11
    ).encode(
        x=alt.X("col:N", sort=x_sort, scale=alt.Scale(domain=x_sort)),
        xOffset=alt.XOffset("lane:N"),
        y=alt.Y("start:T", scale=alt.Scale(domain=domain)),
        text="label:N",
        opacity=alt.condition(alt.datum.is_done, alt.value(0.7), alt.value(1.0)),
    )
    layers = [bars, text]
    if today_col is not None:
        now_df = pd.DataFrame({"t": [datetime.combine(ANCHOR, NOW.time().replace(second=0, microsecond=0))], "col": [today_col]})
        layers.append(
            alt.Chart(now_df).mark_rule(color="#e11d48", strokeWidth=2).encode(
                y=alt.Y("t:T", scale=alt.Scale(domain=domain))
            )
        )
    return alt.layer(*layers).properties(height=height)


def _show_clock(ev: pd.DataFrame, x_sort: list[str], col_of, tag: str, height: int = 600) -> int:
    """Draw the clock for these events and open whatever gets tapped.
    Returns how many events had no time and so are not on it."""
    blocks = _blocks(ev, col_of)
    if not len(blocks):
        st.caption("Nothing with a time of day here.")
        return int(len(ev))
    blocks = _lanes(blocks)
    if (blocks["lane"] > 0).any():
        st.caption(":material/stacks: Overlapping items sit side by side.")
    today_col = col_of(TODAY) if col_of(TODAY) in x_sort else None
    state = st.altair_chart(
        _clock_chart(blocks, x_sort, today_col, height),
        width="stretch",
        on_select="rerun",
        selection_mode=["pick"],
        key=f"cal_chart_{tag}_{st.session_state.cal_nonce}",
    )
    try:
        sel = (state.get("selection") or {}).get("pick") or []
    except AttributeError:
        sel = []
    if sel:
        key = sel[0].get("key") if isinstance(sel[0], dict) else None
        if key:
            _open(str(key))
    return int(len(ev) - len(blocks))


def _button(ev: dict, key: str, with_day: bool = False, compact: bool = False) -> None:
    """One event as a tappable button that opens it where it was saved."""
    when = ev["time"] or ""
    if with_day:
        when = f"{ev['day']:%a %d} {when}".strip()
    label = f"{when} {ev['title']}".strip()
    if compact and len(label) > 26:
        label = label[:25] + "…"
    meta = agenda.KINDS[ev["kind"]]
    help_text = f"{meta['label']} · {ev['day']:%A %d %B}" + (f" · {ev['time']}" if ev["time"] else "")
    if ev["subtitle"]:
        help_text += f" · {ev['subtitle']}"
    if ev["detail"]:
        help_text += f" · {ev['detail']}"
    help_text += f" — opens {meta['page_title']}"
    if st.button(
        f"~~{label}~~" if ev["done"] else label,
        key=key,
        icon=meta["icon"],
        type="tertiary",
        help=help_text,
    ):
        _open(ev["key"])


def _row(ev: dict, key: str) -> None:
    """One event as a full row: dot, title, meta, open button, and for a
    task its time-of-day editor."""
    meta = agenda.KINDS[ev["kind"]]
    with st.container(horizontal=True, vertical_alignment="center"):
        if ev["kind"] == "task":
            tid = int(ev["id"])
            wkey = f"cal_time_{tid}"

            def _set(tid=tid, wkey=wkey):
                v = st.session_state.get(wkey)
                planning.set_task_time(tid, v.strftime("%H:%M") if v else None)

            st.time_input(
                "Start",
                value=store.as_time(ev["time"]),
                key=wkey,
                step=timedelta(minutes=15),
                on_change=_set,
                label_visibility="collapsed",
                width=110,
            )
        else:
            st.markdown(f"**{ev['time'] or '—'}**", width=70)
        ui.chip(meta["label"], ev["color"])
        done = ":material/check_circle: " if ev["done"] else ""
        st.markdown(
            f"{done}**{ev['title']}**  \n:small[{ev['subtitle']}"
            + (f" · {ui.hours_text(int(ev['minutes']))}" if ev["minutes"] and ev["kind"] != "deadline" else "")
            + (f" · {ev['detail']}" if ev["detail"] else "")
            + "]",
            width="stretch",
        )
        if st.button(
            "Open", key=key, icon=":material/open_in_new:", type="secondary",
            help=f"Opens {meta['page_title']} with this item at the top",
        ):
            _open(ev["key"])


# --- month -------------------------------------------------------------------

if view == "Month":
    weeks = cal.monthcalendar(picked.year, picked.month)
    first = date(picked.year, picked.month, 1)
    grid_start = first - timedelta(days=first.weekday())
    grid_end = grid_start + timedelta(days=7 * len(weeks) - 1)
    ev = agenda.events(grid_start, grid_end, kinds)
    st.markdown(f"### {picked:%B %Y}")
    st.caption(
        f"{len(ev)} items this month. Tap one to open it; tap *more* to see the whole day."
    )
    head = st.columns(7)
    for i, name in enumerate(ui.DAY_NAMES):
        head[i].caption(name[:3])
    for w, week in enumerate(weeks):
        cols = st.columns(7)
        for i, dom in enumerate(week):
            d = grid_start + timedelta(days=7 * w + i)
            with cols[i]:
                with st.container(border=True):
                    if dom == 0:
                        st.caption(f"{d.day}")
                        continue
                    if d == TODAY:
                        st.badge(f"{d.day} · today", color="violet")
                    else:
                        st.markdown(f"**{d.day}**" if d.weekday() < 5 else f"{d.day}")
                    mine = ev[ev["day"] == d] if len(ev) else ev
                    for r in mine.head(4).to_dict("records"):
                        _button(r, f"cal_m_{r['key']}_{d}", compact=True)
                    if len(mine) > 4:
                        st.button(
                            f"+{len(mine) - 4} more",
                            key=f"cal_more_{d}",
                            type="tertiary",
                            on_click=_open_day,
                            args=(d,),
                        )


# --- week --------------------------------------------------------------------

elif view == "Week":
    sunday = monday + timedelta(days=6)
    ev = agenda.events(monday, sunday, kinds)
    st.markdown(f"### {scoring.week_label(monday)}")
    labels = [_day_label(monday + timedelta(days=i)) for i in range(7)]
    if not len(ev):
        st.info("Nothing on this week yet.", icon=":material/event_available:")
    else:
        untimed = _show_clock(ev, labels, _day_label, "week")
        st.caption(
            "Tap a block to open it. "
            + (f"{untimed} item(s) have no time of day and are listed below." if untimed else "")
        )
        cols = st.columns(7)
        for i in range(7):
            d = monday + timedelta(days=i)
            mine = ev[ev["day"] == d] if len(ev) else ev
            with cols[i]:
                if d == TODAY:
                    st.badge(f"{labels[i]} · today", color="violet")
                else:
                    st.markdown(f"**{labels[i]}**")
                if not len(mine):
                    st.caption("—")
                for r in mine.to_dict("records"):
                    _button(r, f"cal_w_{r['key']}_{d}", compact=True)


# --- day ---------------------------------------------------------------------

elif view == "Day":
    ev = agenda.events_on(picked)
    ev = ev[ev["kind"].isin(kinds)] if len(ev) else ev
    st.markdown(f"### {picked:%A %d %B %Y}" + ("  ·  today" if picked == TODAY else ""))
    if not len(ev):
        st.info(
            f"Nothing on {picked:%A %d %B}. Tasks are made on **Today**, **The week** "
            "or **To do**; deadlines on **Opportunities**; exams, lectures and study "
            "sessions on **School**.",
            icon=":material/event_available:",
        )
    else:
        left, right = st.columns([3, 2])
        with left:
            total = int(ev[ev["kind"] != "deadline"]["minutes"].sum())
            st.caption(f"{len(ev)} items · about {ui.hours_text(total)} of timed things. Set a task's time on the left of its row.")
            for r in ev.to_dict("records"):
                _row(r, f"cal_d_{r['key']}")
        with right:
            _show_clock(ev, [_day_label(picked)], _day_label, "day", height=520)

    # tasks this week that have no day yet can be pulled onto this one
    loose = planning.tasks(monday=monday, unscheduled_only=True)
    if len(loose):
        with st.expander(
            f"This week's tasks without a day ({len(loose)})", icon=":material/move_down:"
        ):
            for t in loose.to_dict("records"):
                tid = int(t["id"])
                with st.container(horizontal=True, vertical_alignment="center"):
                    st.markdown(
                        f"**{t['title']}**  \n:small[{t['track']}"
                        + (f" · {t['category']}" if t["category"] else "")
                        + f" · {ui.hours_text(int(t['planned_minutes']))}]",
                        width="stretch",
                    )
                    if st.button(f"Do it {picked:%a %d}", key=f"cal_pull_{tid}", icon=":material/today:"):
                        planning.update_task(tid, day=picked)
                        planning.set_task_time(
                            tid, agenda.next_free_time(picked, int(t["planned_minutes"])).strftime("%H:%M")
                        )
                        st.rerun()


# --- list --------------------------------------------------------------------

else:
    first = date(picked.year, picked.month, 1)
    last = date(picked.year, picked.month, cal.monthrange(picked.year, picked.month)[1])
    ev = agenda.events(first, last, kinds)
    st.markdown(f"### {picked:%B %Y}, as a list")
    if not len(ev):
        st.info("Nothing this month.", icon=":material/event_available:")
    else:
        for d, chunk in ev.groupby("day", sort=True):
            with st.container(border=True):
                with st.container(horizontal=True, vertical_alignment="center"):
                    st.markdown(f"**{d:%A %d %B}**", width="stretch")
                    if d == TODAY:
                        st.badge("today", color="violet")
                    elif d < TODAY:
                        st.badge("past", color="gray")
                    st.badge(f"{len(chunk)}", color="blue")
                for r in chunk.to_dict("records"):
                    _row(r, f"cal_l_{r['key']}")


# --- every plan gets a date and a time ---------------------------------------

pending = agenda.unscheduled_tasks()
with st.expander(
    f"Plans without a date or a time ({len(pending)})",
    icon=":material/more_time:" if len(pending) else ":material/check_circle:",
    expanded=False,
):
    if not len(pending):
        st.success("Every open task has a day and a time of day.", icon=":material/check:")
    else:
        st.caption(
            "Every plan should have a date and a time. These were made before that rule, "
            "or lost theirs. One click gives each a day (its own week, or today if that "
            "week is gone) and the next free slot on that day — then move them around "
            "here or on **To do**."
        )
        view_df = pending[["title", "track", "day", "time", "planned_minutes", "week_start"]].copy()
        view_df["day"] = view_df["day"].map(lambda d: d or "—")
        view_df["time"] = view_df["time"].map(lambda t: t or "—")
        st.dataframe(
            view_df,
            hide_index=True,
            column_config={
                "title": st.column_config.TextColumn("Task", width="large"),
                "track": st.column_config.TextColumn("Track"),
                "day": st.column_config.TextColumn("Day"),
                "time": st.column_config.TextColumn("Time"),
                "planned_minutes": st.column_config.NumberColumn("Minutes"),
                "week_start": st.column_config.TextColumn("Week of"),
            },
            width="stretch",
        )
        if st.button(
            f"Give all {len(pending)} a date and a time",
            type="primary",
            icon=":material/auto_fix_high:",
            key="cal_autoschedule",
        ):
            got = agenda.auto_schedule()
            st.toast(f"{got['days']} got a day, {got['times']} got a time")
            st.rerun()
