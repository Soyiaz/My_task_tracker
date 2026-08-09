"""The dials: how long the summer is, how many hours a week, and how those
hours are meant to be split."""

from datetime import date

import pandas as pd
import streamlit as st

from tracker import db, scoring, structure, ui

ui.page_header(
    "Settings",
    "How long the summer is, how many hours a week, and how those hours are "
    "meant to split.",
    ":material/tune:",
)

start, end, weekly = scoring.plan_window()

with st.container(border=True):
    st.markdown("**The window**")
    with st.form("window", border=False):
        c1, c2, c3 = st.columns(3)
        new_start = c1.date_input("Start", value=start, format="YYYY-MM-DD")
        new_end = c2.date_input("End", value=end, format="YYYY-MM-DD")
        new_weekly = c3.number_input(
            "Hours per week",
            min_value=1.0,
            max_value=100.0,
            value=float(weekly),
            step=1.0,
            help="The total you intend to put in across all five tracks.",
        )
        if st.form_submit_button("Save", type="primary", icon=":material/save:"):
            if new_end <= new_start:
                st.error("The end has to come after the start.")
            else:
                db.set_setting("start_date", new_start.isoformat())
                db.set_setting("end_date", new_end.isoformat())
                db.set_setting("weekly_hours", new_weekly)
                st.toast("Window updated")
                st.rerun()

    weeks = ((new_end - new_start).days + 1) / 7
    st.caption(
        f"{weeks:.1f} weeks · {weeks * new_weekly:.0f} hours planned in total."
    )


with st.container(border=True):
    st.markdown("**The standing split — a fallback, not a rule**")
    st.caption(
        "Since the real split depends on the week, this is only what a week "
        "gets when you have not planned one: it prefills the budget on the "
        "week page, and stands in for any week that went unplanned. It also "
        "sets how much each track weighs in goal completion."
    )
    trk = db.query(
        "SELECT id, key, name, color, goal, target_share FROM tracks ORDER BY sort"
    )
    edited = st.data_editor(
        trk,
        key="shares",
        hide_index=True,
        column_config={
            "id": None,
            "key": None,
            "name": st.column_config.TextColumn("Track", disabled=True),
            "color": st.column_config.TextColumn(
                "Colour",
                width="small",
                help="Hex, e.g. #6366f1. Used for this track in every chart.",
                validate=r"^#[0-9a-fA-F]{6}$",
            ),
            "goal": st.column_config.TextColumn("Goal", width="large"),
            "target_share": st.column_config.NumberColumn(
                "Share of time",
                min_value=0.0,
                max_value=1.0,
                step=0.05,
                format="percent",
            ),
        },
    )
    total = float(edited["target_share"].sum())
    if abs(total - 1.0) > 0.001:
        st.warning(
            f"Shares add up to {total:.0%}. They are used as ratios either way, "
            "but 100% keeps the hour targets honest."
        )
    with st.container(horizontal=True):
        if st.button("Save shares", type="primary", icon=":material/save:"):
            for row in edited.to_dict("records"):
                db.execute(
                    "UPDATE tracks SET target_share = ?, goal = ?, color = ? "
                    "WHERE id = ?",
                    (
                        float(row["target_share"]),
                        row["goal"],
                        row["color"],
                        int(row["id"]),
                    ),
                )
            st.toast("Shares updated")
            st.rerun()
        if st.button("Normalise to 100%", icon=":material/balance:"):
            if total > 0:
                for row in edited.to_dict("records"):
                    db.execute(
                        "UPDATE tracks SET target_share = ? WHERE id = ?",
                        (float(row["target_share"]) / total, int(row["id"])),
                    )
                st.rerun()

    preview = edited.copy()
    preview["hours_per_week"] = preview["target_share"] * new_weekly
    st.dataframe(
        preview[["name", "target_share", "hours_per_week"]],
        hide_index=True,
        column_config={
            "name": st.column_config.TextColumn("Track"),
            "target_share": st.column_config.NumberColumn("Share", format="percent"),
            "hours_per_week": st.column_config.NumberColumn(
                "That is", format="%.1f h/week"
            ),
        },
    )


