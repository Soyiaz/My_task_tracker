"""School: the courses, how far the lectures have got against how far you
have, the exams, and the study plan that gets you there in time.

Everything dated here (lectures, exams, study sessions) is drawn on the
Calendar, and exams within a month are pinned on the Dashboard.
"""

from datetime import date, time, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from tracker import agenda, notes, school, scoring, ui

TODAY = date.today()
MONDAY = scoring.week_start(TODAY)

ui.page_header(
    "School",
    "Courses and units, what the lecture has covered against what you have "
    "studied, the exams, and a dated study plan for each one.",
    ":material/school:",
)

courses = school.courses()
by_id = {c["id"]: c for c in courses}
names = school.course_names()
jump = agenda.take_jump("exam", "study", "lecture")


# --- shared pieces -----------------------------------------------------------


def course_chip(cid: int) -> None:
    c = by_id.get(cid) or school.course(cid)
    if c:
        ui.chip(c["name"] + (f" · {c['code']}" if c["code"] else ""), c["color"])


def lecture_text(c: dict) -> str:
    if not c["lectures"]:
        return "no lecture slots yet"
    return ", ".join(
        f"{school.DAY_NAMES[s['day']][:3]} {s['start']}–{s['end']}"
        + (f" ({s['room']})" if s["room"] else "")
        for s in c["lectures"]
    )


def slots_editor(key: str, current: list[dict]) -> list[dict]:
    """The weekly lecture timetable of one course, as an editable table."""
    df = pd.DataFrame(
        [
            {
                "day": school.DAY_NAMES[s["day"]],
                "start": time.fromisoformat(s["start"]),
                "end": time.fromisoformat(s["end"]),
                "room": s["room"],
            }
            for s in current
        ]
        or [{"day": "Monday", "start": time(9, 0), "end": time(10, 30), "room": ""}]
    )
    edited = st.data_editor(
        df,
        key=key,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "day": st.column_config.SelectboxColumn("Day", options=school.DAY_NAMES, required=True),
            "start": st.column_config.TimeColumn("Starts", format="HH:mm", step=900),
            "end": st.column_config.TimeColumn("Ends", format="HH:mm", step=900),
            "room": st.column_config.TextColumn("Room"),
        },
        width="stretch",
    )
    out = []
    for r in edited.to_dict("records"):
        if not r.get("day") or r.get("start") is None or pd.isna(r.get("start")):
            continue
        s = r["start"] if isinstance(r["start"], time) else time(9, 0)
        e = r["end"] if isinstance(r["end"], time) and not pd.isna(r["end"]) else time(s.hour + 1 if s.hour < 23 else 23, s.minute)
        out.append(
            {
                "day": school.DAY_NAMES.index(r["day"]),
                "start": s.strftime("%H:%M"),
                "end": e.strftime("%H:%M"),
                "room": str(r.get("room") or ""),
            }
        )
    return out


def course_form(key: str, c: dict | None = None) -> dict | None:
    """Add or edit a course. Returns the field dict when saved."""
    c = c or {}
    k = lambda n: f"{key}_{n}"  # noqa: E731
    c1, c2, c3 = st.columns([3, 1, 1])
    name = c1.text_input("Course name *", value=c.get("name", ""), key=k("name"), placeholder="e.g. Linear Algebra")
    code = c2.text_input("Code", value=c.get("code", ""), key=k("code"), placeholder="MATH 201")
    units = c3.number_input("Units", min_value=0.0, max_value=12.0, value=float(c.get("units", 3)), step=0.5, key=k("units"))
    c4, c5, c6 = st.columns([2, 2, 1])
    instructor = c4.text_input("Instructor", value=c.get("instructor", ""), key=k("instr"))
    chapters = c5.number_input(
        "Chapters / topics in the syllabus", min_value=1, max_value=200,
        value=int(c.get("chapters", 12) or 12), step=1, key=k("chapters"),
        help="The unit everything is measured in: the lecture covers N of them, you study N of them.",
    )
    color = c6.color_picker("Colour", value=c.get("color", school.COLORS[len(courses) % len(school.COLORS)]), key=k("color"))
    c7, c8 = st.columns(2)
    term_start = c7.date_input("Term starts", value=c.get("term_start") or TODAY, key=k("ts"))
    term_end = c8.date_input("Term ends", value=c.get("term_end") or (TODAY + timedelta(weeks=15)), key=k("te"))
    st.caption("Lecture timetable — one row per weekly slot. These are drawn on the Calendar.")
    lectures = slots_editor(k("slots"), c.get("lectures", []))
    notes_text = st.text_area("Notes", value=c.get("notes", ""), key=k("notes"), height=60, placeholder="Grading, office hours, links…")
    if st.button("Save course", type="primary", icon=":material/save:", key=k("save")):
        if not name.strip():
            st.warning("Give the course a name.")
            return None
        return {
            "name": name, "code": code, "units": units, "chapters": int(chapters),
            "instructor": instructor, "color": color,
            "term_start": term_start if isinstance(term_start, date) else None,
            "term_end": term_end if isinstance(term_end, date) else None,
            "lectures": lectures, "notes": notes_text,
        }
    return None


