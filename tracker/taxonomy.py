"""The shape of the work: seven tracks, their categories and subcategories.

Every hour logged and every task planned lands somewhere in this tree, and
carries the domains it fed. The tree is data, not code — it is written into the
database on first run and editable afterwards — but this is where it starts.

A category can demand extra detail before an entry counts as complete:

``title``    what it was — the topic, the project, the job, the hobby
``purpose``  why you did it (PCB learning is not done until this is answered)
``link``     a video or a document
``detail``   free text, for the "other" branches
``file``     an uploaded artefact, kept under ``files/``

``done_requires`` is the stricter list applied when a *project* is marked
finished — a board is not finished without a video and documentation.
"""

from __future__ import annotations

# --- the cross-cutting lenses ----------------------------------------------
#
# Tracks say where the hour was spent. Domains say what it was *for*, and they
# cut across every track: a club project, a PCB board and a FloLabs robot can
# all be feeding robotics. This is the view the whole summer is measured by.

DOMAINS = [
    ("robotics", "Robotics", "#6366f1", 1),
    ("ai", "AI", "#14b8a6", 2),
    ("cv", "Computer vision", "#f59e0b", 3),
    ("growth", "Personal growth", "#f43f5e", 4),
]

FIELD_LABELS = {
    "title": "What exactly",
    "purpose": "Why — what is it for",
    "link": "Link (video or document)",
    "detail": "Details",
    "file": "File",
}

# (key, name, icon, colour, goal, fallback share of a normal week, sort)
TRACKS = [
    (
        "flolabs",
        "FloLabs internship",
        ":material/apartment:",
        "#6366f1",
        "Real engineering workflows across IoT, robotics, automation and GTM.",
        0.25,
        1,
    ),
    (
        "pcb",
        "PCB design",
        ":material/developer_board:",
        "#0ea5e9",
        "Principles, then boards: concept to Gerbers, documented well enough "
        "to show.",
        0.20,
        2,
    ),
    (
        "uav",
        "UAV",
        ":material/flight:",
        "#14b8a6",
        "Configure it, fly it, and keep the team moving.",
        0.12,
        3,
    ),
    (
        "income",
        "Income & career",
        ":material/payments:",
        "#22c55e",
        "Turn the skills into paid work, in person or remote.",
        0.13,
        4,
    ),
    (
        "ethioxplore",
        "EthioXplore startup",
        ":material/travel_explore:",
        "#a855f7",
        "3D and technical building, plus the business side of a real startup.",
        0.10,
        5,
    ),
    (
        "club",
        "Club",
        ":material/groups:",
        "#f59e0b",
        "Projects and research with other people — AI, robotics, computer "
        "vision.",
        0.10,
        6,
    ),
    (
        "personal",
        "Personal growth",
        ":material/self_improvement:",
        "#f43f5e",
        "Travel, books and a hobby kept alive — the lens the rest is measured "
        "against.",
        0.10,
        7,
    ),
]

# track key -> categories
#   (key, name, requires, default domains, [(subcat key, name, domains)])
CATEGORIES: dict[str, list[tuple]] = {
    "flolabs": [
        (
            "iot",
            "IoT",
            [],
            ["ai"],
            [
                ("caipo", "CAIPO", ["ai"]),
                ("mini_robot", "Mini desktop robot", ["robotics", "ai"]),
                ("other", "Other", []),
            ],
        ),
        (
            "robotics",
            "Robotics",
            [],
            ["robotics"],
            [
                ("mini_robot", "Mini desktop robot", ["robotics"]),
                ("other", "Other", ["robotics"]),
            ],
        ),
        (
            "automation",
            "Automation",
            [],
            [],
            [
                ("new_workflow", "New workflow", []),
                ("edit_existing", "Editing an existing one", []),
                ("other", "Other", []),
            ],
        ),
        (
            "gtm",
            "GTM",
            ["title"],
            [],
            [
                ("video", "Video", []),
                ("script", "Script", []),
                ("other_content", "Other content", []),
            ],
        ),
    ],
    "pcb": [
        (
            "learning",
            "Learning principles",
            ["title", "purpose", "file"],
            [],
            [],
        ),
        (
            "projects",
            "Making projects",
            ["title"],
            [],
            [],
        ),
        (
            "exploring",
            "Exploring projects to make",
            ["title"],
            [],
            [
                ("robotics", "Robotics", ["robotics"]),
                ("uav", "UAV", ["robotics"]),
                ("iot_basic", "Basic IoT", []),
                ("iot_ai", "IoT with AI", ["ai"]),
                ("iot_cv", "IoT with computer vision", ["cv"]),
            ],
        ),
    ],
    "uav": [
        ("config", "Config", ["detail"], ["robotics"], []),
        ("flying", "Practice flying", [], ["robotics"], []),
        ("meeting", "Meeting", [], [], []),
    ],
    "income": [
        (
            "in_person",
            "In person",
            ["title"],
            [],
            [
                ("meeting", "Meeting", []),
                ("testing", "Testing", []),
                ("building", "Building", []),
            ],
        ),
        (
            "remote",
            "Remote",
            ["title"],
            [],
            [
                ("meeting", "Meeting", []),
                ("testing", "Testing", []),
                ("building", "Building", []),
            ],
        ),
    ],
    "ethioxplore": [
        (
            "meeting",
            "Meeting",
            [],
            [],
            [("in_person", "In person", []), ("online", "Online", [])],
        ),
        (
            "building",
            "Building",
            ["title"],
            [],
            [
                ("three_d", "3D", []),
                ("technical", "Other technical", []),
            ],
        ),
        ("business", "Business plan", ["detail"], [], []),
    ],
    "club": [
        (
            "meeting",
            "Meeting",
            [],
            [],
            [("in_person", "In person", []), ("online", "Online", [])],
        ),
        (
            "project",
            "Project",
            ["title"],
            [],
            [
                ("ai", "AI", ["ai"]),
                ("robotics", "Robotics", ["robotics"]),
                ("cv", "Computer vision", ["cv"]),
            ],
        ),
        ("research", "Research", ["title"], [], []),
    ],
    "personal": [
        (
            "travel",
            "Travel",
            [],
            ["growth"],
            [
                ("watching", "Watching", []),
                ("planning", "Searching and planning", []),
                ("travelling", "Travelling", []),
            ],
        ),
        (
            "book_club",
            "Book club",
            [],
            ["growth"],
            [("reading", "Reading", []), ("meeting", "Meeting", [])],
        ),
        (
            "hobbies",
            "Hobbies",
            ["title"],
            ["growth"],
            [
                ("learning", "Learning it", []),
                ("doing", "Doing the activity", []),
            ],
        ),
    ],
}