with st.container(border=True):
    st.markdown("**The domains — the lens everything is measured by**")
    st.caption(
        "Robotics, AI, computer vision and personal growth cut across the "
        "tracks. Target share is what fraction of your hours you want each to "
        "get; the dashboard flags whichever is thinnest."
    )
    doms = db.query(
        "SELECT id, key, name, color, target_share, sort FROM domains ORDER BY sort"
    )
    edited_doms = st.data_editor(
        doms,
        key="domains",
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "id": None,
            "key": st.column_config.TextColumn("Key", width="small",
                                               help="Short slug stored on entries."),
            "name": st.column_config.TextColumn("Domain"),
            "color": st.column_config.TextColumn(
                "Colour", width="small", validate=r"^#[0-9a-fA-F]{6}$"
            ),
            "target_share": st.column_config.NumberColumn(
                "Target share", min_value=0.0, max_value=1.0, step=0.05, format="percent"
            ),
            "sort": st.column_config.NumberColumn("Order", width="small"),
        },
    )
    dom_total = float(edited_doms["target_share"].sum())
    if abs(dom_total - 1.0) > 0.001:
        st.caption(f"Targets add up to {dom_total:.0%}.")
    if st.button("Save domains", type="primary", icon=":material/save:"):
        db.sync_table("domains", doms, edited_doms, {"color": "#6366f1", "sort": 99})
        st.toast("Domains updated")
        st.rerun()
    st.caption(
        "Renaming is safe. Changing a **key** orphans the entries already "
        "tagged with the old one, and deleting a domain leaves its hours "
        "counted as unassigned."
    )


with st.container(border=True):
    st.markdown("**The structure — make it yours**")
    st.caption(
        "The stock tracks and categories are one person's summer, not a rule. "
        "Rename or delete any of them and grow your own — every page, form, "
        "chart and report follows whatever this says."
    )

    st.markdown("**Tracks**")
    trk_edit = structure.tracks_editable()
    edited_trk = st.data_editor(
        trk_edit,
        key="structure_tracks",
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "id": None,
            "key": None,
            "name": st.column_config.TextColumn("Track", required=True),
            "icon": st.column_config.TextColumn(
                "Icon",
                width="medium",
                help="A Material symbol, like `:material/rocket_launch:` — "
                "browse them at fonts.google.com/icons.",
            ),
            "sort": st.column_config.NumberColumn("Order", width="small"),
        },
    )
    removed_tracks = set(trk_edit["id"]) - {
        int(v) for v in edited_trk["id"].dropna()
    }
    allow_delete = False
    if removed_tracks:
        imp = structure.track_impact()
        imp = imp[imp["id"].isin(removed_tracks)]
        st.warning(
            "Deleting "
            + ", ".join(f"**{r['name']}**" for r in imp.to_dict("records"))
            + " takes everything filed under it: "
            + "; ".join(
                f"{r['name']} — {r['tasks']} tasks, {r['hours']:.1f} h logged, "
                f"{r['milestones']} milestones"
                for r in imp.to_dict("records")
            )
            + ". There is no undo.",
            icon=":material/warning:",
        )
        allow_delete = st.checkbox(
            "I understand — delete for good", key="structure_allow_delete"
        )
    if st.button(
        "Save tracks",
        key="structure_tracks_save",
        type="primary",
        icon=":material/save:",
        disabled=bool(removed_tracks) and not allow_delete,
    ):
        structure.save_tracks(edited_trk, allow_delete=allow_delete)
        st.toast("Tracks updated")
        st.rerun()
    st.caption(
        "A new track starts with a 10% share of time — give it its real share "
        "in the standing split above, and its milestones on the Tracks page."
    )

    st.divider()
    st.markdown("**Categories — and what each one asks for**")
    trk_now = scoring.tracks()
    track_names = {r["name"]: int(r["id"]) for r in trk_now.to_dict("records")}
    picked_track = st.selectbox(
        "Track to edit", list(track_names), key="structure_cat_track"
    )
    tid = track_names[picked_track]
    field_help = ", ".join(f"`{k}` ({v})" for k, v in structure.FIELD_LABELS.items())
    domain_help = ", ".join(f"`{k}`" for k in structure.domains()["key"])
    cats_edit = structure.categories_editable(tid)
    edited_cats = st.data_editor(
        cats_edit,
        key=f"structure_cats_{tid}",
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "id": None,
            "key": None,
            "name": st.column_config.TextColumn("Category", required=True),
            "requires": st.column_config.TextColumn(
                "Asks for",
                help="What the entry form demands before it accepts work "
                f"here. Comma-separated from: {field_help}. `file` demands "
                "an upload.",
            ),
            "domains": st.column_config.TextColumn(
                "Usual domains",
                help="Suggested lenses for work filed here, comma-separated "
                f"keys: {domain_help}.",
            ),
            "sort": st.column_config.NumberColumn("Order", width="small"),
        },
    )
    if st.button(
        "Save categories",
        key=f"structure_cats_save_{tid}",
        type="primary",
        icon=":material/save:",
    ):
        structure.save_categories(tid, edited_cats)
        st.toast("Categories updated")
        st.rerun()
    st.caption(
        "Deleting a category keeps the tasks and hours filed under it — they "
        "only lose the label. Unknown field or domain keys are dropped on save."
    )

    if len(cats_edit):
        cat_names = {r["name"]: int(r["id"]) for r in cats_edit.to_dict("records")}
        picked_cat = st.selectbox(
            "Subcategories of", list(cat_names), key=f"structure_sub_cat_{tid}"
        )
        cid = cat_names[picked_cat]
        subs_edit = structure.subcategories_editable(cid)
        edited_subs = st.data_editor(
            subs_edit,
            key=f"structure_subs_{cid}",
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "id": None,
                "key": None,
                "name": st.column_config.TextColumn("Subcategory", required=True),
                "domains": st.column_config.TextColumn(
                    "Usual domains", help=f"Comma-separated keys: {domain_help}."
                ),
                "sort": st.column_config.NumberColumn("Order", width="small"),
            },
        )
        if st.button(
            "Save subcategories",
            key=f"structure_subs_save_{cid}",
            type="primary",
            icon=":material/save:",
        ):
            structure.save_subcategories(cid, edited_subs)
            st.toast("Subcategories updated")
            st.rerun()