def exam_card(e: dict, highlight: bool = False, key_prefix: str = "ex") -> None:
    c = by_id.get(e["course_id"]) or school.course(e["course_id"]) or {"name": "?", "color": "#64748b"}
    left = (e["day"] - TODAY).days if e["day"] else None
    summary = school.plan_summary(e["id"])
    with st.container(border=True):
        if highlight:
            st.caption(":material/arrow_back: From the calendar — this is the one you tapped.")
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"**{e['kind']} · {e['title']}**", width="stretch")
            ui.chip(c["name"], c["color"])
            if e["status"] == "Done":
                st.badge("done" + (f" · {e['score']}" if e.get("score") not in (None, "") else ""), icon=":material/check:", color="green")
            elif left is None:
                st.badge("no date", color="gray")
            elif left < 0:
                st.badge(f"{-left} d ago", color="gray")
            elif left == 0:
                st.badge("today", icon=":material/alarm:", color="red")
            else:
                st.badge(f"in {left} d", icon=":material/alarm:", color="red" if left <= 3 else ("orange" if left <= 10 else "blue"))
        bits = []
        if e["day"]:
            bits.append(f"**{e['day']:%A %d %B}**" + (f" at {e['time']}" if e["time"] else ""))
        if e["minutes"]:
            bits.append(ui.hours_text(e["minutes"]))
        if e["location"]:
            bits.append(e["location"])
        if e["weight"]:
            bits.append(f"{e['weight']:.0f}% of the grade")
        if bits:
            st.markdown(" · ".join(bits))
        if e["topics"]:
            st.caption(f"Topics: {e['topics']}")
        if e["start_study"] and e["status"] != "Done":
            start_left = (e["start_study"] - TODAY).days
            if summary["sessions"]:
                st.progress(
                    summary["done"] / summary["sessions"],
                    text=f"Study plan · {summary['done']} of {summary['sessions']} sessions done · "
                    f"{ui.hours_text(summary['minutes_done'])} of {ui.hours_text(summary['minutes'])}",
                )
            elif start_left > 0:
                st.caption(f"Start studying on **{e['start_study']:%a %d %b}** ({start_left} days from now) — no sessions planned yet.")
            elif start_left <= 0:
                st.warning(
                    f"The plan said start studying on {e['start_study']:%a %d %b} and there are no sessions yet.",
                    icon=":material/running_with_errors:",
                )
        with st.container(horizontal=True):
            if e["status"] != "Done":
                with st.popover("Plan the study", icon=":material/event_repeat:", key=f"{key_prefix}_plan_{e['id']}"):
                    plan_form(e)
                if st.button("Mark done", icon=":material/check:", key=f"{key_prefix}_done_{e['id']}", type="tertiary"):
                    school.update_exam(e["id"], status="Done")
                    st.rerun()
            else:
                if st.button("Reopen", icon=":material/undo:", key=f"{key_prefix}_reopen_{e['id']}", type="tertiary"):
                    school.update_exam(e["id"], status="Upcoming")
                    st.rerun()
            with st.popover("Edit", icon=":material/edit:", key=f"{key_prefix}_edit_{e['id']}"):
                exam_form(f"{key_prefix}_ef_{e['id']}", e)
            if st.button("Delete", icon=":material/delete:", key=f"{key_prefix}_del_{e['id']}", type="tertiary", help="Also deletes its study sessions."):
                school.delete_exam(e["id"])
                st.toast("Exam deleted")
                st.rerun()
        ss = school.sessions(exam_id=e["id"])
        if ss:
            with st.expander(f"Study sessions ({summary['done']}/{len(ss)})", icon=":material/menu_book:"):
                session_rows(ss, f"{key_prefix}_s_{e['id']}")


