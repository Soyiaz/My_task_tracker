"""Duo: the tracker Lily and Zen share — both of today's lists, the weekly
duel, the week and the month day by day, the savings goal, and what the other
one just did. Lily's own duo tasks can be ticked from here."""

from datetime import date

import streamlit as st

from tracker import duo, ui

ui.page_header(
    "Duo",
    "The shared tracker: both days side by side, the duel, the week, the savings goal.",
    ":material/group:",
)

# --- is it connected? --------------------------------------------------------

if not duo.configured():
    st.info(
        "The Duo page reads the tracker Lily and Zen share — the one with the "
        "Telegram bot, the website and the Android app. It is not connected yet.",
        icon=":material/link_off:",
    )
    st.markdown(
        "Add the duo server's address and **your own** duo password to the secrets "
        "(the same password you use to log in on the duo website or app):"
    )
    st.code(
        '[duo]\nurl = "https://your-duo-server.example"\npassword = "your duo password"\n'
        '# optional, hosted with accounts: only this account mirrors ticks\nemail = "you@example.com"',
        language="toml",
    )
    st.caption(
        "Deployed: share.streamlit.io → the app → Settings → Secrets. "
        "Locally: `.streamlit/secrets.toml`, or the DUO_URL / DUO_PASSWORD environment variables."
    )
    st.stop()

try:
    board = duo.board()
except duo.DuoError as exc:
    st.error(str(exc), icon=":material/cloud_off:")
    if st.button("Try again"):
        duo.refresh()
        st.rerun()
    st.stop()

my_id = duo.me() if duo.active() else None
members = board["members"]
rules = board["rules"]

# Colors match the duo website and app: the first member blue, the second green.
MEMBER_COLORS = ["#3B6FE0", "#2F9E6A"]
STATE_COLORS = {
    "none": "#E7E5E1", "future": "#DCE6F7", "open": "#9DBFEE", "perfect": "#3FB27F",
    "partial": "#A6DDBF", "miss": "#F2A39B", "bad": "#D9483B",
}
GLYPH = {"done": "✓", "missed": "✗", "ignored": "✗", "excused": "–", "pending": "○"}


def _flash(message: str, icon: str = ":material/check:") -> None:
    st.session_state["duo_flash"] = (message, icon)


def _do(task_id: str, day: str, action: str, amount: int = 1) -> None:
    try:
        duo.mark(task_id, day, action, amount)
    except duo.DuoError as exc:
        _flash(str(exc), ":material/error:")


if "duo_flash" in st.session_state:
    message, icon = st.session_state.pop("duo_flash")
    st.toast(message, icon=icon)

top = st.columns([4, 1])
top[0].caption(
    f"{board['today']} · {board['daysLeftInWeek']} days left in the week · "
    f"🔥 {board['sharedStreak']} days done together"
)
if top[1].button("Refresh", icon=":material/refresh:", use_container_width=True):
    duo.refresh()
    st.rerun()

# --- the duel ----------------------------------------------------------------

duel = st.columns(len(members))
for i, m in enumerate(members):
    with duel[i]:
        st.markdown(f"**:{'blue' if i == 0 else 'green'}[{m['name']}]** · level {m['level']}")
        st.progress(
            max(0.0, min(m["weeklyXp"] / rules["startXp"], 1.0)),
            text=f"♥ {m['weeklyXp']} / {rules['startXp']} · {m['excusesLeft']} excuses left",
        )
        for reward in m["pendingRewards"]:
            st.warning(f"Owes a penalty task: {reward}", icon=":material/gavel:")

# --- both days ---------------------------------------------------------------


def _label(o: dict) -> str:
    extra = []
    if o["target"] > 1:
        extra.append(f"{o['progress']}/{o['target']} {o.get('unit') or ''}".strip())
    if o.get("time"):
        extra.append(o["time"])
    if o["date"] != board["today"]:
        extra.append("yesterday")
    return o["taskName"] + (f"  ·  {' · '.join(extra)}" if extra else "")


