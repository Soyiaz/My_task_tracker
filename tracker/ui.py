"""Small shared pieces of the look: colour scales, chips, formatting.

Anything that would otherwise be copy-pasted between pages, and anything that
has to stay consistent for the app to feel like one thing.
"""

from __future__ import annotations

import html as _html
from datetime import date

import altair as alt
import streamlit as st

from tracker import scoring, structure

FOCUS = {1: "Scattered", 2: "Patchy", 3: "Okay", 4: "Good", 5: "Deep"}
FOCUS_ICON = {
    1: ":material/cloud:",
    2: ":material/cloudy:",
    3: ":material/partly_cloudy_day:",
    4: ":material/sunny:",
    5: ":material/bolt:",
}

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def color_scale(names: list[str]) -> alt.Scale:
    """An Altair colour scale pinned to the tracks' own colours, so a track is
    the same colour on every chart in the app."""
    colors = scoring.track_colors()
    domain = [n for n in names if n in colors]
    return alt.Scale(domain=domain, range=[colors[n] for n in domain])


def track_color_field(field: str = "track", legend: bool = True) -> alt.Color:
    names = list(scoring.track_colors())
    return alt.Color(
        f"{field}:N",
        scale=color_scale(names),
        title=None,
        legend=alt.Legend(orient="bottom") if legend else None,
    )


def domain_color_field(field: str = "domain", legend: bool = True) -> alt.Color:
    colors = {**structure.domain_colors(), "Unassigned": "#94a3b8"}
    domain = list(colors)
    return alt.Color(
        f"{field}:N",
        scale=alt.Scale(domain=domain, range=[colors[n] for n in domain]),
        title=None,
        legend=alt.Legend(orient="bottom") if legend else None,
    )


def domain_pills(keys: str | list[str] | None) -> None:
    """The lenses an entry fed, as small coloured chips on one line."""
    if isinstance(keys, str):
        keys = structure.split(keys)
    if not keys:
        return
    names = structure.domain_names()
    colors = {r["key"]: r["color"] for r in structure.domains().to_dict("records")}
    spans = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:.3rem;'
        f'margin-right:.5rem;font-size:.75rem;opacity:.85">'
        f'<span style="width:.5rem;height:.5rem;border-radius:50%;'
        f'background:{colors.get(k, "#94a3b8")}"></span>{names.get(k, k)}</span>'
        for k in keys
    )
    st.html(f'<div style="line-height:1.6">{spans}</div>')


def hours_text(minutes: float) -> str:
    """90 -> '1h 30m'. Reads faster than 1.5 h when you are scanning a list."""
    minutes = int(round(minutes))
    if minutes < 60:
        return f"{minutes}m"
    h, m = divmod(minutes, 60)
    return f"{h}h" if m == 0 else f"{h}h {m:02d}m"


def chip(label: str, color: str) -> None:
    """A track's name behind its own colour. There is no native element for a
    coloured dot, and the tracks are much easier to tell apart with one."""
    st.html(
        f'<span style="display:inline-flex;align-items:center;gap:.4rem;'
        f'font-size:.82rem;font-weight:500;opacity:.9">'
        f'<span style="width:.55rem;height:.55rem;border-radius:50%;'
        f'background:{color};flex:none"></span>{_html.escape(str(label))}</span>'
    )


def chips(pairs: list[tuple[str, str]]) -> None:
    """Several coloured dots on one line — a legend without a chart."""
    spans = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:.35rem;'
        f'margin-right:.9rem;font-size:.78rem;opacity:.85">'
        f'<span style="width:.6rem;height:.6rem;border-radius:3px;'
        f'background:{color};flex:none"></span>{_html.escape(str(label))}</span>'
        for label, color in pairs
    )
    st.html(f'<div style="line-height:1.9">{spans}</div>')


def status_badge(status: str) -> None:
    tone = {
        "On track": ("green", ":material/check_circle:"),
        "Slipping": ("orange", ":material/trending_down:"),
        "Behind": ("red", ":material/priority_high:"),
        "Untouched": ("gray", ":material/remove:"),
    }.get(status, ("gray", None))
    st.badge(status, icon=tone[1], color=tone[0])


def attainment_badge(value: float, label: str | None = None) -> None:
    text = label or f"{value:.0%}"
    if value >= 1.0:
        st.badge(text, icon=":material/check:", color="green")
    elif value >= 0.8:
        st.badge(text, icon=":material/trending_up:", color="blue")
    elif value >= 0.5:
        st.badge(text, icon=":material/trending_flat:", color="orange")
    else:
        st.badge(text, icon=":material/trending_down:", color="red")


def require_tracks() -> None:
    """Stop a page early while the tracker is still blank — everything on it
    presumes at least one track. Settings stays reachable to fix that."""
    if len(scoring.tracks()):
        return
    st.info(
        "Your tracker is blank — no tracks yet. A track is a big area of "
        "your plan (a job, a skill, a project); open **Settings** and build "
        "your own under *The structure — make it yours*.",
        icon=":material/foundation:",
    )
    try:
        st.page_link(
            "app_pages/settings.py", label="Go to Settings", icon=":material/tune:"
        )
    except Exception:
        # Outside st.navigation (bare page runs, tests) the link has no
        # route to point at; the sidebar still gets people there.
        pass
    st.stop()


def page_header(title: str, subtitle: str, icon: str) -> None:
    st.title(f"{icon} {title}")
    st.caption(subtitle)


