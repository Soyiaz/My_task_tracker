"""The journal: a six-question morning conversation, and everything it
has ever said, by date."""

from datetime import date, datetime, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from tracker import cloud, journal, ui

ui.page_header(
    "Journal",
    "Six questions, answered like a chat. The archive keeps every day.",
    ":material/auto_stories:",
)

# --- is there anywhere to write? --------------------------------------------

if not journal.configured():
    st.info(
        "The journal keeps its entries in a **Neon** Postgres database — "
        "separate from the tracker, so nothing here touches your tracker "
        "data. It is not connected yet.",
        icon=":material/cloud_off:",
    )
    st.markdown(
        "1. Create a free project at **neon.tech** (no card needed).\n"
        "2. Copy the **connection string** it shows you "
        "(`postgresql://...@...neon.tech/...`).\n"
        "3. Add it to the app's secrets:"
    )
    st.code('[neon]\nurl = "postgresql://USER:PASSWORD@HOST/DB?sslmode=require"', language="toml")
    st.caption(
        "Deployed: share.streamlit.io → the app → Settings → Secrets. "
        "Locally: `.streamlit/secrets.toml` next to `streamlit_app.py`."
    )
    st.stop()

uid = journal.uid()
if uid is None:
    st.info(
        "The journal is private to an account — sign in to write yours. "
        "The shared demo does not keep a diary.",
        icon=":material/lock:",
    )
    st.stop()

try:
    journal.ensure_schema()
except Exception as e:
    st.error(
        "The journal database did not answer. Check the `[neon]` connection "
        "string in secrets, and that the Neon project is not paused.",
        icon=":material/cloud_off:",
    )
    st.caption(f"`{type(e).__name__}: {e}`")
    st.stop()

TODAY = date.today()

today_tab, archive_tab = st.tabs(
    [":material/edit_note: Today", ":material/calendar_month: The archive"]
)


def show_entry(entry: dict, key_prefix: str, deletable: bool = False) -> None:
    """One journaled day, rendered the same everywhere — editable in place."""
    d = entry["day"]
    d = d if isinstance(d, date) else date.fromisoformat(str(d))
    with st.container(border=True):
        head = st.container(horizontal=True, vertical_alignment="center")
        with head:
            st.markdown(f"**{d:%A %d %B %Y}**", width="stretch")
            ago = (TODAY - d).days
            st.badge(
                "today" if ago == 0 else ("yesterday" if ago == 1 else f"{ago} days ago"),
                icon=":material/event:",
                color="green" if ago == 0 else "gray",
            )
            with st.popover(":material/edit:", help="Edit this entry"):
                edited = {}
                for k, _, label, icon in journal.QUESTIONS:
                    edited[k] = st.text_area(
                        f"{icon} {label}",
                        value=str(entry.get(k, "") or ""),
                        key=f"{key_prefix}_edit_{d}_{k}",
                        height=80,
                    )
                if st.button(
                    "Save changes",
                    key=f"{key_prefix}_editsave_{d}",
                    type="primary",
                    icon=":material/save:",
                ):
                    journal.save_entry(uid, d, edited)
                    st.toast(f"{d:%d %b} updated")
                    st.rerun()
            if deletable:
                with st.popover(":material/delete:", help="Delete this entry"):
                    st.caption("This deletes the whole day. There is no undo.")
                    if st.button(
                        "Delete this entry",
                        key=f"{key_prefix}_del_{d}",
                        icon=":material/delete_forever:",
                    ):
                        journal.delete_entry(uid, d)
                        st.toast(f"{d:%d %b} deleted")
                        st.rerun()
        left, right = st.columns(2)
        for i, (k, _, label, icon) in enumerate(journal.QUESTIONS):
            text = str(entry.get(k, "") or "").strip()
            if not text:
                continue
            with left if i % 2 == 0 else right:
                st.markdown(f"{icon} **{label}**")
                st.markdown(text)


# --- today: the conversation -------------------------------------------------

