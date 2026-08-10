"""Small shared pieces of the look: colour scales, chips, formatting.

Anything that would otherwise be copy-pasted between pages, and anything that
has to stay consistent for the app to feel like one thing.
"""

from __future__ import annotations

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
        f'background:{color};flex:none"></span>{label}</span>'
    )


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