with st.container(border=True):
    st.markdown("**How the score is worked out**")
    st.markdown(
        """
- **Goal completion** — every milestone carries a weight (a skill is 1, an
  output 2–3, a project 3). Per track: finished weight over total weight, with
  in-progress counting half. Tracks are then blended by their planned share of
  time, so the score reflects the plan's priorities, not the raw item count.
- **On pace** — half *time*, half *milestones*, each capped at 100%. A track
  that has the hours but finishes nothing scores 50%, and so does one that
  finishes things without the hours behind them.
- **Hours expected so far** — the sum of the budgets you actually set, week by
  week, prorated for a week that is only part over. A week you never planned
  falls back to the standing split above. This is why the split matters less
  than it looks: the week page is where the real allocation happens.
- **Domain coverage** — each entry carries the domains it fed, so an hour can
  count toward more than one. Coverage is that domain's share of all logged
  hours; the gap is against the target share above.
- **Work on this next** — the tracks with the lowest on-pace score, listed
  worst first, with a suggested hour figure of next week's normal allocation
  plus whatever it is behind.
- **The week and the day** — separate from the score. The share above sets the
  *default* budget when you plan a week; once you save that week, its own
  budget is what the week is judged on. Hit rate is tasks finished over tasks
  planned, with dropped tasks excluded so an honest "not today" costs nothing.
"""
    )


with st.container(border=True):
    st.markdown("**Data**")
    log = scoring.time_log()
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "Download time log (CSV)",
            data=log.to_csv(index=False).encode("utf-8"),
            file_name=f"time-log-{date.today():%Y-%m-%d}.csv",
            mime="text/csv",
            icon=":material/download:",
            disabled=not len(log),
        )
    with c2:
        ms = scoring.milestones()
        st.download_button(
            "Download milestones (CSV)",
            data=ms.to_csv(index=False).encode("utf-8"),
            file_name=f"milestones-{date.today():%Y-%m-%d}.csv",
            mime="text/csv",
            icon=":material/download:",
            disabled=not len(ms),
        )
    st.caption(f"Everything lives in `{db.DB_PATH}`. Back that file up.")

    with st.expander("Rebuild from the taxonomy"):
        st.warning(
            "This deletes the whole tree — tracks, categories, domains, "
            "milestones, projects, opportunities, books, weeks, tasks **and "
            "every logged hour** — then plants it again from `taxonomy.py`. "
            "Uploaded files stay on disk but lose their entries. To reshape "
            "the structure *without* losing anything, use the structure "
            "editor above instead."
        )
        confirm = st.text_input("Type RESET to confirm", key="reset_confirm")
        if st.button(
            "Rebuild everything",
            type="primary",
            icon=":material/warning:",
            disabled=confirm != "RESET",
        ):
            db.wipe()
            st.toast("Rebuilt from the taxonomy")
            st.rerun()
