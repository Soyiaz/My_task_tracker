"""Opportunities and their deadlines: what to apply for, by when, and what
each one needs from you.

Add one and it lands on the Calendar (the deadline, and the day you plan to
apply); when it is close, the Dashboard pins a reminder in the corner.
"""

from datetime import date, time, timedelta

import pandas as pd
import streamlit as st

from tracker import agenda, opps, ui

TODAY = date.today()

ui.page_header(
    "Opportunities",
    "Scholarships, internships, programmes — each with a deadline, a plan "
    "for when to apply, and the list of what it asks for.",
    ":material/work:",
)

df = opps.frame()
jump = agenda.take_jump("deadline", "apply")


# --- adding one --------------------------------------------------------------


def _req_lines(text: str) -> list[str]:
    return [ln.strip(" -•*\t") for ln in text.splitlines() if ln.strip(" -•*\t")]


with st.expander(
    "Add an opportunity", icon=":material/add_circle:", expanded=not len(df)
):
    c1, c2 = st.columns([3, 2])
    with c1:
        name = st.text_input("Name *", key="opp_name", placeholder="e.g. DAAD Master's scholarship")
        organisation = st.text_input("Organisation", key="opp_org", placeholder="Who runs it")
        link = st.text_input("Link", key="opp_link", placeholder="https://…")
    with c2:
        category = st.selectbox("Category", opps.CATEGORIES, key="opp_cat")
        status = st.selectbox("Status", opps.STATUS, key="opp_status")

    st.markdown("**The dates**")
    d1, d2, d3 = st.columns(3)
    with d1:
        deadline = st.date_input("Application deadline *", value=TODAY + timedelta(days=30), key="opp_deadline")
        deadline_time = st.time_input("Closes at", value=time(23, 59), key="opp_deadline_time", step=timedelta(minutes=15))
    with d2:
        has_open = st.checkbox("Applications open on a date", key="opp_has_open")
        apply_from = (
            st.date_input("Opens", value=TODAY, key="opp_apply_from") if has_open else None
        )
    with d3:
        plan_apply = st.checkbox("Plan the day I apply", value=True, key="opp_plan_apply")
        apply_on = None
        apply_time = None
        if plan_apply:
            default_apply = max(TODAY, (deadline - timedelta(days=3)) if isinstance(deadline, date) else TODAY)
            apply_on = st.date_input("I will apply on", value=default_apply, key="opp_apply_on")
            apply_time = st.time_input("at", value=time(10, 0), key="opp_apply_time", step=timedelta(minutes=15))

    reqs_text = st.text_area(
        "Requirements — one per line",
        key="opp_reqs",
        height=120,
        placeholder="Transcript\nTwo recommendation letters\nMotivation letter (max 1 page)\nCV\nEnglish test score",
    )
    notes = st.text_area("Notes", key="opp_notes", height=70, placeholder="Eligibility, amounts, who to ask…")

    if st.button("Save opportunity", type="primary", icon=":material/save:", key="opp_add"):
        if not name.strip():
            st.warning("Give it a name.")
        elif not isinstance(deadline, date):
            st.warning("It needs a deadline.")
        else:
            rid = opps.add(
                name,
                category,
                deadline,
                deadline_time,
                apply_from,
                apply_on,
                apply_time,
                _req_lines(reqs_text),
                link,
                organisation,
                notes,
                status,
            )
            st.toast(f"Saved · deadline {deadline:%a %d %b}")
            for k in ("opp_name", "opp_org", "opp_link", "opp_reqs", "opp_notes"):
                st.session_state.pop(k, None)
            st.rerun()


if not len(df):
    st.info(
        "Nothing here yet. Add the first one above — it goes straight onto the "
        "Calendar, and the Dashboard will remind you as the deadline nears.",
        icon=":material/event_upcoming:",
    )
    st.stop()


# --- the state of play -------------------------------------------------------

