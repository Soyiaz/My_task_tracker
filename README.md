# Plan tracker

A local, single-file-database app for running a time-boxed plan — a summer,
a semester, a sabbatical, a product push. You decide the tracks the plan is
made of and the finish lines that count; the app helps you plan each week,
work each day, log the hours, and reads back where you stand against the
goal — and *why* you are behind wherever you are.

Built with Streamlit, stored in SQLite. No accounts, no server, no cloud:
everything lives in one `tracker.db` next to the app. Back up that file and
you have backed up everything.

## Running it

```
pip install streamlit pandas
streamlit run streamlit_app.py
```

(On Windows, `start.bat` does the same through a local `.venv` if you have
one.)

The first run creates `tracker.db` and plants a **starter plan** — the
author's summer: seven tracks covering an internship, PCB design, UAV
flying, income, a startup, a student club and personal growth. It is there
as a worked example, not a rule. Keep whatever is useful and delete the
rest.

## Make it yours

Everything about the structure is editable inside the app — no code, no
data loss. On **Settings**, under *The structure — make it yours*:

- **Tracks** — the big areas your plan is made of. Add, rename, reorder or
  delete them. Deleting one takes everything filed under it, so the app
  shows exactly what that costs ("4 tasks, 12.5 h logged, 15 milestones")
  and asks for explicit confirmation first.
- **Categories** — the kinds of work inside a track. Each category can
  demand the information *you* want captured with it: a title, a why, a
  link, free details, or an uploaded file. Work logged there is refused
  until those fields are filled, so the record stays worth reading later.
  Deleting a category keeps its tasks and hours — they only lose the label.
- **Subcategories** — one level finer, with the domains each one usually
  feeds.
- **Domains** — the cross-cutting lenses everything is measured by (see
  below). Rename the defaults or replace them with your own, with a target
  share each.

Milestones — the finish lines that drive the score — live on the **Tracks &
milestones** page, editable in place, including for a track you created five
minutes ago. The plan's start and end dates, the weekly hour target and the
standing time split are at the top of Settings.

The only file worth editing by hand is `tracker/taxonomy.py`, and only if
you want to change what a *fresh* database starts with — for instance to
ship your own template to someone else.

## Hosting it with accounts (optional)

Run locally, the app needs no accounts — your data is a file on your disk.
Deployed (say on Streamlit Community Cloud), the container's disk is wiped
on every restart and shared by every visitor, so a plain deployment is only
good as a resettable demo.

Cloud mode fixes that. When the deployment's secrets contain the two
sections below, the app gates itself behind **Sign in with Google** and
gives every account its own database, parked in a free Supabase storage
bucket so it survives restarts. A new account starts **blank** — no tracks,
no template — and every page points to the structure editor until the first
track exists; the starter plan only appears in the shared **Just try the
demo** sandbox, which is exactly what it is for: seeing a filled-in tracker
before building your own. Without the secrets, nothing changes — local use
stays loginless and starts from the template.

Setup, once, all free:

1. **Google login** — in Google Cloud Console create an OAuth 2.0 *Web
   application* client. Authorized redirect URI:
   `https://<your-app>.streamlit.app/oauth2callback`. Note the client id
   and secret.
2. **Supabase** — create a free project and copy its URL and the
   `service_role` API key. The storage bucket is created automatically on
   first use.
3. **Secrets** — in the deployed app's settings, add:

   ```toml
   [auth]
   redirect_uri = "https://<your-app>.streamlit.app/oauth2callback"
   cookie_secret = "<any long random string>"
   client_id = "<google client id>"
   client_secret = "<google client secret>"
   server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

   [supabase]
   url = "https://<project>.supabase.co"
   key = "<service_role key>"
   bucket = "trackers"
   ```

Honest limits: each user's database is uploaded whole when it changes (it
is small), and if the same account is open in two places at once the last
writer wins. Uploaded files are parked in the same bucket.

**Email and password** works beside Google, with no extra setup. The
landing page has *Log in* and *Sign up* tabs; a password is stored only as
a salted PBKDF2 hash in `<account>/auth.json` in the bucket, and no
database table is added or changed. An email that already has a tracker
made through Google cannot be claimed by signing up with it: that owner
signs in with Google and sets a password under *Password* in the sidebar.
Eight wrong passwords in a row lock the account for 15 minutes. Honest
limits: emails are not verified, there is no "forgot password" (sign in
with Google and set a new one, or delete `auth.json` in the bucket), and a
password login lasts for the browser session — a page refresh asks again.