def session_rows(ss: list[dict], key_prefix: str) -> None:
    for s in ss:
        with st.container(horizontal=True, vertical_alignment="center"):
            done = st.checkbox(
                f"{s['day']:%a %d %b} · {s['time']} · {ui.hours_text(s['minutes'])}"
                + (f" — {s['topic']}" if s["topic"] else ""),
                value=s["done"],
                key=f"{key_prefix}_{s['id']}_{int(s['done'])}",
                width="stretch",
            )
            if done != s["done"]:
                school.toggle_session(s["id"], done)
                st.rerun()
            if s["day"] and s["day"] < TODAY and not s["done"]:
                st.badge("missed", color="red")
            with st.popover(":material/edit:", key=f"{key_prefix}_e_{s['id']}", help="Move or resize"):
                nd = st.date_input("Day", value=s["day"] or TODAY, key=f"{key_prefix}_ed_{s['id']}")
                nt = st.time_input("Time", value=time.fromisoformat(s["time"]), key=f"{key_prefix}_et_{s['id']}", step=timedelta(minutes=15))
                nm = st.number_input("Minutes", min_value=15, max_value=480, value=int(s["minutes"]), step=15, key=f"{key_prefix}_em_{s['id']}")
                ntopic = st.text_input("Topic", value=s["topic"], key=f"{key_prefix}_etp_{s['id']}")
                if st.button("Save", key=f"{key_prefix}_es_{s['id']}", type="primary"):
                    school.update_session(s["id"], day=nd, time=nt, minutes=int(nm), topic=ntopic)
                    st.rerun()
            if st.button(":material/delete:", key=f"{key_prefix}_d_{s['id']}", type="tertiary", help="Remove this session"):
                school.delete_session(s["id"])
                st.rerun()


def plan_form(e: dict) -> None:
    k = f"plan_{e['id']}"
    existing = school.sessions(exam_id=e["id"])
    st.caption(
        f"Lay study sessions on the calendar from a start day up to the day before the "
        f"{e['kind'].lower()}" + (f" on {e['day']:%d %b}" if e["day"] else "") + "."
    )
    start = st.date_input(
        "Start studying on",
        value=e["start_study"] or school.suggested_start(e["kind"], e["day"]) or TODAY,
        key=f"{k}_start",
        help=f"The usual lead time for a {e['kind'].lower()} is {school.LEAD_DAYS.get(e['kind'], 7)} days.",
    )
    days = st.pills(
        "Which days",
        list(range(7)),
        format_func=lambda i: school.DAY_NAMES[i][:3],
        selection_mode="multi",
        default=[0, 1, 2, 3, 4, 5, 6],
        key=f"{k}_days",
    )
    c1, c2 = st.columns(2)
    at = c1.time_input("Session starts at", value=time(18, 0), key=f"{k}_time", step=timedelta(minutes=15))
    minutes = c2.number_input("Minutes per session", min_value=15, max_value=480, value=60, step=15, key=f"{k}_min")
    topics = st.text_area(
        "Topics, one per line (optional)",
        key=f"{k}_topics",
        height=90,
        placeholder="Dealt out across the sessions in order.",
        value=e["topics"].replace(", ", "\n") if e["topics"] else "",
    )
    end = (e["day"] - timedelta(days=1)) if e["day"] else None
    preview = school.plan_days(start, end, set(days or range(7))) if (end and isinstance(start, date) and start <= end) else []
    if end is None:
        st.warning("Give the exam a date first.")
    elif not preview:
        st.warning("No days in that span — the start is after the exam, or no weekdays are ticked.")
    else:
        st.caption(
            f"{len(preview)} sessions × {ui.hours_text(int(minutes))} = "
            f"**{ui.hours_text(len(preview) * int(minutes))}** of study, "
            f"{preview[0]:%d %b} → {preview[-1]:%d %b}."
        )
    replace = True
    if existing:
        replace = st.checkbox(f"Replace the {len(existing)} sessions already planned", value=True, key=f"{k}_replace")
    if st.button("Create the plan", type="primary", icon=":material/event_repeat:", key=f"{k}_go", disabled=not preview):
        n = school.build_plan(e["id"], start, set(days or range(7)), at, int(minutes), topics.splitlines(), replace=replace)
        st.toast(f"{n} study sessions on the calendar")
        st.rerun()