# Extra demands made of a *project* before it counts as finished.
PROJECT_DONE_REQUIRES = ["link", "file"]


# --- the milestone checklist ------------------------------------------------
#
# Goal completion still runs off a weighted checklist; these are the things
# that, if they all happened, would mean the summer worked. Sections match the
# category names above so the two views line up.

# track key -> [(section, name, kind, weight)]
MILESTONES: dict[str, list[tuple[str, str, str, float]]] = {
    "flolabs": [
        ("IoT", "Understand the CAIPO hardware architecture", "skill", 1),
        ("IoT", "Understand the CAIPO software stack", "skill", 1),
        ("IoT", "CAIPO system understanding document", "output", 3),
        ("Robotics", "Mini desktop robot architecture", "skill", 1),
        ("Robotics", "Motors, sensors and control loop", "skill", 1),
        ("Robotics", "Robotics system documentation", "output", 3),
        ("Automation", "Ship one new workflow", "output", 3),
        ("Automation", "Improve an existing workflow", "output", 2),
        ("GTM", "Publish one video", "output", 2),
        ("GTM", "Write one script", "output", 1),
        ("GTM", "One technical post", "output", 1),
    ],
    "pcb": [
        ("Learning principles", "Schematic design", "skill", 1),
        ("Learning principles", "Component selection", "skill", 1),
        ("Learning principles", "Datasheet analysis", "skill", 1),
        ("Learning principles", "Footprint creation", "skill", 1),
        ("Learning principles", "PCB layout", "skill", 1),
        ("Learning principles", "Routing techniques", "skill", 1),
        ("Learning principles", "Design rule checking", "skill", 1),
        ("Learning principles", "Gerber generation", "skill", 1),
        ("Learning principles", "Power management and regulation", "skill", 1),
        ("Learning principles", "Communication protocols", "skill", 1),
        ("Exploring projects to make", "Shortlist a robotics board", "output", 1),
        ("Exploring projects to make", "Shortlist a UAV board", "output", 1),
        ("Exploring projects to make", "Shortlist an AI or CV board", "output", 1),
    ],
    "uav": [
        ("Config", "Flight controller fully configured", "skill", 2),
        ("Config", "Tuning pass done", "skill", 1),
        ("Config", "Telemetry and FPV working", "skill", 1),
        ("Practice flying", "Ten flight sessions", "habit", 2),
        ("Practice flying", "First confident manual flight", "skill", 2),
        ("Meeting", "Regular attendance at team meetings", "habit", 1),
    ],
    "income": [
        ("Build value", "Portfolio or profile live", "output", 2),
        ("Find opportunities", "Five applications sent", "habit", 1),
        ("Find opportunities", "Network with professionals", "habit", 1),
        ("In person", "Complete one in-person build", "output", 2),
        ("Remote", "Complete one remote build", "output", 2),
        ("Convert", "Land one paid engagement", "output", 3),
    ],
    "ethioxplore": [
        ("Meeting", "Attend or lead the regular meetings", "habit", 1),
        ("Building", "Other technical contribution", "output", 2),
        ("Business plan", "Write one section of the business plan", "output", 2),
    ],
    "club": [
        ("Meeting", "Regular attendance", "habit", 1),
        ("Project", "Ship an AI project", "output", 3),
        ("Project", "Ship a robotics project", "output", 3),
        ("Project", "Ship a computer vision project", "output", 3),
        ("Research", "One research write-up", "output", 2),
    ],
    "personal": [
        ("Travel", "Plan one trip properly", "output", 1),
        ("Travel", "Take one trip", "output", 2),
        ("Book club", "Attend the meetings", "habit", 1),
        ("Book club", "Write reflections", "habit", 1),
        ("Hobbies", "Pick up one new hobby skill", "skill", 1),
        ("Hobbies", "Keep it up weekly", "habit", 1),
    ],
}

# track key -> [(name, category, difficulty, weight)]
PROJECTS: dict[str, list[tuple[str, str, str, float]]] = {
    "pcb": [
        ("Robotics board", "Robotics", "Intermediate", 3),
        ("UAV board", "UAV", "Advanced", 3),
        ("AI or CV IoT board", "IoT", "Intermediate", 3),
    ],
    "ethioxplore": [
        ("3D asset pack for EthioXplore", "3D", "Intermediate", 3),
    ],
}

BOOKS = ["July", "August", "September"]
