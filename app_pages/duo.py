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
if top[1].button("Refresh", icon=":material/refresh:", width="stretch"):
    duo.refresh()
    st.rerun()

# --- the duel ----------------------------------------------------------------
# One card for the week's duel: each side in their own colour, the XP that is
# left as a bar, who is ahead in the middle. Pure HTML so the two halves can
# share one frame; the colours come from the same palette as the rest.

import html as _html  # noqa: E402

from tracker import look  # noqa: E402

_pal = look.palette()


def _side(i: int, m: dict) -> str:
    c = MEMBER_COLORS[i % 2]
    pct = max(0, min(100, round(100 * m["weeklyXp"] / rules["startXp"])))
    owed = "".join(
        f'<div class="duo-owe">⚖ owes a penalty task: {_html.escape(r)}</div>' for r in m["pendingRewards"]
    )
    return (
        f'<div class="duo-side" style="--c:{c}">'
        f'<div class="duo-name">{_html.escape(m["name"])}<span>level {m["level"]}</span></div>'
        f'<div class="duo-xp">{m["weeklyXp"]}<span>/ {rules["startXp"]} XP</span></div>'
        f'<div class="duo-bar"><div style="width:{pct}%"></div></div>'
        f'<div class="duo-meta">{m["done"]}/{m["total"]} done today · {m["excusesLeft"]} excuses left</div>'
        f"{owed}</div>"
    )


if len(members) >= 2:
    a, b = members[0], members[1]
    gap = a["weeklyXp"] - b["weeklyXp"]
    verdict = (
        "Dead even" if gap == 0 else f"{(a if gap > 0 else b)['name']} leads by {abs(gap)}"
    )
    st.html(
        f"""
<style>
.duo-duel {{ display:grid; grid-template-columns: 1fr auto 1fr; gap: 1rem; align-items: center;
  padding: 1.1rem 1.2rem; border-radius: 20px; background: {_pal['card']}; border: 1px solid {_pal['card_border']};
  box-shadow: {_pal['shadow']}; -webkit-backdrop-filter: blur(14px) saturate(140%); backdrop-filter: blur(14px) saturate(140%); margin-bottom: 1rem; }}
.duo-side {{ min-width: 0; }}
.duo-name {{ font-weight: 700; font-size: 1.05rem; color: var(--c); display:flex; align-items: baseline; gap: .5rem; }}
.duo-name span {{ font-size: .74rem; font-weight: 600; color: {_pal['muted']}; text-transform: uppercase; letter-spacing: .06em; }}
.duo-xp {{ font-size: 2.1rem; font-weight: 800; letter-spacing: -.03em; line-height: 1.1; margin: .15rem 0 .35rem; color: {_pal['text']}; font-variant-numeric: tabular-nums; }}
.duo-xp span {{ font-size: .85rem; font-weight: 600; color: {_pal['muted']}; margin-left: .35rem; letter-spacing: 0; }}
.duo-bar {{ height: .6rem; border-radius: 999px; background: {_pal['track']}; overflow: hidden; }}
.duo-bar > div {{ height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--c), color-mix(in srgb, var(--c) 55%, white)); transition: width .6s ease; }}
.duo-meta {{ font-size: .8rem; color: {_pal['muted']}; margin-top: .4rem; }}
.duo-owe {{ font-size: .8rem; color: #e11d48; font-weight: 600; margin-top: .3rem; }}
.duo-vs {{ text-align: center; min-width: 6.5rem; }}
.duo-vs b {{ display: inline-grid; place-items: center; width: 2.6rem; height: 2.6rem; border-radius: 50%;
  background: linear-gradient(135deg, {_pal['primary']}, {_pal['primary2']}); color: #fff; font-size: .8rem; letter-spacing: .08em;
  box-shadow: 0 8px 18px {_pal['primary_shadow']}; }}
.duo-vs div {{ font-size: .78rem; color: {_pal['muted']}; margin-top: .45rem; }}
.duo-side:last-child {{ text-align: right; }}
.duo-side:last-child .duo-name {{ justify-content: flex-end; }}
.duo-side:last-child .duo-bar > div {{ margin-left: auto; }}
@media (max-width: 760px) {{ .duo-duel {{ grid-template-columns: 1fr; }} .duo-vs {{ order: -1; }}
  .duo-side:last-child {{ text-align: left; }} .duo-side:last-child .duo-name {{ justify-content: flex-start; }} .duo-side:last-child .duo-bar > div {{ margin-left: 0; }} }}
</style>
<div class="duo-duel">{_side(0, a)}<div class="duo-vs"><b>VS</b><div>{_html.escape(verdict)}<br>{board['daysLeftInWeek']} days left</div></div>{_side(1, b)}</div>
"""
    )
else:
    for i, m in enumerate(members):
        st.progress(
            max(0.0, min(m["weeklyXp"] / rules["startXp"], 1.0)),
            text=f"{m['name']} · ♥ {m['weeklyXp']} / {rules['startXp']} · {m['excusesLeft']} excuses left",
        )

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
    with row[1].popover("", icon=":material/more_horiz:", width="stretch"):
        st.button(
            f"Not done (−{rules['penalty']['missed']})", key=f"m_{o['_id']}",
            on_click=_do, args=(o["taskId"], o["date"], "missed"), width="stretch",
        )
        me = next((m for m in members if m["userId"] == my_id), None)
        st.button(
            f"Excuse ({me['excusesLeft'] if me else 0} left)", key=f"e_{o['_id']}",
            disabled=bool(me and me["excusesLeft"] <= 0),
            on_click=_do, args=(o["taskId"], o["date"], "excused"), width="stretch",
        )
        st.button(
            "Undo", key=f"u_{o['_id']}", disabled=o["status"] == "pending" and o["progress"] == 0,
            on_click=_do, args=(o["taskId"], o["date"], "undo"), width="stretch",
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
                    if cols[1].form_submit_button("Add", width="stretch") and amount:
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