def exam_form(key: str, e: dict | None = None) -> None:
    e = e or {}
    k = lambda n: f"{key}_{n}"  # noqa: E731
    if not courses:
        st.caption("Add a course first.")
        return
    opts = [c["id"] for c in courses]
    cur = e.get("course_id", opts[0])
    course_id = st.selectbox(
        "Course", opts, index=opts.index(cur) if cur in opts else 0,
        format_func=lambda i: names.get(i, "?"), key=k("course"),
    )
    c1, c2 = st.columns([1, 2])
    kind = c1.selectbox("Kind", school.EXAM_KINDS, index=school.EXAM_KINDS.index(e.get("kind", "Test")), key=k("kind"))
    title = c2.text_input("Title", value=e.get("title", ""), key=k("title"), placeholder="e.g. Midterm 1 — chapters 1–5")
    d1, d2, d3 = st.columns(3)
    day = d1.date_input("Date", value=e.get("day") or (TODAY + timedelta(days=14)), key=k("day"))
    at = d2.time_input("Time", value=time.fromisoformat(e["time"]) if e.get("time") else time(9, 0), key=k("time"), step=timedelta(minutes=15))
    minutes = d3.number_input("Minutes", min_value=15, max_value=480, value=int(e.get("minutes", 90) or 90), step=15, key=k("min"))
    l1, l2 = st.columns(2)
    location = l1.text_input("Location", value=e.get("location", ""), key=k("loc"))
    weight = l2.number_input("Weight (% of grade)", min_value=0.0, max_value=100.0, value=float(e.get("weight", 0) or 0), step=5.0, key=k("weight"))
    topics = st.text_input("Topics covered", value=e.get("topics", ""), key=k("topics"), placeholder="chapters 1–5, …")
    suggested = school.suggested_start(kind, day if isinstance(day, date) else None)
    start_study = st.date_input(
        "Start studying on",
        value=e.get("start_study") or suggested or TODAY,
        key=k("start"),
        help=f"Suggested for a {kind.lower()}: {school.LEAD_DAYS.get(kind, 7)} days before.",
    )
    notes_text = st.text_input("Notes", value=e.get("notes", ""), key=k("notes"))
    score = None
    if e.get("status") == "Done":
        score = st.text_input("Score", value=str(e.get("score") or ""), key=k("score"))
    if st.button("Save", type="primary", icon=":material/save:", key=k("save")):
        if e:
            fields = dict(
                course_id=int(course_id), kind=kind, title=title.strip() or kind,
                day=day if isinstance(day, date) else None, time=at, minutes=int(minutes),
                location=location, weight=float(weight), topics=topics,
                start_study=start_study if isinstance(start_study, date) else None, notes=notes_text,
            )
            if score is not None:
                fields["score"] = score
            school.update_exam(e["id"], **fields)
            st.toast("Exam updated")
        else:
            school.add_exam(
                int(course_id), kind, title, day if isinstance(day, date) else None, at,
                int(minutes), location, float(weight), topics,
                start_study if isinstance(start_study, date) else None, notes_text,
            )
            st.toast(f"{kind} added · {day:%a %d %b}" if isinstance(day, date) else f"{kind} added")
        st.rerun()


# --- from the calendar -------------------------------------------------------

if jump is not None:
    if jump["kind"] == "exam":
        e = school.exam(int(jump["id"]))
        if e:
            exam_card(e, highlight=True, key_prefix="jx")
            st.divider()
    elif jump["kind"] == "study":
        s = school.session(int(jump["id"]))
        if s:
            with st.container(border=True):
                st.caption(":material/arrow_back: From the calendar — this study session.")
                with st.container(horizontal=True, vertical_alignment="center"):
                    st.markdown(f"**Study · {names.get(s['course_id'], '?')}**", width="stretch")
                    course_chip(s["course_id"])
                st.markdown(
                    f"{s['day']:%A %d %B} · {s['time']} · {ui.hours_text(s['minutes'])}"
                    + (f" — {s['topic']}" if s["topic"] else "")
                )
                session_rows([s], "js")
            if s["exam_id"]:
                e = school.exam(s["exam_id"])
                if e:
                    st.caption("It belongs to this exam's plan:")
                    exam_card(e, key_prefix="jsx")
            st.divider()
    elif jump["kind"] == "lecture":
        cid = str(jump["id"]).split("-")[0]
        c = school.course(int(cid)) if cid.isdigit() else None
        if c:
            with st.container(border=True):
                st.caption(":material/arrow_back: From the calendar — this lecture's course.")
                with st.container(horizontal=True, vertical_alignment="center"):
                    st.markdown(f"**{c['name']}**", width="stretch")
                    ui.chip(c["code"] or "course", c["color"])
                st.markdown(lecture_text(c))
                p = school.progress(c["id"])
                st.progress(min(p["lecture_pct"], 1.0), text=f"Lecture at {p['lecture']:g} of {p['total']} chapters · you at {p['studied']:g}")
            st.divider()


