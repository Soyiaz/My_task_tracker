"""Write the taxonomy into a fresh database.

Nothing here is a decision — the decisions live in ``taxonomy.py``. This just
lays them down in the right order and wires the foreign keys.
"""

from __future__ import annotations

from tracker import db, taxonomy


def plant() -> None:
    for key, name, icon, color, goal, share, sort in taxonomy.TRACKS:
        db.execute(
            "INSERT INTO tracks(key, name, icon, color, goal, target_share, sort) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key, name, icon, color, goal, share, sort),
        )

    for key, name, color, sort in taxonomy.DOMAINS:
        db.execute(
            "INSERT INTO domains(key, name, color, target_share, sort) "
            "VALUES (?, ?, ?, ?, ?)",
            (key, name, color, 1 / len(taxonomy.DOMAINS), sort),
        )

    track_ids = {
        r["key"]: r["id"] for r in db.query("SELECT id, key FROM tracks").to_dict("records")
    }

    for track_key, categories in taxonomy.CATEGORIES.items():
        for i, (cat_key, cat_name, requires, domains, subcats) in enumerate(categories):
            cat_id = db.execute(
                "INSERT INTO categories(track_id, key, name, requires, domains, sort) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    track_ids[track_key],
                    cat_key,
                    cat_name,
                    ",".join(requires),
                    ",".join(domains),
                    i,
                ),
            )
            for j, (sub_key, sub_name, sub_domains) in enumerate(subcats):
                db.execute(
                    "INSERT INTO subcategories(category_id, key, name, domains, sort) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (cat_id, sub_key, sub_name, ",".join(sub_domains), j),
                )

    for track_key, rows in taxonomy.MILESTONES.items():
        db.execute_many(
            "INSERT INTO items(track_id, section, name, kind, weight, sort) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (track_ids[track_key], section, name, kind, weight, i)
                for i, (section, name, kind, weight) in enumerate(rows)
            ],
        )

    for track_key, rows in taxonomy.PROJECTS.items():
        db.execute_many(
            "INSERT INTO projects(track_id, name, category, difficulty, weight) "
            "VALUES (?, ?, ?, ?, ?)",
            [(track_ids[track_key], name, cat, diff, w) for name, cat, diff, w in rows],
        )

    db.execute_many(
        "INSERT INTO books(month) VALUES (?)", [(m,) for m in taxonomy.BOOKS]
    )