def _my_row(o: dict) -> None:
    locked = o["status"] in ("missed", "ignored", "excused")
    row = st.columns([6, 1])
    with row[0]:
        if o["target"] > 1 and o["status"] != "done":
            sub = st.columns([5, 1])
            sub[0].markdown(f"{GLYPH['pending']} {_label(o)}")
            sub[1].button(
                "+1", key=f"p_{o['_id']}", disabled=locked,
                on_click=_do, args=(o["taskId"], o["date"], "progress"),
            )
        else:
            st.checkbox(
                _label(o),
                value=o["status"] == "done",
                key=f"c_{o['_id']}_{o['status']}",
                disabled=locked,
                on_change=_do,
                args=(o["taskId"], o["date"], "undo" if o["status"] == "done" else "done"),
            )
    with row[1].popover("", icon=":material/more_horiz:", use_container_width=True):
        st.button(
            f"Not done (−{rules['penalty']['missed']})", key=f"m_{o['_id']}",
            on_click=_do, args=(o["taskId"], o["date"], "missed"), use_container_width=True,
        )
        me = next((m for m in members if m["userId"] == my_id), None)
        st.button(
            f"Excuse ({me['excusesLeft'] if me else 0} left)", key=f"e_{o['_id']}",
            disabled=bool(me and me["excusesLeft"] <= 0),
            on_click=_do, args=(o["taskId"], o["date"], "excused"), use_container_width=True,
        )
        st.button(
            "Undo", key=f"u_{o['_id']}", disabled=o["status"] == "pending" and o["progress"] == 0,
            on_click=_do, args=(o["taskId"], o["date"], "undo"), use_container_width=True,
        )


days = st.columns(len(members))
for i, m in enumerate(members):
    with days[i]:
        with st.container(border=True):
            mine = m["userId"] == my_id
            st.markdown(f"#### :{'blue' if i == 0 else 'green'}[{m['name']}] · {m['done']}/{m['total']}")
            items = (m.get("yesterdayPending", []) + m["items"]) if mine else m["items"]
            if not items:
                st.caption("Nothing scheduled today.")
            for o in items:
                if mine:
                    _my_row(o)
                else:
                    penalty = f" · −{o['penalty']}" if o.get("penalty") else ""
                    st.markdown(f"{GLYPH.get(o['status'], '○')} {_label(o)}{penalty}")
            if mine:
                st.caption("Tick to finish · ⋯ for not done, excuse or undo.")

# --- the week and the month --------------------------------------------------


def _cell(day: dict, size: int, label: str = "", today: bool = False) -> str:
    a, b = (members + [{}, {}])[:2]
    ca = STATE_COLORS[day["members"].get(a.get("userId", ""), {}).get("state", "none")]
    cb = STATE_COLORS[day["members"].get(b.get("userId", ""), {}).get("state", "none")]
    ring = "box-shadow: 0 0 0 2px currentColor;" if today else ""
    return (
        f'<div title="{day["date"]}" style="width:{size}px;height:{size}px;border-radius:{size // 4}px;'
        f"background:linear-gradient(to bottom right,{ca} 50%,{cb} 50%);{ring}"
        f'display:flex;align-items:center;justify-content:center;font-size:{size // 3}px;'
        f'font-weight:600;color:#1C1B1A">{label}</div>'
    )


legend = " ".join(
    f'<span style="display:inline-flex;align-items:center;gap:4px;margin-right:10px">'
    f'<span style="width:10px;height:10px;border-radius:3px;background:{STATE_COLORS[k]}"></span>{v}</span>'
    for k, v in [("perfect", "all done"), ("partial", "some done"), ("open", "open"),
                 ("miss", "1 missed"), ("bad", "2+ missed"), ("future", "planned")]
)