# --- the numbers ---------------------------------------------------------------

week_hours = school.this_week_hours(MONDAY)
upcoming = school.upcoming_exams(60)
backlog = sum(school.progress(c["id"])["backlog"] for c in courses)
suggested_hours = school.total_units() * 2

with st.container(horizontal=True):
    st.metric("Courses", len(courses), border=True, help="Archived ones are not counted.")
    st.metric("Units", f"{school.total_units():g}", border=True)
    st.metric(
        "Studied this week",
        f"{week_hours:g} h",
        delta=f"{week_hours - suggested_hours:+.1f} h vs {suggested_hours:g} h suggested" if suggested_hours else None,
        border=True,
        help="Suggested is two hours per unit per week — the usual rule of thumb.",
    )
    st.metric(
        "Chapters behind the lecture",
        f"{backlog:g}",
        border=True,
        help="Across all courses: chapters the lecture has covered that you have not studied yet.",
    )
    if upcoming:
        nxt = upcoming[0]
        st.metric(
            "Next exam",
            f"{nxt['days_left']} d" if nxt["days_left"] >= 0 else "today",
            delta=f"{nxt['kind']} · {nxt['course']}",
            delta_color="off",
            border=True,
        )
    else:
        st.metric("Next exam", "—", border=True)

courses_tab, week_tab, exams_tab, progress_tab = st.tabs(
    [
        ":material/library_books: Courses",
        ":material/edit_calendar: This week",
        ":material/quiz: Exams & study plan",
        ":material/monitoring: Progress",
    ]
)


# --- courses -----------------------------------------------------------------

with courses_tab:
    with st.expander("Add a course", icon=":material/add_circle:", expanded=not courses):
        got = course_form("newcourse")
        if got:
            school.add_course(**got)
            st.toast(f"{got['name']} added")
            st.rerun()

    if not courses:
        st.info("No courses yet. Add the first one above.", icon=":material/library_books:")
    for c in courses:
        p = school.progress(c["id"])
        with st.container(border=True):
            with st.container(horizontal=True, vertical_alignment="center"):
                st.markdown(f"**{c['name']}**" + (f"  ·  {c['code']}" if c["code"] else ""), width="stretch")
                ui.chip(f"{c['units']:g} units", c["color"])
                if c["instructor"]:
                    st.badge(c["instructor"], icon=":material/person:", color="gray")
                if p["backlog"] > 0:
                    st.badge(f"{p['backlog']:g} ch behind", icon=":material/trending_down:", color="orange")
                else:
                    st.badge("caught up", icon=":material/check:", color="green")
            st.caption(f"Lectures: {lecture_text(c)}")
            c1, c2 = st.columns(2)
            with c1:
                st.progress(min(p["lecture_pct"], 1.0), text=f"Lecture has covered {p['lecture']:g} of {p['total']} chapters")
            with c2:
                st.progress(min(p["studied_pct"], 1.0), text=f"You have studied {p['studied']:g} of {p['total']} · {p['hours']:g} h")
            if c["notes"]:
                st.caption(c["notes"])
            nbs = notes.notebooks(c["id"])
            with st.container(horizontal=True):
                if st.button(
                    f"Notes ({len(nbs)})" if nbs else "Open notes",
                    icon=":material/draw:",
                    key=f"course_notes_{c['id']}",
                    type="tertiary",
                ):
                    st.session_state["notes_course"] = c["id"]
                    if nbs:
                        st.session_state["notes_current"] = nbs[0]["id"]
                    # the Notes pickers keep their own state; clear it so they open here
                    for k in [k for k in st.session_state if str(k).startswith("notes_pick_") or k == "notes_course_pick"]:
                        st.session_state.pop(k, None)
                    st.switch_page("app_pages/notes.py")
                with st.popover("Edit", icon=":material/edit:", key=f"course_edit_{c['id']}"):
                    got = course_form(f"editcourse_{c['id']}", c)
                    if got:
                        school.update_course(c["id"], **got)
                        st.toast("Course updated")
                        st.rerun()
                if st.button("Archive", icon=":material/inventory_2:", key=f"course_arch_{c['id']}", type="tertiary", help="Hides it; keeps everything."):
                    school.update_course(c["id"], archived=True)
                    st.rerun()
                with st.popover("Delete", icon=":material/delete:", key=f"course_del_{c['id']}"):
                    st.caption("Takes its weekly log, exams and study sessions with it. Notebooks stay.")
                    if st.button("Delete for good", key=f"course_del_go_{c['id']}", icon=":material/delete_forever:"):
                        school.delete_course(c["id"])
                        st.toast("Course deleted")
                        st.rerun()

    archived = [c for c in school.courses(include_archived=True) if c["archived"]]
    if archived:
        with st.expander(f"Archived ({len(archived)})"):
            for c in archived:
                with st.container(horizontal=True, vertical_alignment="center"):
                    st.markdown(f"{c['name']}", width="stretch")
                    if st.button("Restore", key=f"course_restore_{c['id']}", type="tertiary"):
                        school.update_course(c["id"], archived=False)
                        st.rerun()


