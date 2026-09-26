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
    html = page.render_overview(rep)
    assert "talk-snapshots" in html
    html = page.render_wiki("ruwiki", rep["wikis"]["ruwiki"], rep, "ru")
    assert "данных ещё нет" in html


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
    rep = {"generated": "now", "wikis": {"ruwiki": W}}
    html = page.render_wiki("ruwiki", W, rep, "ru")
    assert "Оставленная" not in html  # витрина — агрегаты, не список статей
    assert "оставлена" in html and "висит без итога" in html
    de = page.render_wiki("ruwiki", W, rep, "de")
    assert "behalten" in de and "ohne Ergebnis" in de
    ov = page.render_overview(rep)
    assert "/wiki/ruwiki" in ov


def test_logs_panel_marks_absent_channels():
    """Канал, которого в вики нет (PROD в рувики), витрина рисует серым, а не пропускает."""
    db = _db()
    rows = [
        ("ruwiki", "2026-07-01", "delete", "article", "discussion", 30),
        ("ruwiki", "2026-07-01", "delete", "article", "speedy", 50),
        ("ruwiki", "2026-07-02", "delete", "user", "speedy", 7),
        ("ruwiki", "2026-07-02", "restore", "article", "-", 2),
        ("ruwiki", "2026-07-02", "move", "article", "-", 9),
        ("enwiki", "2026-07-01", "delete", "article", "prod", 40),
        ("enwiki", "2026-07-01", "delete", "draft", "speedy", 300),
    ]
    db.executemany("INSERT INTO log_counts (wiki, day, kind, ns_group, channel, n) VALUES (?, ?, ?, ?, ?, ?)", rows)
    db.commit()
    rep = report.build(db, [wikis.get("ruwiki"), wikis.get("enwiki")])
    ru, en = rep["wikis"]["ruwiki"]["logs"], rep["wikis"]["enwiki"]["logs"]
    assert ru["delete_channels"]["discussion"] == 30 and ru["delete_ns"]["user"] == 7
    assert "prod" in ru["absent"] and "prod" not in en["absent"]
    assert ru["kinds"] == {"delete": 87, "restore": 2, "move": 9, "protect": 0}
    assert en["delete_ns"]["draft"] == 300 and en["has_draft"]
    html = page.render_wiki("ruwiki", rep["wikis"]["ruwiki"], rep, "ru")
    assert "в этом разделе нет" in html and "по итогу обсуждения" in html
    ov = page.render_overview(rep)
    assert "class='absent'" in ov and "proposed deletion (PROD)" in ov


def test_log_channels_classify():
    en = wikis.get("enwiki").log_channels
    assert en.classify("[[Wikipedia:Articles for deletion/Foo]]") == "discussion"
    assert en.classify("Expired [[WP:PROD|PROD]], concern was: x") == "prod"
    assert en.classify("[[WP:CSD#G13|G13]]: Abandoned draft") == "speedy"
    assert en.classify("[[WP:G5]]: Mass deletion of pages added by X") == "speedy"
    assert en.group(118) == "draft" and en.group(5) == "other"
    ru = wikis.get("ruwiki").log_channels
    assert ru.classify("/*<noinclude>{{к удалению|1=2026-07-16}}") == "discussion"
    assert ru.classify("[[ВП:КБУ#О9]]") == "speedy"
    assert "prod" not in ru.present() and "prod" in wikis.get("dewiki").log_channels.ALL