left, right = st.columns([3, 2])
with left:
    with st.container(border=True):
        st.markdown("**This week**")
        letters = "MTWTFSS"
        cells = "".join(
            f'<div style="display:flex;flex-direction:column;align-items:center;gap:2px">'
            f'{_cell(d, 34, today=d["date"] == board["today"])}<span style="font-size:11px;opacity:.6">{letters[i]}</span></div>'
            for i, d in enumerate(board["weekDays"])
        )
        st.markdown(f'<div style="display:flex;gap:8px;margin:4px 0 8px">{cells}</div>', unsafe_allow_html=True)

        today = date.fromisoformat(board["today"])
        try:
            month = duo.month(today.year, today.month)
            lead = date.fromisoformat(month["days"][0]["date"]).weekday()
            grid = '<div style="width:34px;height:34px"></div>' * lead + "".join(
                _cell(d, 34, str(int(d["date"][8:])), d["date"] == month["today"]) for d in month["days"]
            )
            st.markdown(f"**{today:%B}**")
            st.markdown(
                f'<div style="display:grid;grid-template-columns:repeat(7,34px);gap:6px">{grid}</div>',
                unsafe_allow_html=True,
            )
        except duo.DuoError:
            st.caption("The month could not be loaded.")
        names = " · ".join(f"{'◤' if i == 0 else '◢'} {m['name']}" for i, m in enumerate(members))
        st.markdown(f'<div style="font-size:12px;opacity:.7;margin-top:8px">{names}<br>{legend}</div>', unsafe_allow_html=True)

with right:
    for goal in board["goals"]:
        with st.container(border=True):
            st.markdown(f"**💰 {goal['name']}**")
            st.progress(
                goal["percent"] / 100,
                text=f"{goal['current']:,.0f} of {goal['target']:,.0f} {goal['unit']} · {goal['percent']}%",
            )
            if duo.active():
                with st.form(f"goal_{goal['_id']}", clear_on_submit=True, border=False):
                    cols = st.columns([2, 1])
                    amount = cols[0].number_input("Add", min_value=0.0, step=100.0, label_visibility="collapsed")
                    if cols[1].form_submit_button("Add", use_container_width=True) and amount:
                        try:
                            duo.contribute(goal["_id"], amount)
                            _flash(f"Added {amount:,.0f} {goal['unit']}")
                        except duo.DuoError as exc:
                            _flash(str(exc), ":material/error:")
                        st.rerun()

    with st.container(border=True):
        st.markdown("**Coming up**")
        if not board["deadlines"]:
            st.caption("No deadlines in the next two weeks.")
        for d in board["deadlines"][:4]:
            when = "today" if d["daysLeft"] == 0 else f"in {d['daysLeft']} days"
            st.markdown(f"{'🔴' if d['daysLeft'] <= 2 else '📅'} {d['name']} · {when}")

    with st.container(border=True):
        st.markdown("**Latest**")
        if not board["feed"]:
            st.caption("Nothing yet.")
        for f in board["feed"][:6]:
            st.markdown(f"**{f['name']}** {GLYPH.get(f['status'], '')} {f['taskName']}")

# --- this week's penalties ---------------------------------------------------

with st.expander("This week's penalties and the rules"):
    try:
        report = duo.week()
        cols = st.columns(len(report["members"]))
        for i, m in enumerate(report["members"]):
            with cols[i]:
                st.markdown(f"**{m['name']}** · ♥ {m['xp']}")
                if not m["penalties"]:
                    st.caption("No penalties yet.")
                for p in m["penalties"]:
                    why = "ignored" if p["status"] == "ignored" else (
                        f"{p['progress']}/{p['target']}" if p["progress"] else "said no")
                    st.markdown(f"{p['date'][5:]} {p['taskName']} · {why} · **−{p['penalty']}**")
    except duo.DuoError as exc:
        st.caption(str(exc))
    st.caption(
        f"Everyone starts the week at {rules['startXp']} and XP only goes down: "
        f"said no or short of a counter −{rules['penalty']['missed']}, never answered by "
        f"0{rules['closeHour']}:00 the next morning −{rules['penalty']['ignored']}, "
        f"excused 0 ({rules['excusesPerWeek']} a week). Monday, the higher score levels up and "
        "the other owes a penalty task. A task here named exactly like a duo task ticks both."
    )