def planned_vs_actual_chart(df, x: str, planned: str, actual: str, height: int = 220):
    """The recurring shape of this app: a pale bar for what was promised, a
    solid one for what happened."""
    base = alt.Chart(df)
    promise = base.mark_bar(
        color="#94a3b8", opacity=0.35, size=22, cornerRadiusEnd=3
    ).encode(
        x=alt.X(f"{x}:N", title=None, sort=list(df[x])),
        y=alt.Y(f"{planned}:Q", title="Hours"),
        tooltip=[x, alt.Tooltip(f"{planned}:Q", title="Planned", format=".1f")],
    )
    got = base.mark_bar(size=11, cornerRadiusEnd=3).encode(
        x=alt.X(f"{x}:N", title=None, sort=list(df[x])),
        y=alt.Y(f"{actual}:Q"),
        color=track_color_field(x) if x == "track" else alt.value("#6366f1"),
        tooltip=[x, alt.Tooltip(f"{actual}:Q", title="Actual", format=".1f")],
    )
    return (promise + got).properties(height=height)


# --- reminders, pinned to the top right --------------------------------------


def _when_text(days_left: int, when: date, at: str | None) -> str:
    if days_left < 0:
        word = f"{-days_left} day{'s' if days_left != -1 else ''} ago"
    elif days_left == 0:
        word = "today"
    elif days_left == 1:
        word = "tomorrow"
    else:
        word = f"in {days_left} days"
    stamp = f"{when:%a %d %b}" + (f" · {at}" if at else "")
    return f"{word} · {stamp}"


def reminder_popup(items: list[dict], title: str = "Coming up", dismiss_key: str = "reminder_popup") -> None:
    """A card fixed to the top-right corner of the screen, listing what is
    due. Pure HTML and CSS: the close button is a checkbox trick, so it
    works without any script and survives reruns the way the rest of the
    page does. Dismissing it for the session is a Streamlit button on the
    page itself, so both ways out exist."""
    if not items:
        return
    rows = []
    for r in items[:6]:
        tone = "#e11d48" if r["days_left"] <= 1 else ("#ea580c" if r["days_left"] <= 7 else "#4f46e5")
        rows.append(
            '<div style="display:flex;gap:.55rem;align-items:flex-start;padding:.45rem 0;'
            'border-top:1px solid rgba(128,128,128,.18)">'
            f'<span style="width:.6rem;height:.6rem;border-radius:50%;background:{r["color"]};'
            'flex:none;margin-top:.35rem"></span>'
            '<div style="min-width:0;flex:1">'
            f'<div style="font-weight:600;font-size:.86rem;line-height:1.25;overflow:hidden;'
            f'text-overflow:ellipsis;white-space:nowrap">{_html.escape(r["title"])}</div>'
            f'<div style="font-size:.74rem;opacity:.75">{_html.escape(r["subtitle"])}'
            + (f' · requirements {r["reqs"]}' if r.get("reqs") else "")
            + "</div>"
            f'<div style="font-size:.76rem;color:{tone};font-weight:600">'
            f'{_html.escape(_when_text(r["days_left"], r["when"], r.get("time")))}</div>'
            "</div></div>"
        )
    more = len(items) - 6
    extra = (
        f'<div style="font-size:.74rem;opacity:.7;padding-top:.4rem">and {more} more below</div>'
        if more > 0
        else ""
    )
    st.html(
        f"""
<style>
#{dismiss_key}-box {{
  position: fixed; top: 3.9rem; right: 1rem; z-index: 999990; width: 21rem; max-width: calc(100vw - 2rem);
  background: var(--secondary-background-color, #f6f7fb); color: inherit;
  border: 1px solid rgba(128,128,128,.25); border-radius: 12px; padding: .7rem .85rem .6rem;
  box-shadow: 0 10px 30px rgba(0,0,0,.18); font-size: .9rem; backdrop-filter: blur(6px);
}}
#{dismiss_key}-toggle {{ display: none; }}
#{dismiss_key}-toggle:checked ~ #{dismiss_key}-box {{ display: none; }}
#{dismiss_key}-box label {{ cursor: pointer; opacity: .6; font-size: 1.1rem; line-height: 1; padding: 0 .2rem; }}
#{dismiss_key}-box label:hover {{ opacity: 1; }}
@media (max-width: 640px) {{ #{dismiss_key}-box {{ top: auto; bottom: 1rem; right: .6rem; }} }}
</style>
<input type="checkbox" id="{dismiss_key}-toggle">
<div id="{dismiss_key}-box">
  <div style="display:flex;align-items:center;justify-content:space-between;gap:.5rem">
    <div style="font-weight:700;font-size:.9rem">⏰ {_html.escape(title)} <span style="opacity:.6;font-weight:500">({len(items)})</span></div>
    <label for="{dismiss_key}-toggle" title="Hide">✕</label>
  </div>
  {''.join(rows)}
  {extra}
</div>
"""
    )


def event_line(ev: dict, show_day: bool = False) -> str:
    """One calendar event as a short markdown line."""
    when = (ev["time"] or "all day")
    if show_day:
        when = f"{ev['day']:%a %d %b} · {when}"
    done = "~~" if ev.get("done") else ""
    return f"{done}**{ev['title']}**{done}  \n:small[{when}" + (
        f" · {ev['subtitle']}" if ev.get("subtitle") else ""
    ) + "]"
