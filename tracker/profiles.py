"""Ready-made plans for the two accounts, from the notebook page.

Three columns on that page: what is Li's alone, what is Zen's alone, and the
*Lizen* column both of them run. A profile is one person's column plus the
shared one. Each track lists its categories; the domains, the required
fields and the milestones are left for the owner to add in Settings.

Planting is additive and idempotent: a track that already exists (by key)
is left exactly as it is, including its categories, so applying a profile
to a tracker that already has work in it only fills the gaps.
"""

from __future__ import annotations

from tracker import db

# (key, name, icon, colour, goal, categories)
LI = [
    (
        "flolabs", "FloLabs", ":material/apartment:", "#6366f1",
        "The internship: real engineering on IoT and the humanoid.",
        ["IoT", "Humanoid"],
    ),
    (
        "projects", "Projects", ":material/build:", "#0ea5e9",
        "Robotics, boards and the website, each one shippable.",
        ["Robotics", "PCB", "Website"],
    ),
]

ZEN = [
    (
        "gheero", "Gheero", ":material/rocket_launch:", "#6366f1",
        "", [],
    ),
    (
        "pms", "PMS", ":material/dashboard:", "#0ea5e9",
        "", [],
    ),
    (
        "ethioadvise", "Ethioadvise", ":material/support_agent:", "#f43f5e",
        "", [],
    ),
]

LIZEN = [
    (
        "applications", "Applications", ":material/send:", "#f59e0b",
        "Everything that gets the applications out the door.",
        [
            "IELTS", "Recommendation letters", "Transcript & MOI",
            "Reaching out to profs", "Applying", "Apps & recruitment gatherings",
        ],
    ),
    (
        "class", "Class", ":material/menu_book:", "#8b5cf6",
        "Keep up with the semester.",
        ["Studying", "Assignment"],
    ),
    (
        "ethioxplore", "EthioXplore", ":material/explore:", "#14b8a6",
        "The startup: ads and opportunities, the build, the meetings.",
        ["AD & opportunity", "Development", "Meetings"],
    ),
    (
        "aar", "AAR Club", ":material/groups:", "#22c55e",
        "The club: meetings, events and the projects they spawn.",
        ["Meetings", "Events", "Projects"],
    ),
    (
        "brightaddis", "Bright Addis", ":material/storefront:", "#ec4899",
        "Wedet, Nester, the company tracker and deliveries.",
        ["Wedet", "Nester", "Company tracker", "Package delivery"],
    ),
    (
        "jobapps", "Job Apps", ":material/work:", "#f97316",
        "Two applications a day.",
        ["2 a day"],
    ),
    (
        "bible", "Bible study", ":material/auto_stories:", "#a16207",
        "One chapter a day, church every Sunday.",
        ["1 chapter a day", "Church (every Sunday)"],
    ),
    (
        "business", "Personal business", ":material/lightbulb:", "#64748b",
        "Saving towards 50k together, ideas, hackathons.",
        ["Saving (50k combined)", "Ideas", "Hackathon"],
    ),
]

PROFILES = {
    "li": {"label": "Li", "tracks": LI + LIZEN},
    "zen": {"label": "Zen", "tracks": ZEN + LIZEN},
}

# Which account gets which plan the moment it is created.
ACCOUNTS = {
    "sosinazegeyem@gmail.com": "li",
    "biruk7479@gmail.com": "zen",
}


def for_email(email: str | None) -> str | None:
    return ACCOUNTS.get((email or "").strip().lower())


def _slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name.lower()).strip("_")


def plant(profile: str) -> dict:
    """Add the profile's tracks and categories that are not there yet.
    Returns how many of each were added."""
    tracks = PROFILES[profile]["tracks"]
    have = {r["key"]: int(r["id"]) for r in db.query("SELECT id, key FROM tracks").to_dict("records")}
    next_sort = int(db.query("SELECT COALESCE(MAX(sort), 0) AS s FROM tracks")["s"].iloc[0]) + 1
    share = 1 / max(1, len(tracks))
    added = {"tracks": 0, "categories": 0}

    for key, name, icon, color, goal, cats in tracks:
        if key in have:
            continue
        track_id = db.execute(
            "INSERT INTO tracks(key, name, icon, color, goal, target_share, sort) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key, name, icon, color, goal, share, next_sort),
        )
        next_sort += 1
        added["tracks"] += 1
        for i, cat in enumerate(cats):
            db.execute(
                "INSERT INTO categories(track_id, key, name, requires, domains, sort) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (track_id, _slug(cat), cat, "", "", i),
            )
            added["categories"] += 1
    return added


def plant_for(email: str | None) -> dict | None:
    """The plan for this account, if it has one; None otherwise."""
    profile = for_email(email)
    return plant(profile) if profile else None
