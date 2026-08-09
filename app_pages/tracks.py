"""The plan itself: every skill, tool, project and output, editable in place."""

import pandas as pd
import streamlit as st

from tracker import db, scoring, structure, ui

ui.page_header(
    "Tracks & milestones",
    "The plan itself. Statuses feed goal completion; weights decide how much "
    "each one counts.",
    ":material/checklist:",
)

STATUS_UI = {"todo": "Not started", "doing": "In progress", "done": "Done"}
UI_STATUS = {v: k for k, v in STATUS_UI.items()}

trk = scoring.tracks()
rep = scoring.track_report().set_index("key")


def status_column(label: str = "Status"):
    return st.column_config.SelectboxColumn(
        label, options=list(UI_STATUS), required=True, width="small"
    )


def editor(table: str, df: pd.DataFrame, key: str, config: dict, defaults: dict):
    """A table you can edit, add rows to and delete rows from, with one Save."""
    shown = df.copy()
    if "status" in shown.columns:
        shown["status"] = shown["status"].map(STATUS_UI).fillna("Not started")
    edited = st.data_editor(
        shown,
        key=key,
        hide_index=True,
        num_rows="dynamic",
        column_config={**config, "id": None},
    )
    if st.button("Save", key=f"{key}_save", icon=":material/save:", type="primary"):
        out = edited.copy()
        if "status" in out.columns:
            out["status"] = out["status"].map(lambda v: UI_STATUS.get(v, "todo"))
        db.sync_table(
            table, df, out, defaults, stamp_done=table in ("items", "projects")
        )
        st.toast("Saved")
        st.rerun()


tabs = st.tabs([r["name"] for r in trk.to_dict("records")])