# --- this week ---------------------------------------------------------------

with week_tab:
    if not courses:
        st.caption("Add a course first.")
    else:
        picked = st.date_input("Week of", value=TODAY, key="school_week_pick", width=170)
        monday = scoring.week_start(picked if isinstance(picked, date) else TODAY)
        st.caption(
            f"**{monday:%d %b} – {monday + timedelta(days=6):%d %b}** · for each course: how many "
            "chapters the lecture got through, how many you studied, and for how long."
        )
        total_h = 0.0
        for c in courses:
            w = school.week_entry(c["id"], monday) or {}
            p = school.progress(c["id"])
            with st.container(border=True):
                with st.container(horizontal=True, vertical_alignment="center"):
                    st.markdown(f"**{c['name']}**", width="stretch")
                    ui.chip(f"lecture at {p['lecture']:g} · you at {p['studied']:g} of {p['total']}", c["color"])
                k = f"wk_{c['id']}_{monday}"
                with st.container(horizontal=True, vertical_alignment="bottom"):
                    lec = st.number_input(
                        "Lecture covered (chapters)", min_value=0.0, max_value=50.0, step=0.5,
                        value=float(w.get("lecture_chapters", 0)), key=f"{k}_lec", width=190,
                    )
                    stu = st.number_input(
                        "You studied (chapters)", min_value=0.0, max_value=50.0, step=0.5,
                        value=float(w.get("study_chapters", 0)), key=f"{k}_stu", width=190,
                    )
                    hrs = st.number_input(
                        "Hours studied", min_value=0.0, max_value=80.0, step=0.5,
                        value=float(w.get("study_hours", 0)), key=f"{k}_hrs", width=150,
                    )
                    note = st.text_input("Notes", value=w.get("notes", ""), key=f"{k}_note", placeholder="What was hard, what to revisit")
                    if st.button("Save", key=f"{k}_save", icon=":material/save:", type="primary"):
                        school.log_week(c["id"], monday, lec, stu, hrs, note)
                        st.toast(f"{c['name']} · week saved")
                        st.rerun()
                total_h += float(w.get("study_hours", 0))
                if w:
                    st.caption(f"Saved · {w['study_hours']:g} h · lecture +{w['lecture_chapters']:g}, you +{w['study_chapters']:g}")
        st.caption(
            f"Saved so far this week: **{total_h:g} h** · suggested {suggested_hours:g} h "
            f"({school.total_units():g} units × 2 h)."
        )


# --- exams & plan ------------------------------------------------------------