open_df = df[df["is_open"]]
with st.container(horizontal=True):
    st.metric("Open", len(open_df), border=True, help="Watching or preparing.")
    st.metric(
        "Closing this week",
        int(((open_df["days_left"] >= 0) & (open_df["days_left"] <= 7)).sum()) if len(open_df) else 0,
        border=True,
    )
    st.metric("Applied", int(df["status"].isin(["Applied", "Interview"]).sum()), border=True)
    st.metric("Accepted", int((df["status"] == "Accepted").sum()), border=True)
    overdue = int(((open_df["days_left"] < 0)).sum()) if len(open_df) else 0
    st.metric("Past deadline, still open", overdue, border=True)


# --- one card ----------------------------------------------------------------


def card(o: dict, highlight: bool = False) -> None:
    color, word = opps.urgency(o["days_left"] if pd.notna(o["days_left"]) else None)
    with st.container(border=True):
        if highlight:
            st.caption(":material/arrow_back: From the calendar — this is the one you tapped.")
        head = st.container(horizontal=True, vertical_alignment="center")
        with head:
            st.markdown(f"**{o['name']}**", width="stretch")
            st.badge(o["category"], color="violet")
            st.badge(o["status"], color=opps.STATUS_COLOR.get(o["status"], "gray"))
            if o["is_open"] or o["days_left"] is None or pd.isna(o["days_left"]):
                st.badge(word, icon=":material/alarm:", color=color)
        line = []
        if o["organisation"]:
            line.append(o["organisation"])
        if o["deadline"]:
            line.append(
                f"deadline **{o['deadline']:%a %d %b %Y}**"
                + (f" at {o['deadline_time']}" if o["deadline_time"] else "")
            )
        if o["apply_from"]:
            line.append(f"opens {o['apply_from']:%d %b}")
        if o["apply_on"]:
            line.append(f"applying on **{o['apply_on']:%a %d %b}**")
        if o["link"]:
            line.append(f"[link]({o['link']})")
        if line:
            st.markdown(" · ".join(line))

        reqs = o["requirements"]
        if reqs:
            done = sum(1 for q in reqs if q["done"])
            st.progress(done / len(reqs), text=f"Requirements · {done} of {len(reqs)} ready")
            cols = st.columns(2)
            for i, q in enumerate(reqs):
                with cols[i % 2]:
                    ticked = st.checkbox(
                        q["text"],
                        value=q["done"],
                        key=f"opp_req_{o['id']}_{i}_{int(q['done'])}",
                    )
                    if ticked != q["done"]:
                        opps.set_requirement(int(o["id"]), i, ticked)
                        st.rerun()
        if o["notes"]:
            st.caption(o["notes"])

        with st.container(horizontal=True):
            if o["is_open"] and st.button(
                "Mark applied",
                icon=":material/send:",
                key=f"opp_applied_{o['id']}",
                type="primary",
            ):
                opps.update(int(o["id"]), status="Applied", applied_on=TODAY)
                st.toast("Applied — well done")
                st.rerun()
            with st.popover("Edit", icon=":material/edit:", key=f"opp_editpop_{o['id']}"):
                edit_form(o)
            if st.button(
                "Delete", icon=":material/delete:", key=f"opp_del_{o['id']}", type="tertiary"
            ):
                opps.delete(int(o["id"]))
                st.toast("Deleted")
                st.rerun()