for tab, t in zip(tabs, trk.to_dict("records")):
    with tab:
        stats = rep.loc[t["key"]]
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"### {t['name']}")
            ui.status_badge(stats["status"])
        st.caption(t["goal"])
        with st.container(horizontal=True):
            st.metric(
                "Milestones",
                f"{stats['progress']:.0%}",
                delta=f"{stats['progress'] - stats['expected_progress']:+.0%} vs pace",
                border=True,
            )
            st.metric(
                "Hours",
                f"{stats['hours']:.1f} h",
                delta=f"{stats['hour_gap']:+.1f} h vs plan",
                border=True,
            )
            st.metric("Health", f"{stats['health']:.0%}", border=True)
            st.metric(
                "Share of time",
                f"{stats['actual_share']:.0%}",
                delta=f"{stats['actual_share'] - stats['target_share']:+.0%} vs planned",
                border=True,
            )

        cats = structure.categories(int(t["id"]))
        if len(cats):
            with st.container(border=True):
                st.markdown("**How work in this track is filed**")
                st.caption(
                    "Every logged hour and every task picks a category, and a "
                    "subcategory where there is one. Categories marked *needs* "
                    "will not accept an entry until those fields are filled."
                )
                for c in cats.to_dict("records"):
                    subs = structure.subcategories(int(c["id"]))
                    with st.container(horizontal=True, vertical_alignment="center"):
                        st.markdown(f"**{c['name']}**")
                        for req in structure.split(c["requires"]):
                            st.badge(
                                structure.FIELD_LABELS.get(req, req),
                                icon=":material/priority_high:",
                                color="orange",
                            )
                        for dom in structure.split(c["domains"]):
                            st.badge(
                                structure.domain_names().get(dom, dom),
                                color="violet",
                            )
                    if len(subs):
                        st.caption(" · ".join(subs["name"]))

        items = db.query(
            "SELECT id, section, name, kind, weight, status, notes FROM items "
            "WHERE track_id = ? ORDER BY sort, id",
            (int(t["id"]),),
        )
        # A track added in the structure editor has no sections yet; it still
        # deserves an editor to grow its first milestones in.
        sections = list(items["section"].unique()) if len(items) else ["Milestones"]
        for section in sections:
            st.markdown(f"**{section}**")
            editor(
                "items",
                items[items["section"] == section].reset_index(drop=True),
                key=f"items_{t['key']}_{section}",
                config={
                    "section": st.column_config.TextColumn("Section", width="small"),
                    "name": st.column_config.TextColumn("Milestone", width="medium"),
                    "kind": st.column_config.SelectboxColumn(
                        "Kind",
                        options=["skill", "tool", "output", "habit"],
                        width="small",
                    ),
                    "weight": st.column_config.NumberColumn(
                        "Weight", min_value=0.5, max_value=5.0, step=0.5
                    ),
                    "status": status_column(),
                    "notes": st.column_config.TextColumn("Notes", width="large"),
                },
                # New rows land at the end of their section.
                defaults={"track_id": int(t["id"]), "section": section, "sort": 999},
            )

        st.markdown("**Projects**")
        st.caption("The things that end up in the portfolio. Worth more than a skill tick.")
        projects = db.query(
            "SELECT id, name, category, difficulty, weight, status, link, notes "
            "FROM projects WHERE track_id = ? ORDER BY id",
            (int(t["id"]),),
        )
        editor(
            "projects",
            projects,
            key=f"projects_{t['key']}",
            config={
                "name": st.column_config.TextColumn("Project", width="medium"),
                "category": st.column_config.TextColumn("Type", width="small"),
                "difficulty": st.column_config.SelectboxColumn(
                    "Difficulty",
                    options=["Beginner", "Intermediate", "Advanced"],
                    width="small",
                ),
                "weight": st.column_config.NumberColumn(
                    "Weight", min_value=1.0, max_value=8.0, step=1.0
                ),
                "status": status_column(),
                "link": st.column_config.LinkColumn("Documentation"),
                "notes": st.column_config.TextColumn("Notes", width="medium"),
            },
            defaults={"track_id": int(t["id"])},
        )

        if t["key"] == "personal":
            st.markdown("**Reading**")
            books = db.query(
                "SELECT id, month, title, status, reflection FROM books ORDER BY id"
            )
            editor(
                "books",
                books,
                key="books",
                config={
                    "month": st.column_config.TextColumn("Month", width="small"),
                    "title": st.column_config.TextColumn("Book", width="medium"),
                    "status": status_column(),
                    "reflection": st.column_config.TextColumn(
                        "Reflection", width="large"
                    ),
                },
                defaults={"month": "", "title": ""},
            )

        if t["key"] == "income":
            st.markdown("**Opportunity tracker**")
            st.caption("Applications, clients, gigs. Not scored — this is the funnel.")
            opps = db.query(
                "SELECT id, name, kind, mode, day, status, result, income, notes "
                "FROM opportunities ORDER BY COALESCE(day, '9999') DESC, id DESC"
            )
            edited = st.data_editor(
                opps,
                key="opps",
                hide_index=True,
                num_rows="dynamic",
                column_config={
                    "id": None,
                    "name": st.column_config.TextColumn("Job title", width="medium"),
                    "kind": st.column_config.SelectboxColumn(
                        "Type",
                        options=[
                            "Freelance",
                            "Tutoring",
                            "Technical service",
                            "Internship",
                            "Job",
                            "Research",
                            "Collaboration",
                        ],
                    ),
                    "mode": st.column_config.SelectboxColumn(
                        "Mode", options=["In person", "Remote"], width="small"
                    ),
                    "day": st.column_config.TextColumn("Date", width="small"),
                    "status": st.column_config.SelectboxColumn(
                        "Status",
                        options=["idea", "applied", "in talks", "won", "lost"],
                        required=True,
                    ),
                    "result": st.column_config.TextColumn("Result", width="medium"),
                    "income": st.column_config.NumberColumn("Income", format="%.0f"),
                    "notes": st.column_config.TextColumn("Notes", width="medium"),
                },
            )
            if st.button("Save", key="opps_save", icon=":material/save:", type="primary"):
                db.sync_table(
                    "opportunities", opps, edited, {"status": "idea", "mode": "Remote"}
                )
                st.toast("Saved")
                st.rerun()

            won = opps[opps["status"] == "won"] if len(opps) else opps
            if len(won):
                st.metric(
                    "Income booked", f"{won['income'].sum():,.0f}", border=True
                )
