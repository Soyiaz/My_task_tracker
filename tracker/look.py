"""The look: one stylesheet for the whole app, a hero header, the logo.

Streamlit's own theme (``.streamlit/config.toml``) sets the colours and
fonts; this module layers the parts a theme file cannot express — a soft
gradient page, frosted-glass cards, a gradient on the active menu item and
the primary button, rounded progress bars, a page header with an icon tile.

Everything is keyed on the active mode (light or dark) so the toggle in the
app menu keeps working. The only script is a few lines that tag bordered
containers and metrics with ``data-card`` — Streamlit gives them no stable
hook of their own — so the stylesheet can dress them without touching the
plain containers used for layout.
"""

from __future__ import annotations

import html as _html

import streamlit as st

# fmt: off
PALETTES = {
    "light": dict(
        bg="#f6f7fb", glow1="rgba(99, 102, 241, .18)", glow2="rgba(20, 184, 166, .14)",
        card="rgba(255, 255, 255, .72)", card_nested="rgba(255, 255, 255, .55)",
        card_border="rgba(99, 102, 241, .16)", card_border_hover="rgba(99, 102, 241, .32)",
        shadow="0 8px 28px rgba(31, 38, 135, .07)", shadow_hover="0 14px 36px rgba(31, 38, 135, .11)",
        side1="rgba(244, 245, 251, .96)", side2="rgba(236, 238, 248, .96)",
        text="#15161c", muted="#5f6578", track="rgba(99, 102, 241, .12)",
        primary="#4f46e5", primary2="#7c3aed", accent="#14b8a6",
        primary_shadow="rgba(79, 70, 229, .28)", scroll="rgba(99, 102, 241, .28)",
        hero_tile="linear-gradient(135deg, #4f46e5, #7c3aed 60%, #14b8a6)",
    ),
    "dark": dict(
        bg="#0b0d14", glow1="rgba(129, 140, 248, .20)", glow2="rgba(45, 212, 191, .12)",
        card="rgba(24, 27, 38, .66)", card_nested="rgba(30, 34, 48, .55)",
        card_border="rgba(148, 163, 255, .14)", card_border_hover="rgba(148, 163, 255, .30)",
        shadow="0 10px 32px rgba(0, 0, 0, .35)", shadow_hover="0 16px 40px rgba(0, 0, 0, .45)",
        side1="rgba(11, 13, 19, .98)", side2="rgba(16, 18, 28, .98)",
        text="#e8eaf2", muted="#9aa3b8", track="rgba(129, 140, 248, .16)",
        primary="#818cf8", primary2="#a78bfa", accent="#2dd4bf",
        primary_shadow="rgba(129, 140, 248, .30)", scroll="rgba(148, 163, 255, .26)",
        hero_tile="linear-gradient(135deg, #6366f1, #8b5cf6 60%, #14b8a6)",
    ),
}
# fmt: on


def mode() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:
        return "light"


def palette() -> dict:
    return PALETTES[mode()]