with exams_tab:
    with st.expander("Add an exam, test or assignment", icon=":material/add_circle:", expanded=not school.exams()):
        exam_form("newexam")
    all_exams = school.exams()
    upcoming_list = [e for e in all_exams if e["status"] != "Done" and (e["day"] is None or e["day"] >= TODAY)]
    past = [e for e in all_exams if e not in upcoming_list]
    if not all_exams:
        st.info("No exams yet. Add one above and plan the study for it.", icon=":material/quiz:")
    if upcoming_list:
        st.markdown("### Coming up")
        for e in upcoming_list:
            exam_card(e, key_prefix="up")
    # study sessions not tied to an exam, and a way to add a free one
    with st.expander("Study sessions not tied to an exam", icon=":material/menu_book:"):
        free = [s for s in school.sessions() if s["exam_id"] is None]
        if free:
            session_rows(free, "free")
        if courses:
            st.caption("Add one")
            with st.container(horizontal=True, vertical_alignment="bottom"):
                fc = st.selectbox("Course", [c["id"] for c in courses], format_func=lambda i: names.get(i, "?"), key="free_course", width=200)
                fd = st.date_input("Day", value=TODAY, key="free_day", width=150)
                ft = st.time_input("Time", value=time(18, 0), key="free_time", step=timedelta(minutes=15), width=110)
                fm = st.number_input("Minutes", min_value=15, max_value=480, value=60, step=15, key="free_min", width=110)
                ftopic = st.text_input("Topic", key="free_topic", placeholder="What you will study")
                if st.button("Add", key="free_add", icon=":material/add:", type="primary"):
                    school.add_session(int(fc), fd, ft, int(fm), ftopic)
                    st.rerun()
    if past:
        with st.expander(f"Done or past ({len(past)})", icon=":material/history:"):
            for e in past:
                exam_card(e, key_prefix="past")


# --- progress ----------------------------------------------------------------

with progress_tab:
    if not courses:
        st.caption("Add a course first.")
    else:
        allw = school.all_weeks_frame()
        if len(allw):
            with st.container(border=True):
                st.markdown("**Hours studied per week, by course**")
                st.altair_chart(
                    alt.Chart(allw)
                    .mark_bar(cornerRadiusEnd=3)
                    .encode(
                        x=alt.X("week_start:T", title=None),
                        y=alt.Y("study_hours:Q", title="Hours"),
                        color=alt.Color(
                            "course:N",
                            title=None,
                            scale=alt.Scale(
                                domain=[c["name"] for c in courses],
                                range=[c["color"] for c in courses],
                            ),
                            legend=alt.Legend(orient="bottom"),
                        ),
                        tooltip=["course", alt.Tooltip("week_start:T", title="Week"), alt.Tooltip("study_hours:Q", title="Hours")],
                    )
                    .properties(height=220),
                    width="stretch",
                )
        for c in courses:
            df = school.week_frame(c["id"])
            p = school.progress(c["id"])
            with st.container(border=True):
                with st.container(horizontal=True, vertical_alignment="center"):
                    st.markdown(f"**{c['name']}**", width="stretch")
                    ui.chip(f"{p['hours']:g} h over {p['weeks']} week(s) · {p['hours_per_week']:.1f} h/week", c["color"])
                if not len(df):
                    st.caption("Nothing logged yet — fill in *This week*.")
                    continue
                long = df.melt(
                    id_vars=["week_start"], value_vars=["lecture_cum", "study_cum"],
                    var_name="who", value_name="chapters",
                )
                long["who"] = long["who"].map({"lecture_cum": "Lecture", "study_cum": "You"})
                total_line = alt.Chart(pd.DataFrame({"y": [p["total"]]})).mark_rule(strokeDash=[4, 4], color="#94a3b8").encode(y="y:Q")
                st.altair_chart(
                    alt.Chart(long)
                    .mark_line(point=True, strokeWidth=2.5)
                    .encode(
                        x=alt.X("week_start:T", title=None),
                        y=alt.Y("chapters:Q", title="Chapters (cumulative)"),
                        color=alt.Color(
                            "who:N", title=None,
                            scale=alt.Scale(domain=["Lecture", "You"], range=["#94a3b8", c["color"]]),
                            legend=alt.Legend(orient="bottom"),
                        ),
                        tooltip=[alt.Tooltip("week_start:T", title="Week"), "who", "chapters"],
                    )
                    .properties(height=200)
                    + total_line,
                    width="stretch",
                )
                st.caption("Grey is where the lecture is, colour is where you are; the dashed line is the whole syllabus. The gap is your backlog.")
