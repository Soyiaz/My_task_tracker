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
| **Today** | The day's plan, the stopwatch, per-task logging, and today's entries. |
| **The week** | Budget → the work → review. The planning page. |
| **To do** | Every task from every week in one list. Add new ones, mark not started / in progress / done, flag what is urgent, and filter by track, status, scope or name. |
| **Dashboard** | Goal completion, on-pace score, which track needs the next block of work, whether the planning habit is holding, and the charts behind all of it. |
| **Reports** | Week, month, whole plan — hours registered against target and against the budget you set, with what got finished. |
| **Tracks & milestones** | The plan itself. Every skill, tool, project, book and opportunity, editable in place. |
| **Settings** | Dates, weekly hour target, the standing time split, the structure editors, domains and colours. |

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
retag its domains, change the estimate, the day, the status and the urgency,
unlink it from its milestone, or delete it. The **Flag** button sits beside
it on all three pages, and every place that *creates* a task offers the
urgent toggle up front.

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

## Layout

```
streamlit_app.py     navigation + the sidebar status panel
.streamlit/          theme (light and dark)
files/               uploaded artefacts (yours — not in the repo)
tracker.db           your data (yours — not in the repo)
tracker/
  taxonomy.py        what a fresh database starts with
  db.py              schema, connections, editable-table writeback
  seed.py            plants the taxonomy into a fresh database
  structure.py       reading and editing the tree, requirement checks, files
  scoring.py         track health, domain coverage, week and month reports
  planning.py        week budgets, tasks, plan-vs-actual adherence
  entryform.py       the track → category → subcategory → detail picker
  taskedit.py        the flag, the edit popover and the row badges
  ui.py              colours, chips, formatting shared across pages
app_pages/
  today.py           the day's plan, stopwatch, structured logging
  week.py            budget / the work / review
  todo.py            every task, everywhere, urgent first
  dashboard.py       headline numbers, domain coverage, advice, charts
  reports.py         week / month / whole plan
  tracks.py          the tree and the milestones, editable
  settings.py        window, target, shares, structure, domains, colours
```

Day to day, reshape the structure from the Settings page — it edits in
place and keeps your data. **Rebuild everything** (also on Settings) is the
scorched-earth option: it wipes the database, log included, and replants
from `taxonomy.py`.