### The journal (optional)

The Journal page keeps its entries in a [Neon](https://neon.tech) Postgres
database — free tier, no card. Create a project, copy its connection
string, and add one more section to the secrets (or set `NEON_URL` in the
environment for a local install):

```toml
[neon]
url = "postgresql://USER:PASSWORD@HOST/DB?sslmode=require"
```

Without it, the Journal page shows setup instructions and the rest of the
app is unaffected. Entries are keyed by the same anonymous account id the
tracker uses; the shared demo gets no journal.

### The Telegram bot (optional)

The same journal can be written from Telegram. Make a bot with
[@BotFather](https://t.me/BotFather), then add to the secrets:

```toml
[telegram]
token = "<the token BotFather gives you>"
access_code = "<a code every new chat must send before the bot answers>"
```

The bot runs as a background thread inside the deployed app — no extra
hosting — and stores every conversation's state in Neon, so a reboot loses
nothing. New chats must pass the access code, then sign up with an email
and password; the email decides which journal entries land in (use the
website's Google email and both write the same journal). Commands:
`journal`, `read`, `days`, `logout`.

Honest limit: the bot is awake only while the app is awake. Community
Cloud puts apps to sleep after ~12 h without visitors; a free uptime
pinger (e.g. cron-job.org hitting the app URL) keeps it always on.

## The loop

**Once a week** — open *The week*. Budget the hours across your tracks for
the week you actually have, then walk the tree — track, kind of work, which
one — and tick the milestones you mean to move. Everything you pick inherits
the whole path and the domains it feeds, so a task already knows where it
will be logged. Last week's numbers and last week's "one thing to change"
sit right there while you do it.

**Every morning** — open *Today*. The tasks you scheduled are waiting. Start
the stopwatch on one and the time lands on that task; finish a task linked
to a milestone and the milestone ticks itself off.

**Every evening** — log anything the stopwatch missed, tick what got done.

**End of the week** — the *Review* tab shows budget against actual, what got
finished and what did not, and asks three questions worth answering.

## Tracks say where, domains say what for

Every logged hour and every planned task picks a path down the tree —
track, category, subcategory — and some branches ask for more before they
accept an entry.

**Domains** cut across all of it. A track answers *where* an hour went; a
domain answers what it was *for*. In the starter plan the domains are
Robotics, AI, Computer vision and Personal growth — so a club project, a
PCB board and an internship robot can all be feeding the same skill, and
the dashboard reads the whole plan through that lens. An hour can feed more
than one domain, so the shares deliberately add to more than 100%. Untagged
hours show up as *Unassigned* — visible on purpose, because a plan measured
by domains should admit what it could not classify.

## The pages

| Page | What it is for |
| --- | --- |
| **Today** | The day's plan, the stopwatch, per-task logging, today's entries — and *Also today*: the deadlines, exams, lectures and study sessions that fall on the day. |
| **The week** | Budget → the work → review. The planning page. |
| **Calendar** | Everything with a date in one place — tasks, application deadlines, planned application days, exams, lectures, study sessions — as a month grid, a week on a clock, a day in detail, or a list. Tap any item and it opens the page where it was saved, with that item at the top. |
| **Journal** | A six-question morning check-in, answered like a chat, with an archive of every day. Lives in its own Neon Postgres database (see below). |
| **To do** | Every task from every week in one list. Add new ones, mark not started / in progress / done, flag what is urgent, and filter by track, status, scope or name. |
| **School** | Courses with their units and lecture timetable; a weekly log of how many chapters the lecture covered against how many you studied and for how long; exams, tests and finals with a date and time; and a study plan per exam that lays dated, timed sessions on the calendar. |
| **Notes** | A Notability-style notebook per course: pen, highlighter, eraser, lasso, text and shapes on lined, grid, dotted, plain or Cornell paper, with pages, thumbnails and PNG export. Autosaves. |
| **Dashboard** | Goal completion, on-pace score, which track needs the next block of work, whether the planning habit is holding, the charts behind all of it — and a reminder pinned to the top-right corner for every deadline, planned application and exam within two weeks. |
| **Reports** | Week, month, whole plan — hours registered against target and against the budget you set, with what got finished. |
| **Opportunities** | Scholarships, internships, programmes and the like: category, organisation, link, the deadline (date and time), when applications open, the day you plan to apply, and a tickable list of what each one requires. |
| **Tracks & milestones** | The plan itself. Every skill, tool, project, book and opportunity, editable in place. |
| **Settings** | Dates, weekly hour target, the standing time split, the structure editors, domains and colours. |

## Opportunities, deadlines and reminders

An opportunity is anything you apply for. Each one carries a **category**
(scholarship, internship, job, fellowship, competition, grant, conference,
programme, research, volunteering, other), the **deadline** with a closing
time, optionally the day **applications open** and the day **you plan to
apply**, and a list of **requirements** — transcript, letters, essay —
ticked off one by one with a progress bar.

The deadline and the planned application day are drawn on the Calendar.
On the Dashboard, anything closing, opening or being sat within fourteen
days is pinned in a card at the **top-right corner** of the screen (close it
with the ✕, or hide it for the session with the button under it), listed in
full below the headline numbers, and announced once per session as a
toast. The sidebar carries a badge on every page when something is due
within a week.

## School

**Courses** have a name, code, units, instructor, colour, term dates, the
number of chapters or topics in the syllabus, and a weekly **lecture
timetable** (day, start, end, room) that the Calendar draws week after week.

**This week** is the weekly log: for each course, how many chapters the
lecture covered, how many you studied, and how many hours it took. The
course card shows the lecture's progress and yours through the syllabus,
and the *backlog* — chapters the lecture has covered that you have not. The
page suggests two hours of study per unit per week, the usual rule of
thumb, and compares the week against it.

**Exams & study plan** holds quizzes, tests, midterms, finals, assignments
and projects, each with a date, time, length, location, weight and topics.
Each exam has a *start studying on* date (suggested from its kind: three
days before a quiz, three weeks before a final) and a **Plan the study**
button that lays study sessions on the calendar from that day to the day
before the exam, on the weekdays you tick, at the time and length you
choose, dealing your list of topics out across them. Sessions are ticked off
as they happen; a missed one is flagged. Sessions can also be added loose,
not tied to any exam.

**Progress** charts, per course, where the lecture is against where you are
week by week (the gap between the lines is the backlog), and the hours
studied per week across courses.

### Notes

The Notes page is the study notebook, modelled on Notability. Tools across
the top: **pen** (pressure-sensitive with a stylus), **highlighter**,
**eraser** (removes whole strokes), **lasso** (select, move, duplicate,
delete), **text**, **shapes** (line, arrow, rectangle, ellipse) and a
**hand** for scrolling. A second row holds the colour swatches, three
stroke widths, the paper (lined, grid, dotted, plain, Cornell) and paper
colour (white, cream, dark). Pages stack vertically with thumbnails down
the left; add, delete, zoom, fit, export a page as PNG. Undo and redo are
per page. Keyboard shortcuts are listed under the notebook.

On a tablet the stylus writes and a finger scrolls; tick *Finger draws* to
write with a finger. The notebook autosaves a moment after the pen lifts
("Saved" top-right), and on leaving the page.

Each notebook belongs to a course (or to none). The ink is vector data,
kept as one JSON file per notebook under `files/` — parked in the cloud
bucket like any upload — while the list of notebooks lives with the rest
of the settings.

## Every plan has a date and a time

A task is always on a day and at a time of day. The forms that create one
(Today, The week, To do) ask for both and start from today and the next
free slot on that day's calendar; the editor does the same. Tasks made
before this rule, or that lost their day, are listed at the bottom of the
Calendar under *Plans without a date or a time* with a one-click fix that
gives each its own week's first open day (or today, for a week that has
gone) and the next free quarter-hour after everything already timed.

## How the numbers work

**Goal completion** is how much of the plan is finished. Each milestone
carries a weight — a skill might count 1, a written output 2–3, a built
project 3. Per track it is finished weight over total weight, with anything
in progress counting half. Tracks are then blended by their planned share of
time, so a track meant to take 30% of the plan moves the number three times
as much as one meant to take 10%. It only goes up.

**On pace** is whether that progress is where it should be *today*, and it
is the number that can fall:

- half **time** — hours logged against the hours the plan expected by now
- half **milestones** — completion against the fraction of the plan elapsed

A track with the hours but nothing finished scores 50%. So does one that
finishes things without the hours behind it. That split is what lets the
dashboard say *why* a track is behind, not just that it is.

**Work on this next** ranks tracks by their on-pace score, worst first, and
suggests an hour figure: next week's normal allocation plus whatever the
track is behind. Under each one are the first few unfinished items,
half-done ones first.

**Editing a task** works the same on Today, The week and To do: an **Edit**
popover on every row that can change the name, move it anywhere in the tree,
retag its domains, change the estimate, the day, the time, the status and the
urgency, unlink it from its milestone, or delete it. The **Flag** button sits
beside it on all three pages, and every place that *creates* a task offers
the urgent toggle up front.

**The day is a free date, and the week follows it.** Nothing pens you into
the seven days of the week a task currently sits in — pick any date and the
task re-files itself under the week that date belongs to, so budgets and
reviews count it where it actually happened. Pushing a Sunday task to
tomorrow moves it into next week's plan rather than leaving it behind.

**Several days at once.** When adding work on the week page, *Several days*
lets you drag a span on the calendar and then untick any day inside it you
did not mean — Tuesday, Thursday and Friday but not Wednesday. One task is
created per day, so the button tells you the real total before you commit:
*"3 items × 3 days = 9 tasks, 13h 30m."* A span crossing Sunday is fine;
each task files under the week of its own day.

**The To do list is grouped by track**, in the plan's order, with each
heading carrying the open count, the time still planned and any overdue
count. Urgent work sits above all of it, across every track, because urgent
outranks tidiness.

**Urgent** does one thing: a task flagged urgent and still open sits at the
top of the *To do* page, and is counted in the sidebar. Finishing it drops
it back into the ordinary pile — an urgent thing you have already done is
not asking anything of you. Everything below the urgent block is ordered in
progress first, then not started, with overdue ahead of the rest and the
soonest day first.

**Hit rate** is tasks finished over tasks planned, for a day or a week.
Dropping a task explicitly ("not happening today") takes it out of the
denominator — an honest no costs nothing, quietly ignoring a task costs you.

**Budget attainment** is hours logged over hours budgeted for that week.

**Hours expected so far** is the sum of the budgets you actually set, week
by week, prorated for a week that is only part over. Because the split
depends on the week, the standing shares in Settings are a *fallback* —
they prefill a new week's budget and stand in for any week that went
unplanned, nothing more. The week page is where the real allocation happens.

**Domain coverage** is each lens's share of all logged hours, against the
target share in Settings. The dashboard names whichever lens is thinnest.

## Where the new things are stored

The SQLite schema has not changed. Opportunities, courses, the weekly
school log, exams, study sessions and the list of notebooks are each one
JSON value in the existing `settings` table (keys `opportunity_deadlines`,
`school_courses`, `school_weeks`, `school_exams`, `school_sessions`,
`notebooks`), read and written through `tracker/store.py` — the same
pattern task times already used. Notebook ink is one JSON file per
notebook under `files/`. A database made before this update works
unchanged, locally or in a cloud bucket.

## Layout

```
streamlit_app.py     navigation + the sidebar status panel
.streamlit/          theme (light and dark)
files/               uploaded artefacts and notebook ink (yours — not in the repo)
tracker.db           your data (yours — not in the repo)
tracker/
  taxonomy.py        what a fresh database starts with
  db.py              schema, connections, editable-table writeback
  seed.py            plants the taxonomy into a fresh database
  structure.py       reading and editing the tree, requirement checks, files
  scoring.py         track health, domain coverage, week and month reports
  planning.py        week budgets, tasks, plan-vs-actual adherence
  store.py           JSON collections in the settings table (no schema change)
  opps.py            opportunities: deadlines, apply dates, requirements
  school.py          courses, weekly log, exams, study sessions and plans
  notes.py           notebooks: the index, and the ink files under files/
  notecanvas.py      the Notability-style editor (a Streamlit v2 component)
  agenda.py          every dated thing as one feed; reminders; calendar jumps
  entryform.py       the track → category → subcategory → detail picker
  taskedit.py        the flag, the edit popover and the row badges
  ui.py              colours, chips, the corner reminder, formatting
app_pages/
  today.py           the day's plan, stopwatch, structured logging
  week.py            budget / the work / review
  calendar.py        month, week, day and list views of everything dated
  todo.py            every task, everywhere, urgent first
  school.py          courses, this week, exams & study plan, progress
  notes.py           the notebook page
  opportunities.py   deadlines and requirements
  dashboard.py       headline numbers, reminders, domain coverage, advice, charts
  reports.py         week / month / whole plan
  tracks.py          the tree and the milestones, editable
  settings.py        window, target, shares, structure, domains, colours
```

Day to day, reshape the structure from the Settings page — it edits in
place and keeps your data. **Rebuild everything** (also on Settings) is the
scorched-earth option: it wipes the database, log included, and replants
from `taxonomy.py`.
