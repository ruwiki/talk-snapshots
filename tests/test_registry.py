"""Инварианты, одинаковые для любого раздела в реестре.

Раздел без фикстуры не считается подключённым: тест ниже это принуждает.
Фикстура — сохранённый ответ DiscussionTools за один день (tests/fixtures/<dbname>/dt_*.json);
рядом может лежать expected.json с ожидаемыми счётчиками — тогда они сверяются точно.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app import wikis
from app.core.threads import build

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def dt_fixtures(dbname: str) -> list[pathlib.Path]:
    return sorted((FIXTURES / dbname).glob("dt_*.json"))


def engine(dbname: str, path: pathlib.Path):
    data = json.loads(path.read_text(encoding="utf-8"))["discussiontoolspageinfo"]
    return build(data.get("threaditemshtml", []), wikis.get(dbname), data.get("transcludedfrom") or {})


@pytest.mark.parametrize("dbname", sorted(wikis.REGISTRY))
def test_every_registered_wiki_has_a_fixture(dbname):
    assert dt_fixtures(dbname), f"{dbname}: нет tests/fixtures/{dbname}/dt_*.json — раздел не подключён"


CASES = [(db, p) for db in sorted(wikis.REGISTRY) for p in dt_fixtures(db)]


@pytest.mark.parametrize("dbname,path", CASES, ids=[f"{d}:{p.stem}" for d, p in CASES])
def test_engine_gives_nominations_with_signed_comments(dbname, path):
    noms = engine(dbname, path)
    assert noms, "движок должен отдать хотя бы одну номинацию"
    comments = [c for n in noms for c in n.comments]
    assert comments
    unsigned = [c for c in comments if c.ts is None or not c.author]
    assert len(unsigned) / len(comments) <= 0.02, f"{len(unsigned)} реплик без автора/времени"
    for n in noms:
        for c in n.comments:
            if c.parent is not None:
                assert 0 <= c.parent < c.idx
                assert n.comments[c.parent].depth < c.depth


@pytest.mark.parametrize("dbname,path", CASES, ids=[f"{d}:{p.stem}" for d, p in CASES])
def test_pages_resolved_for_almost_every_nomination(dbname, path):
    """Номинация без единой найденной страницы — дырка в модели, а не «не найдена»."""
    noms = engine(dbname, path)
    unknown = [n.title for n in noms if n.kind == "unknown"]
    assert len(unknown) / len(noms) <= 0.05, unknown
    for n in noms:
        for p in n.pages:
            assert p.title and ":" not in p.title[:1]
            assert not p.title.startswith(("User", "Участник", "Benutzer"))


@pytest.mark.parametrize("dbname,path", CASES, ids=[f"{d}:{p.stem}" for d, p in CASES])
def test_expected_counts(dbname, path):
    exp_path = path.with_name(path.stem.replace("dt_", "expected_") + ".json")
    if not exp_path.exists():
        pytest.skip("нет expected.json")
    exp = json.loads(exp_path.read_text(encoding="utf-8"))
    noms = engine(dbname, path)
    got = dict(
        nominations=len(noms),
        comments=sum(len(n.comments) for n in noms),
        pages=sum(len(n.pages) for n in noms),
        groups=sum(1 for n in noms if n.kind == "group"),
        not_article=sum(1 for n in noms if n.kind == "not_article"),
        outcomes=sum(len(n.outcomes) for n in noms),
        voted=sum(1 for n in noms for c in n.comments if c.vote),
        bots=sum(1 for n in noms for c in n.comments if c.is_bot),
    )
    for k, v in exp.items():
        assert got[k] == v, f"{k}: ожидалось {v}, получено {got[k]} (всё: {got})"


def test_core_has_no_wiki_names():
    """Ядро не ветвится по разделу: ни одного dbname в app/core."""
    core = pathlib.Path(__file__).parent.parent / "app" / "core"
    names = [f'"{d}"' for d in wikis.REGISTRY] + [f"'{d}'" for d in wikis.REGISTRY]
    for f in core.glob("*.py"):
        text = f.read_text(encoding="utf-8")
        for name in names:
            assert name not in text, f"{f.name} упоминает {name}"
