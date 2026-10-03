"""Summer tracker — July 15 to September 15.

    streamlit run streamlit_app.py

The order of the menu is the order of the habit: plan the week, work the day,
then read what it added up to.
"""

from datetime import date, timedelta

import streamlit as st

from tracker import cloud, db

st.set_page_config(
    page_title="Plan tracker",
    page_icon=":material/target:",
    layout="wide",
)

# In a deployment with login configured this gates the session and points it
# at the signed-in user's own database; everywhere else it does nothing.
cloud.activate()

db.init()

# The Telegram journal bot rides along inside this process — a daemon thread
# that long-polls while the app is awake. Does nothing unless [telegram] and
# [neon] are both in the secrets.
try:
    from tracker import bot

    bot.ensure_running()
except Exception:
    pass

# Imported after init so the schema exists before anything queries it.
from tracker import agenda, planning, scoring, ui  # noqa: E402

nav = st.navigation(
    {
        "Every day": [
            st.Page(
                "app_pages/today.py", title="Today", icon=":material/wb_sunny:", default=True
            ),
            st.Page("app_pages/week.py", title="The week", icon=":material/date_range:"),
            st.Page(
                "app_pages/calendar.py",
                title="Calendar",
                icon=":material/calendar_clock:",
            ),
            st.Page(
                "app_pages/journal.py",
                title="Journal",
                icon=":material/auto_stories:",
            ),
            st.Page(
                "app_pages/todo.py", title="To do", icon=":material/checklist_rtl:"
            ),
        ],
        "School": [
            st.Page("app_pages/school.py", title="School", icon=":material/school:"),
            st.Page("app_pages/notes.py", title="Notes", icon=":material/draw:"),
        ],
        "Review": [
            st.Page("app_pages/dashboard.py", title="Dashboard", icon=":material/speed:"),
            st.Page(
                "app_pages/reports.py", title="Reports", icon=":material/calendar_month:"
            ),
        ],
        "The plan": [
            st.Page(
                "app_pages/opportunities.py",
                title="Opportunities",
                icon=":material/work:",
            ),
            st.Page(
                "app_pages/tracks.py",
                title="Tracks & milestones",
                icon=":material/checklist:",
            ),
            st.Page("app_pages/settings.py", title="Settings", icon=":material/tune:"),
        ],
    }
)

# --- sidebar: the state of play, on every page ------------------------------

with st.sidebar:
    # What is about to be due — deadlines, planned applications, exams —
    # is worth a badge on every page, not just the dashboard.
    try:
        due = agenda.due_soon(7)
    except Exception:
        due = []
    if due:
        worst = due[0]
        st.badge(
            f"{len(due)} due within a week · {worst['title'][:28]}"
            + ("…" if len(worst["title"]) > 28 else ""),
            icon=":material/alarm:",
            color="red" if worst["days_left"] <= 1 else "orange",
        )

    if not len(scoring.tracks()):
        st.caption(
            "A blank tracker. Build your first track under **Settings → "
            "The structure — make it yours**."
        )
    else:
        today = date.today()
        monday = scoring.week_start(today)
        h = scoring.headline()
        week = planning.week_adherence(monday)
        day = planning.day_adherence(today)

        running = scoring.running_timer()
        if running:
            st.badge(
                f"{ui.hours_text(running['minutes'])} · {running['activity'] or running['track']}",
                icon=":material/timer:",
                color="violet",
            )

        board = planning.board()
        if len(board):
            open_tasks = board[board["is_open"]]
            urgent = int((open_tasks["urgent"]).sum()) if len(open_tasks) else 0
            overdue = int((open_tasks["overdue"]).sum()) if len(open_tasks) else 0
            if urgent:
                st.badge(f"{urgent} urgent", icon=":material/priority_high:", color="red")
            if overdue:
                st.badge(f"{overdue} overdue", icon=":material/schedule:", color="orange")

        st.caption("The plan")
        st.progress(
            min(h["goal_completion"], 1.0),
            text=f"{h['goal_completion']:.0%} complete · {h['days_left']} days left",
        )

        st.caption("This week")
        st.progress(
            min(week["hours_attainment"], 1.0),
            text=f"{week['actual_hours']:.1f} h of {week['planned_hours']:.1f} h budgeted",
        )

        st.caption("Today")
        if day["planned_minutes"]:
            st.progress(
                min(day["attainment"], 1.0),
                text=f"{ui.hours_text(day['actual_minutes'])} of "
                f"{ui.hours_text(day['planned_minutes'])} · "
                f"{day['tasks_done']}/{day['tasks_planned']} tasks",
            )
        else:
            st.caption(
                f"{ui.hours_text(day['actual_minutes'])} logged, nothing planned"
                if day["actual_minutes"]
                else "Nothing planned or logged yet"
            )

        if not week["is_planned"] and today.weekday() <= 1:
            st.info("The week is not planned yet.", icon=":material/event_busy:")
        sunday = monday + timedelta(days=6)
        if today >= sunday - timedelta(days=1) and not planning.get_week(monday)["reviewed_on"]:
            st.info("Time to review the week.", icon=":material/rate_review:")

    cloud.account_ui()

nav.run()

# Any write this run made goes back to remote storage (cloud mode only).
cloud.flush()