def edit_form(o: dict) -> None:
    rid = int(o["id"])
    name = st.text_input("Name", value=o["name"], key=f"oe_name_{rid}")
    organisation = st.text_input("Organisation", value=o["organisation"], key=f"oe_org_{rid}")
    link = st.text_input("Link", value=o["link"], key=f"oe_link_{rid}")
    category = st.selectbox(
        "Category", opps.CATEGORIES,
        index=opps.CATEGORIES.index(o["category"]) if o["category"] in opps.CATEGORIES else len(opps.CATEGORIES) - 1,
        key=f"oe_cat_{rid}",
    )
    status = st.selectbox(
        "Status", opps.STATUS, index=opps.STATUS.index(o["status"]), key=f"oe_status_{rid}"
    )
    deadline = st.date_input("Deadline", value=o["deadline"] or TODAY, key=f"oe_deadline_{rid}")
    deadline_time = st.time_input(
        "Closes at",
        value=time.fromisoformat(o["deadline_time"]) if o["deadline_time"] else time(23, 59),
        key=f"oe_dtime_{rid}", step=timedelta(minutes=15),
    )
    has_open = st.checkbox("Applications open on a date", value=o["apply_from"] is not None, key=f"oe_hasopen_{rid}")
    apply_from = st.date_input("Opens", value=o["apply_from"] or TODAY, key=f"oe_from_{rid}") if has_open else None
    plan_apply = st.checkbox("Plan the day I apply", value=o["apply_on"] is not None, key=f"oe_plan_{rid}")
    apply_on = apply_time = None
    if plan_apply:
        apply_on = st.date_input("I will apply on", value=o["apply_on"] or TODAY, key=f"oe_on_{rid}")
        apply_time = st.time_input(
            "at", value=time.fromisoformat(o["apply_time"]) if o["apply_time"] else time(10, 0),
            key=f"oe_ontime_{rid}", step=timedelta(minutes=15),
        )
    reqs_text = st.text_area(
        "Requirements — one per line",
        value="\n".join(q["text"] for q in o["requirements"]),
        key=f"oe_reqs_{rid}", height=110,
    )
    notes = st.text_area("Notes", value=o["notes"], key=f"oe_notes_{rid}", height=70)
    if st.button("Save changes", type="primary", icon=":material/save:", key=f"oe_save_{rid}"):
        old = {q["text"]: q["done"] for q in o["requirements"]}
        reqs = [{"text": t, "done": old.get(t, False)} for t in _req_lines(reqs_text)]
        opps.update(
            rid,
            name=name.strip() or o["name"],
            organisation=organisation,
            link=link,
            category=category,
            status=status,
            deadline=deadline if isinstance(deadline, date) else None,
            deadline_time=deadline_time,
            apply_from=apply_from if isinstance(apply_from, date) else None,
            apply_on=apply_on if isinstance(apply_on, date) else None,
            apply_time=apply_time,
            requirements=reqs,
            notes=notes,
        )
        st.toast("Updated")
        st.rerun()


# --- the list ----------------------------------------------------------------

if jump is not None:
    hit = df[df["id"] == int(jump["id"])]
    if len(hit):
        card(hit.iloc[0].to_dict(), highlight=True)
        st.divider()

with st.container(border=True):
    with st.container(horizontal=True):
        cat_filter = st.pills("Category", opps.CATEGORIES, selection_mode="multi", key="opp_f_cat")
        status_filter = st.pills(
            "Status", opps.STATUS, selection_mode="multi",
            default=["Watching", "Preparing"], key="opp_f_status",
        )
    search = st.text_input("Search", key="opp_f_search", placeholder="Filter by name…", label_visibility="collapsed")

view = df.copy()
if cat_filter:
    view = view[view["category"].isin(cat_filter)]
if status_filter:
    view = view[view["status"].isin(status_filter)]
if search.strip():
    view = view[view["name"].str.lower().str.contains(search.strip().lower(), regex=False)]
if jump is not None:
    view = view[view["id"] != int(jump["id"])]

st.caption(f"{len(view)} of {len(df)} opportunities · soonest deadline first")

if not len(view):
    st.caption("Nothing matches those filters.")
else:
    soon = view[view["is_open"] & (view["days_left"] <= 14)] if len(view) else view
    rest = view.drop(soon.index)
    if len(soon):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown("### Closing within two weeks")
            st.badge(f"{len(soon)}", color="red")
        for o in soon.to_dict("records"):
            card(o)
    if len(rest):
        if len(soon):
            st.markdown("### Everything else")
        for o in rest.to_dict("records"):
            card(o)
