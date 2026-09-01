"""Витрина: агрегаты и HTML собираются на пустой и на минимальной базе."""

from __future__ import annotations

import datetime as dt

from app import page, report, wikis
from app.db import connect


def _db():
    db = connect(":memory:")
    db.init_schema()
    return db


def test_report_on_empty_db_renders():
    db = _db()
    rep = report.build(db, [wikis.get("ruwiki"), wikis.get("enwiki")])
    assert rep["wikis"]["ruwiki"]["empty"]
    html = page.render(rep)
    assert "talk-snapshots" in html and "данных ещё нет" in html


def test_lifecycle_separates_outcome_from_state():
    db = _db()
    today = dt.date(2026, 8, 31)
    old = (today - dt.timedelta(days=40)).isoformat()
    fresh = (today - dt.timedelta(days=3)).isoformat()
    rows = [
        # (id, day, title, page_state, outcome_kind)
        (1, old, "Удалённая", "deleted", "delete"),
        (2, old, "Оставленная", "exists", "keep"),
        (3, old, "Висящая", "exists", None),
        (4, fresh, "Свежая", "exists", None),
        (5, old, "Оставили и снесли", "deleted", "keep"),
    ]
    db.execute("INSERT INTO pages (id, wiki, title, day, fetched_at) VALUES (1, 'ruwiki', 'p', ?, 'x')", (old,))
    for nid, day, title, state, kind in rows:
        db.execute("INSERT INTO nominations (id, page_id, wiki, day, title, struck, n_comments, kind) "
                   "VALUES (?, 1, 'ruwiki', ?, ?, 0, 2, 'single')", (nid, day, title))
        db.execute("INSERT INTO nomination_pages (nomination_id, wiki, ns, title, resolved_by) VALUES (?, 'ruwiki', 0, ?, 't')",
                   (nid, title))
        db.execute("INSERT INTO page_state (wiki, ns, title, state, deleted_at, reason_class, checked_at) "
                   "VALUES ('ruwiki', 0, ?, ?, ?, 'discussion', 'x')",
                   (title, state, f"{old}T10:00:00+00:00" if state == "deleted" else None))
        if kind:
            db.execute("INSERT INTO discussion_outcome (nomination_id, wiki, page, kind, closer, source, raw) "
                       "VALUES (?, 'ruwiki', '', ?, 'Closer', 'section', '')", (nid, kind))
        db.execute("INSERT INTO comments (nomination_id, wiki, idx, author, ts, depth, is_outcome, is_bot, text) "
                   "VALUES (?, 'ruwiki', 0, 'Someone', ?, 0, 0, 0, 'x')", (nid, f"{day}T12:00:00+00:00"))
    db.commit()
    W = report.build_wiki(db, wikis.get("ruwiki"), today=today)
    assert W["lifecycle_total"] == {"deleted": 2, "kept": 1, "hanging": 1, "discussing": 1}
    assert W["outcome_kinds"] == {"delete": 1, "keep": 2}
    assert W["deletion_delay"] == {"<1d": 2}
    assert W["top_participants"][0]["user"] == "Someone"
    html = page.render({"generated": "now", "wikis": {"ruwiki": W}})
    assert "Оставленная" not in html  # витрина — агрегаты, не список статей
    assert "оставлена" in html and "висит без итога" in html
