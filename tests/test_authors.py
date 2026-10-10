"""Снимок авторов: агрегация по правкам, боты помечены, запись в page_authors обновляется без дублей."""

from datetime import UTC, datetime

from app import wikis
from app.core import authors, pipeline, revisions
from app.db import connect
from app.models import Nomination, PageRef, Revision


def _rev(i, actor, delta, day):
    return Revision(rev_id=i, page_title="Ромашка", wiki="ruwiki", actor=actor,
                    ts=datetime(2026, 10, day, tzinfo=UTC), section=None, summary="", size_delta=delta)


REVS = [_rev(1, "Автор", 3000, 1), _rev(2, "KrBot", 10, 2), _rev(3, "Автор", -200, 3),
        _rev(4, "Правщик", 120, 4), _rev(5, "", 5, 5)]


def test_snapshot_aggregates_per_user(monkeypatch):
    spec = wikis.get("ruwiki")
    seen = []
    monkeypatch.setattr(revisions, "fetch", lambda s, title, api=None: seen.append(title) or REVS)
    got = {a.user: a for a in authors.snapshot(spec, [(0, "Ромашка")], api=None)}
    assert seen == ["Ромашка"]
    assert set(got) == {"Автор", "KrBot", "Правщик"}          # пустой актор отброшен
    assert (got["Автор"].edits, got["Автор"].bytes_added) == (2, 3000)   # минус не вычитается
    assert got["Автор"].first_ts.day == 1 and got["Автор"].last_ts.day == 3
    assert got["KrBot"].is_bot and not got["Автор"].is_bot


def test_store_authors_upserts(monkeypatch):
    spec = wikis.get("ruwiki")
    db = connect(":memory:")
    db.init_schema()
    monkeypatch.setattr(revisions, "fetch", lambda s, title, api=None: REVS)
    nom = Nomination(title="Ромашка", heading_raw="Ромашка", struck=False)
    nom.pages = [PageRef(ns=0, title="Ромашка", resolved_by="test")]
    assert pipeline.store_authors(db, spec, [nom, nom], api=None) == 3
    monkeypatch.setattr(revisions, "fetch", lambda s, title, api=None: REVS + [_rev(6, "Автор", 50, 6)])
    pipeline.store_authors(db, spec, [nom], api=None)
    rows = db.execute("SELECT user, edits, bytes_added, is_bot FROM page_authors ORDER BY user").fetchall()
    assert [tuple(r) for r in rows] == [("KrBot", 1, 10, 1), ("Автор", 3, 3050, 0), ("Правщик", 1, 120, 0)]