_CSS = """
<style>
/* ---- the page ---------------------------------------------------------- */
.stApp {{
  background:
    radial-gradient(1100px 540px at -6% -12%, {glow1}, transparent 60%),
    radial-gradient(900px 480px at 106% -6%, {glow2}, transparent 55%),
    {bg} !important;
  background-attachment: fixed;
}}
[data-testid="stHeader"] {{ background: transparent !important; }}
[data-testid="stAppDeployButton"] {{ display: none; }}
[data-testid="stMainBlockContainer"] {{ padding-top: 2.6rem; padding-bottom: 5rem; }}
h1, h2, h3 {{ letter-spacing: -.02em; }}
::-webkit-scrollbar {{ width: 10px; height: 10px; }}
::-webkit-scrollbar-thumb {{ background: {scroll}; border-radius: 10px; border: 3px solid transparent; background-clip: content-box; }}
::-webkit-scrollbar-track {{ background: transparent; }}

/* ---- glass cards: bordered containers and metrics ---------------------- */
[data-testid="stVerticalBlock"][data-card],
[data-testid="stMetric"][data-card] {{
  background: {card} !important;
  border: 1px solid {card_border} !important;
  border-radius: 18px !important;
  box-shadow: {shadow};
  -webkit-backdrop-filter: blur(14px) saturate(140%);
  backdrop-filter: blur(14px) saturate(140%);
  transition: box-shadow .2s ease, border-color .2s ease, transform .2s ease;
}}
[data-testid="stVerticalBlock"][data-card] {{ padding: 1.05rem 1.15rem !important; }}
[data-testid="stVerticalBlock"][data-card]:hover,
[data-testid="stMetric"][data-card]:hover {{ box-shadow: {shadow_hover}; border-color: {card_border_hover} !important; }}
[data-card] [data-card] {{ background: {card_nested} !important; box-shadow: none; -webkit-backdrop-filter: none; backdrop-filter: none; }}
[data-card] [data-card]:hover {{ transform: none; }}
[data-testid="stMetric"][data-card] {{ padding: .9rem 1.05rem !important; }}
[data-testid="stMetricLabel"] p {{
  text-transform: uppercase; letter-spacing: .08em; font-size: .72rem !important;
  font-weight: 600; color: {muted};
}}
[data-testid="stMetricValue"] {{ font-weight: 700; letter-spacing: -.025em; font-variant-numeric: tabular-nums; }}

/* ---- sidebar ----------------------------------------------------------- */
[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, {side1}, {side2}) !important;
  border-right: 1px solid {card_border};
}}
[data-testid="stSidebarNavLink"] {{ border-radius: 10px; transition: background .15s ease, transform .15s ease; }}
[data-testid="stSidebarNavLink"]:hover {{ transform: translateX(2px); }}
[data-testid="stSidebarNavLink"][aria-current="page"] {{
  background: linear-gradient(90deg, {primary}, {primary2}) !important;
  box-shadow: 0 6px 16px {primary_shadow};
}}
[data-testid="stSidebarNavLink"][aria-current="page"] p,
[data-testid="stSidebarNavLink"][aria-current="page"] [data-testid="stIconMaterial"] {{ color: #fff !important; }}
[data-testid="stNavSectionHeader"] {{
  text-transform: uppercase; letter-spacing: .1em; font-size: .68rem !important;
  font-weight: 700; color: {muted} !important;
}}
[data-testid="stSidebar"] [data-testid="stProgressBarTrack"] {{ height: .4rem !important; }}

/* ---- buttons, inputs, progress, expanders ------------------------------ */
[data-testid="stBaseButton-primary"] {{
  background: linear-gradient(135deg, {primary}, {primary2}) !important;
  border: none !important; box-shadow: 0 6px 16px {primary_shadow};
  transition: transform .15s ease, box-shadow .15s ease;
}}
[data-testid="stBaseButton-primary"]:hover {{ transform: translateY(-1px); box-shadow: 0 10px 22px {primary_shadow}; }}
[data-testid="stBaseButton-secondary"] {{
  background: {card} !important; transition: transform .15s ease, border-color .15s ease;
}}
[data-testid="stBaseButton-secondary"]:hover {{ transform: translateY(-1px); border-color: {primary} !important; }}
[data-testid="stProgressBarTrack"] {{
  height: .55rem !important; border-radius: 999px !important; background: {track} !important; overflow: hidden;
}}
[data-testid="stProgressBarTrack"] > div {{
  background: linear-gradient(90deg, {primary}, {accent}) !important; border-radius: 999px !important;
}}
[data-testid="stExpander"] details {{
  border-radius: 14px !important; background: {card};
  -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px);
}}
[data-testid="stTextInputRootElement"], .react-aria-ComboBox > div[role="group"],
[data-testid="stNumberInputContainer"], [data-testid="stTextArea"] textarea {{ border-radius: 12px !important; }}
[data-testid="stTabs"] [role="tablist"] {{ gap: .35rem; }}
[data-testid="stTabs"] [role="tab"] {{ border-radius: 10px 10px 0 0; padding: .35rem .7rem; }}
[data-testid="stMainBlockContainer"] > div {{ animation: tk-fade .35s ease; }}
@keyframes tk-fade {{ from {{ opacity: 0; transform: translateY(5px); }} to {{ opacity: 1; transform: none; }} }}

/* ---- the hero header ---------------------------------------------------- */
.tk-hero {{ display: flex; align-items: center; gap: 1rem; margin: 0 0 1.2rem; }}
.tk-hero-tile {{
  width: 3.4rem; height: 3.4rem; flex: none; border-radius: 16px; display: grid; place-items: center;
  background: {hero_tile}; color: #fff; box-shadow: 0 10px 24px {primary_shadow};
}}
.tk-hero-tile span {{ font-family: 'Material Symbols Rounded'; font-size: 1.9rem; line-height: 1; }}
.tk-hero h1 {{ margin: 0 !important; padding: 0 !important; font-size: 2rem; line-height: 1.15; font-weight: 750; color: {text}; }}
.tk-hero-sub {{ margin-top: .2rem; font-size: .92rem; color: {muted}; }}
@media (max-width: 640px) {{
  .tk-hero h1 {{ font-size: 1.55rem; }}
  .tk-hero-tile {{ width: 2.8rem; height: 2.8rem; }}
  [data-testid="stVerticalBlock"][data-card] {{ padding: .85rem .9rem !important; }}
}}
</style>
"""

_JS = """
<script>
(function () {
  // Tag bordered containers and metrics so the stylesheet can find them.
  const mark = () => {
    document.querySelectorAll(
      '[data-testid="stVerticalBlock"]:not([data-card]), [data-testid="stMetric"]:not([data-card])'
    ).forEach((el) => {
      const cs = getComputedStyle(el);
      if (cs.borderTopWidth !== '0px' && cs.borderTopStyle !== 'none') el.setAttribute('data-card', '1');
    });
  };
  if (!window.__tkCards) {
    window.__tkCards = new MutationObserver(() => {
      clearTimeout(window.__tkCardsT);
      window.__tkCardsT = setTimeout(mark, 40);
    });
    window.__tkCards.observe(document.body, { childList: true, subtree: true });
  }
  mark();
})();
</script>
"""


def inject() -> None:
    """Call once per run, from the entry script, before any page draws."""
    st.html(_CSS.format(**palette()))
    st.html(_JS, unsafe_allow_javascript=True)


def hero(title: str, subtitle: str, icon: str) -> None:
    """The page header: an icon tile, the title, a line under it.
    ``icon`` is a Streamlit icon string such as ``:material/speed:``."""
    name = icon.strip(":").removeprefix("material/")
    st.html(
        f'<div class="tk-hero"><div class="tk-hero-tile"><span>{_html.escape(name)}</span></div>'
        f"<div><h1>{_html.escape(title)}</h1>"
        f'<div class="tk-hero-sub">{_html.escape(subtitle)}</div></div></div>'
    )


def logo() -> None:
    try:
        st.logo("static/logo.svg", size="large")
    except Exception:
        pass
