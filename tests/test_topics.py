"""Снимок P31/P106 по элементу Викиданных: лучший ранг, нарезка по 50, ошибки не роняют день,
снимки переезжают на новые id номинаций после purge."""

from app.core import pipeline, revisions, topics
from app.db import connect
from app.models import Nomination, PageRef


def _snak(q, rank="normal"):
    return {"mainsnak": {"datavalue": {"value": {"id": q}}}, "rank": rank}


class _WD:
    """Отдаёт только запрошенные id — как настоящий wbgetentities."""

    def __init__(self, entities, error=None):
        self.entities, self.error, self.calls = entities, error, []

    def get(self, **params):
        self.calls.append(params)
        if self.error:
            return {"error": self.error}
        ids = params["ids"].split("|")
        return {"entities": {q: self.entities.get(q, {"id": q, "missing": ""}) for q in ids}}


ENT = {
    "Q1": {"claims": {
        "P31": [_snak("Q5"), _snak("Q5"), _snak("Q215627", "deprecated")],
        "P106": [_snak("Q43845"), {"mainsnak": {"snaktype": "novalue"}, "rank": "normal"}],
    }},
    "Q2": {"claims": {"P31": [_snak("Q4830453"), _snak("Q891723", "preferred")]}},
}


def test_claims_best_rank_and_missing():
    rows = [
        (0, "Иванов", "category", "Предприниматели"),
        (0, "Иванов", "wikibase_item", "Q1"),
        (0, "Ромашка", "wikibase_item", "Q2"),
        (0, "Удалённая", "wikibase_item", "Q3"),
    ]
    wd = _WD(ENT)
    assert topics.claims(rows, wd) == [
        (0, "Иванов", "P31", "Q5"),
        (0, "Иванов", "P106", "Q43845"),
        (0, "Ромашка", "P31", "Q891723"),   # preferred вытесняет normal
    ]
    assert wd.calls == [{"action": "wbgetentities", "ids": "Q1|Q2|Q3", "props": "claims"}]


def test_claims_batches_of_50_with_matching_ids():
    rows = [(0, f"T{i}", "wikibase_item", f"Q{i}") for i in range(60)]
    wd = _WD({f"Q{i}": {"claims": {"P31": [_snak("Q5")]}} for i in range(60)})
    got = topics.claims(rows, wd)
    assert len(got) == 60 and len(wd.calls) == 2
    assert sorted(q for c in wd.calls for q in c["ids"].split("|")) == sorted(f"Q{i}" for i in range(60))


def test_claims_error_response_and_exception_give_empty(caplog):
    rows = [(0, "X", "wikibase_item", "Q1")]
    assert topics.claims(rows, _WD(ENT, error={"code": "no-such-entity", "info": "bad id"})) == []
    assert "no-such-entity" in caplog.text

    class _Broken:
        def get(self, **params):
            raise RuntimeError("wikidata down")

    assert topics.claims(rows, _Broken()) == []
    assert "wikidata down" in caplog.text
    assert topics.claims([(0, "X", "category", "Y")], _Broken()) == []


class _Wiki:
    def paged(self, **params):
        yield {"query": {"pages": [{"title": "Ромашка", "categories": [{"title": "Категория:Компании"}],
                                    "pageprops": {"wikibase_item": "Q2"}}]}}


def test_snapshot_appends_claims_to_categories(monkeypatch):
    from app import wikis

    spec = wikis.get("ruwiki")
    monkeypatch.setattr(revisions, "replicas_available", lambda: False)
    monkeypatch.setattr(topics, "wikidata_api", lambda: _WD(ENT))
    got = topics.snapshot(spec, [(0, "Ромашка")], api=_Wiki())
    assert got == [(0, "Ромашка", "category", "Компании"), (0, "Ромашка", "wikibase_item", "Q2"),
                   (0, "Ромашка", "P31", "Q891723")]


def test_store_topics_carries_snapshot_to_new_nomination_id(monkeypatch):
    from app import wikis

    spec = wikis.get("ruwiki")
    db = connect(":memory:")
    db.init_schema()
    # старый снимок (статья уже удалена — новый снимок пуст) висит на номинации 1
    db.execute("INSERT INTO topics VALUES (1, 'ruwiki', 0, 'Ромашка', 'P31', 'Q4830453', '2026-10-01')")
    monkeypatch.setattr(topics, "snapshot", lambda spec, refs, api=None, wikidata=None: [])
    nom = Nomination(title="Ромашка", heading_raw="Ромашка", struck=False)
    nom.pages = [PageRef(ns=0, title="Ромашка", resolved_by="test")]
    assert pipeline.store_topics(db, spec, [nom], [7], api=None) == (0, 0)
    rows = db.execute("SELECT nomination_id, source, value FROM topics ORDER BY nomination_id").fetchall()
    assert [tuple(r) for r in rows] == [(1, "P31", "Q4830453"), (7, "P31", "Q4830453")]
