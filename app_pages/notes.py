"""Notes: a Notability-style notebook per course, for studying.

Pen, highlighter, eraser, lasso, text and shapes on lined, grid, dotted,
plain or Cornell paper; pages stack vertically with thumbnails down the
side; everything autosaves a moment after the pen lifts. The ink is kept as
vector strokes in one JSON file per notebook under ``files/`` (see
``tracker/notes.py``), so it is parked in the cloud like any upload.
"""

import streamlit as st

from tracker import notecanvas, notes, school, ui

ui.page_header(
    "Notes",
    "A notebook per course. Write with a pen, a finger or the mouse; it "
    "saves itself.",
    ":material/draw:",
)

courses = school.courses(include_archived=True)
course_names = {c["id"]: c["name"] for c in courses}
course_colors = {c["id"]: c["color"] for c in courses}


# --- which notebook ------------------------------------------------------------

all_nbs = notes.notebooks()
course_filter = st.session_state.get("notes_course")

bar = st.container(horizontal=True, vertical_alignment="bottom")
with bar:
    course_opts = [None] + [c["id"] for c in courses]
    course_filter = st.selectbox(
        "Course",
        course_opts,
        index=course_opts.index(course_filter) if course_filter in course_opts else 0,
        format_func=lambda i: "All courses" if i is None else course_names[i],
        key="notes_course_pick",
        width=200,
    )
    st.session_state["notes_course"] = course_filter
    shown = [n for n in all_nbs if course_filter is None or n["course_id"] == course_filter]
    ids = [n["id"] for n in shown]
    current = st.session_state.get("notes_current")
    if current not in ids:
        current = ids[0] if ids else None
    labels = {
        n["id"]: n["title"]
        + (f" · {course_names[n['course_id']]}" if n["course_id"] in course_names and course_filter is None else "")
        for n in shown
    }
    picked = st.selectbox(
        "Notebook",
        ids,
        index=ids.index(current) if current in ids else 0,
        format_func=lambda i: labels.get(i, "?"),
        key=f"notes_pick_{course_filter}",
        width=320,
        disabled=not ids,
        placeholder="No notebooks yet",
    ) if ids else None
    if picked is not None:
        st.session_state["notes_current"] = picked

    with st.popover("New", icon=":material/add:"):
        title = st.text_input("Title", key="nb_new_title", placeholder="e.g. Lecture 4 — eigenvalues")
        cid = st.selectbox(
            "Course",
            [None] + [c["id"] for c in courses],
            index=([None] + [c["id"] for c in courses]).index(course_filter) if course_filter in course_names else 0,
            format_func=lambda i: "No course" if i is None else course_names[i],
            key="nb_new_course",
        )
        paper = st.selectbox("Paper", list(notes.PAPERS), format_func=lambda k: notes.PAPERS[k], key="nb_new_paper")
        pcolor = st.selectbox("Paper colour", list(notes.PAPER_COLORS), format_func=lambda k: notes.PAPER_COLORS[k], key="nb_new_pcolor")
        if st.button("Create notebook", type="primary", icon=":material/add:", key="nb_new_go"):
            nid = notes.create(title, cid, paper, pcolor)
            st.session_state["notes_current"] = nid
            st.session_state["notes_course"] = cid
            # the pickers keep their own widget state; drop it so they open on the new one
            for k in [k for k in st.session_state if str(k).startswith("notes_pick_") or k == "notes_course_pick"]:
                st.session_state.pop(k, None)
            st.session_state.pop("nb_new_title", None)
            st.rerun()

    if picked is not None:
        nb = notes.notebook(picked)
        with st.popover(":material/more_horiz:", help="Rename, move or delete"):
            new_title = st.text_input("Title", value=nb["title"], key=f"nb_ren_{picked}")
            new_course = st.selectbox(
                "Course",
                [None] + [c["id"] for c in courses],
                index=([None] + [c["id"] for c in courses]).index(nb["course_id"]) if nb["course_id"] in course_names else 0,
                format_func=lambda i: "No course" if i is None else course_names[i],
                key=f"nb_move_{picked}",
            )
            if st.button("Save", key=f"nb_ren_go_{picked}", type="primary", icon=":material/save:"):
                notes.rename(picked, new_title)
                notes.move(picked, new_course)
                st.rerun()
            st.divider()
            st.caption("Deleting removes every page. There is no undo.")
            if st.button("Delete notebook", key=f"nb_del_{picked}", icon=":material/delete_forever:"):
                notes.delete(picked)
                st.session_state.pop("notes_current", None)
                for k in [k for k in st.session_state if str(k).startswith("notes_pick_")]:
                    st.session_state.pop(k, None)
                st.toast("Notebook deleted")
                st.rerun()
    tall = st.segmented_control("Height", ["Normal", "Tall"], default="Normal", key="notes_height", label_visibility="collapsed")


if picked is None:
    st.info(
        "No notebook yet. Press **New** to start one — pick the course it belongs "
        "to and the paper you like.",
        icon=":material/draw:",
    )
    if not courses:
        st.caption("Courses are made on the School page; a notebook can also live without one.")
    st.stop()


# --- the editor ----------------------------------------------------------------

nb = notes.notebook(picked)
doc = notes.load_doc(picked)
seq_key = f"notes_saved_seq_{picked}"
saved_seq = int(st.session_state.get(seq_key, doc.get("seq", 0)) or 0)

result = notecanvas.mount(
    picked,
    doc,
    nb["title"],
    course_names.get(nb["course_id"], ""),
    course_colors.get(nb["course_id"], ""),
    saved_seq=saved_seq,
    height=1000 if tall == "Tall" else 780,
)

incoming = getattr(result, "doc", None)
if isinstance(incoming, dict) and incoming.get("pages"):
    seq = int(incoming.get("seq", 0) or 0)
    if seq > saved_seq:
        notes.save_doc(picked, incoming)
        st.session_state[seq_key] = seq
        st.toast("Notebook saved", icon=":material/save:")

st.caption(
    f"{nb['pages']} page{'s' if nb['pages'] != 1 else ''}"
    + (f" · last written {nb['updated_at'][:16].replace('T', ' ')}" if nb["updated_at"] else "")
    + " · Shortcuts: **P** pen · **H** highlighter · **E** eraser · **L** lasso · "
    "**T** text · **S** shapes · **V** scroll · **Z** undo · **Shift+Z** redo · "
    "**[ ]** thinner / thicker · **+ − 0** zoom · **Ctrl+wheel** zoom · "
    "double-click a text to edit it. On a tablet the stylus writes and a "
    "finger scrolls; tick *Finger draws* to write with a finger."
)