with today_tab:
    existing = journal.entry_for(uid, TODAY)
    rewriting = st.session_state.get("j_rewrite", False)

    if existing and not rewriting:
        st.caption(
            "Today is already written. Fix a line with the pencil, or rewrite "
            "the whole thing below."
        )
        show_entry(existing, "today", deletable=True)
        if st.button("Rewrite today", icon=":material/edit:", key="j_redo"):
            st.session_state.j_rewrite = True
            st.session_state.j_answers = {}
            st.rerun()
    else:
        answers = st.session_state.setdefault("j_answers", {})

        with st.chat_message("assistant"):
            st.markdown(
                f"Morning — it's **{TODAY:%A, %d %B}**. Six questions, "
                "answer them like messages. Ready when you are."
            )

        asked_next = False
        for k, question, _, _ in journal.QUESTIONS:
            if k in answers:
                with st.chat_message("assistant"):
                    st.markdown(question)
                with st.chat_message("user"):
                    st.markdown(answers[k])
            elif not asked_next:
                with st.chat_message("assistant"):
                    st.markdown(question)
                asked_next = True

        done = len(answers)
        st.progress(done / len(journal.KEYS), text=f"{done} of {len(journal.KEYS)} answered")

        if done < len(journal.KEYS):
            said = st.chat_input("Write it like a message…", key="j_chat")
            if said and said.strip():
                next_key = [k for k in journal.KEYS if k not in answers][0]
                answers[next_key] = said.strip()
                if len(answers) == len(journal.KEYS):
                    journal.save_entry(uid, TODAY, answers)
                    st.session_state.j_answers = {}
                    st.session_state.j_rewrite = False
                    st.toast("Journaled. See you tomorrow.", icon="📖")
                st.rerun()
        if answers and st.button(
            "Start over", icon=":material/restart_alt:", key="j_restart", type="tertiary"
        ):
            st.session_state.j_answers = {}
            st.rerun()


# --- the archive: everything, by date ----------------------------------------

with archive_tab:
    df = journal.entries(uid)
    if not len(df):
        st.info(
            "Nothing here yet — the first entry starts the archive.",
            icon=":material/auto_stories:",
        )
    else:
        df = df.copy()
        df["day"] = [d if isinstance(d, date) else date.fromisoformat(str(d)) for d in df["day"]]
        days = set(df["day"])

        m1, m2, m3 = st.columns(3)
        m1.metric("Entries", len(df))
        m2.metric("Streak", f"{journal.streak(days, TODAY)} days")
        month_count = sum(1 for d in days if d.year == TODAY.year and d.month == TODAY.month)
        m3.metric("This month", month_count)

        # twelve weeks of little squares — journaled days light up
        start = TODAY - timedelta(days=TODAY.weekday()) - timedelta(weeks=11)
        grid = pd.DataFrame(
            {"d": [start + timedelta(days=i) for i in range((TODAY - start).days + 1)]}
        )
        grid["week"] = [f"{d.isocalendar().year}-{d.isocalendar().week:02d}" for d in grid["d"]]
        grid["weekday"] = [ui.DAY_NAMES[d.weekday()][:3] for d in grid["d"]]
        grid["journaled"] = [d in days for d in grid["d"]]
        grid["date"] = [f"{d:%d %b}" for d in grid["d"]]
        heat = (
            alt.Chart(grid)
            .mark_rect(cornerRadius=3, width=16, height=16)
            .encode(
                x=alt.X("week:O", sort=sorted(grid["week"].unique()), axis=None),
                y=alt.Y(
                    "weekday:O",
                    sort=[n[:3] for n in ui.DAY_NAMES],
                    axis=alt.Axis(title=None, labelFontSize=10),
                ),
                color=alt.condition(
                    alt.datum.journaled,
                    alt.value("#22c55e"),
                    alt.value("#88888822"),
                ),
                tooltip=[
                    alt.Tooltip("date:N", title="Day"),
                    alt.Tooltip("journaled:N", title="Journaled"),
                ],
            )
            .properties(height=140)
        )
        st.altair_chart(heat, width="content")

        st.divider()
        recent = df.head(10)
        for row in recent.to_dict("records"):
            show_entry(row, "arch", deletable=True)
        rest = df.iloc[10:]
        if len(rest):
            with st.expander(f"Older entries ({len(rest)})", icon=":material/inventory_2:"):
                for row in rest.to_dict("records"):
                    show_entry(row, "old", deletable=True)
