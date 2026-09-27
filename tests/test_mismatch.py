"""Несовпадения обсуждение ↔ журнал: классы находятся, страница рендерится со ссылками."""

from __future__ import annotations

from urllib.parse import quote

from app import page, report, wikis
from app.core import mismatch
from app.db import connect


def _db():
    db = connect(":memory:")
    db.init_schema()
    db.execute("INSERT INTO pages (id, wiki, title, day, fetched_at) "
               "VALUES (1, 'ruwiki', 'Википедия:К удалению/24 сентября 2026', '2026-09-24', 'x')")
    rows = [
        # (id, title, page_state, outcome, closed_at, struck)
        (1, "Удалена без итога", "deleted", None, None, 0),
        (2, "Удалена, итог есть", "deleted", "delete", "2026-09-25", 0),
        (3, "Оставили и снесли", "deleted", "keep", "2026-09-25", 0),
        (4, "Итог удалить, живёт", "exists", "delete", "2026-09-25", 0),
        (5, "Редирект не сделан", "exists", "redirect", "2026-09-25", 0),
        (6, "Нигде нет", "missing", None, None, 0),
        (7, "Зачёркнута и удалена", "deleted", None, None, 1),
        (8, "Всё сходится", "exists", "keep", "2026-09-25", 0),
    ]
    for nid, title, state, kind, closed_at, struck in rows:
        db.execute("INSERT INTO nominations (id, page_id, wiki, day, title, struck, closed_at, n_comments, kind) "
                   "VALUES (?, 1, 'ruwiki', '2026-09-24', ?, ?, ?, 1, 'single')", (nid, title, struck, closed_at))
        db.execute("INSERT INTO nomination_pages (nomination_id, wiki, ns, title, resolved_by) "
                   "VALUES (?, 'ruwiki', 0, ?, 't')", (nid, title))
        if state != "missing":
            db.execute("INSERT INTO page_state (wiki, ns, title, state, deleted_at, reason_class, checked_at) "
                       "VALUES ('ruwiki', 0, ?, ?, ?, 'speedy', 'x')",
                       (title, state, "2026-09-24T10:00:00+00:00" if state == "deleted" else None))
        if kind:
            db.execute("INSERT INTO discussion_outcome (nomination_id, wiki, page, kind, closer, source, raw) "
                       "VALUES (?, 'ruwiki', '', ?, 'Closer', 'section', '')", (nid, kind))
    db.execute("INSERT INTO nominations (id, page_id, wiki, day, title, struck, n_comments, kind) "
               "VALUES (9, 1, 'ruwiki', '2026-09-24', 'Без страниц', 0, 1, 'unknown')")
    db.commit()
    return db


def test_classes_are_found():
    db = _db()
    cases, counts = mismatch.find(db, wikis.get("ruwiki"))
    assert counts == {"deleted_open": 1, "kept_deleted": 1, "delete_exists": 1, "redirect_exists": 1,
                      "no_pages": 1, "missing": 1}
    c = cases["deleted_open"][0]
    assert c.title == "Удалена без итога" and c.reason == "speedy"
    q = lambda x: quote(x, safe=":/()!,'")  # noqa: E731
    assert c.discussion_url == ("https://ru.wikipedia.org/wiki/" + q("Википедия:К_удалению/24_сентября_2026")
                                + "#" + q("Удалена_без_итога"))
    assert c.page_url == "https://ru.wikipedia.org/wiki/" + q("Удалена_без_итога")
    assert "Special:Log&type=delete&page=" + q("Удалена_без_итога") in c.log_url
    assert cases["no_pages"][0].nomination == "Без страниц"


def test_limit_zero_keeps_counts():
    db = _db()
    cases, counts = mismatch.find(db, wikis.get("ruwiki"), limit=0)
    assert sum(counts.values()) == 6 and all(not v for v in cases.values())


def test_page_renders_with_links_and_report_carries_counts():
    db = _db()
    spec = wikis.get("ruwiki")
    rep = report.build(db, [spec])
    assert rep["wikis"]["ruwiki"]["mismatches"]["deleted_open"] == 1
    html = page.render_wiki("ruwiki", rep["wikis"]["ruwiki"], rep, "ru")
    assert "/wiki/ruwiki/mismatches" in html and "Несовпадения обсуждений и журналов: 6" in html
    cases, counts = mismatch.find(db, spec)
    html = page.render_mismatches("ruwiki", rep["wikis"]["ruwiki"], rep, "ru", cases, counts)
    assert quote("Удалена_без_итога") in html and "type=delete" in html and ">Удалена без итога<" in html
    assert "Всё сходится" not in html


def test_overview_links_mismatch_counts():
    db = _db()
    rep = report.build(db, [wikis.get("ruwiki")])
    html = page.render_overview(rep)
    assert "<a href='/wiki/ruwiki/mismatches'>6</a>" in html
