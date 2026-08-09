"""Тесты слоя 1 на реальных страницах обсуждений.

Главный инвариант: каждая метка времени на странице либо становится репликой,
либо попадает в счётчик отфильтрованного. Молча терять подписи нельзя — иначе
граф участия окажется неполным, а мы об этом не узнаем.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app import wikis
from app.parse import parse_page

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

CASES = [
    ("ru_ku_2026-07-01.wikitext", "ruwiki", "Википедия:К удалению/1 июля 2026", 21),
    ("ru_ku_2024-03-15.wikitext", "ruwiki", "Википедия:К удалению/15 марта 2024", 22),
    ("en_afd_syria.wikitext", "enwiki", "5 September 2016 Syria bombings", 1),
    ("en_afd_stepper.wikitext", "enwiki", "3rd Ward Stepper", 1),
]


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("fname,dbname,title,expected_noms", CASES)
def test_every_timestamp_accounted_for(fname, dbname, title, expected_noms):
    text = load(fname)
    wiki = wikis.get(dbname)
    stats: dict[str, int] = {}
    noms = parse_page(text, wiki, title, stats=stats)

    assert len(noms) == expected_noms
    parsed = sum(len(n.comments) for n in noms)
    timestamps = len(wiki.timestamp_re().findall(text))
    assert parsed + sum(stats.values()) == timestamps


@pytest.mark.parametrize("fname,dbname,title,_", CASES)
def test_threading_is_consistent(fname, dbname, title, _):
    noms = parse_page(load(fname), wikis.get(dbname), title)
    for nom in noms:
        for c in nom.comments:
            assert c.parent is None or c.parent < c.idx
            if c.parent is not None:
                assert nom.comments[c.parent].depth < c.depth


@pytest.mark.parametrize("fname,dbname,title,_", CASES)
def test_comments_have_author_and_time(fname, dbname, title, _):
    noms = parse_page(load(fname), wikis.get(dbname), title)
    comments = [c for n in noms for c in n.comments]
    assert comments
    assert all(c.ts is not None for c in comments)
    # неподписанные реплики бывают, но их должно быть мало
    unsigned = [c for c in comments if not c.author]
    assert len(unsigned) / len(comments) < 0.1
    assert all(c.text for c in comments), "реплика не должна вычищаться в пустоту"


def test_ru_thread_chain():
    """Ветка про Кармели — восемь уровней вложенности подряд, живой спор."""
    noms = parse_page(load(CASES[0][0]), wikis.RUWIKI, CASES[0][2])
    nom = next(n for n in noms if "Кармели" in n.title)
    assert "Schrike" in nom.participants
    assert "~2026-35347-60" in nom.participants, "временный аккаунт должен опознаваться"
    chain = [c for c in nom.comments if c.depth >= 5]
    assert chain, "глубокая ветка должна сохраниться"
    assert any(c.author == "Korolev Alexandr" for c in chain)


def test_ru_outcome_detected():
    noms = parse_page(load(CASES[0][0]), wikis.RUWIKI, CASES[0][2])
    with_outcome = [n for n in noms if any(c.is_outcome for c in n.comments)]
    assert with_outcome, "на дневной странице обязаны быть подведённые итоги"
    for nom in with_outcome:
        outcomes = [c for c in nom.comments if c.is_outcome]
        # итог всегда позже открытия номинации
        assert outcomes[0].ts >= nom.comments[0].ts


def test_en_votes_parsed():
    noms = parse_page(load("en_afd_syria.wikitext"), wikis.ENWIKI, "5 September 2016 Syria bombings")
    votes = [c.vote for n in noms for c in n.comments if c.vote]
    assert votes.count("Merge") >= 3


def test_ru_has_almost_no_formal_votes():
    """Ради этого и сделан плагинный слой 2: в рувики голосования нет."""
    noms = parse_page(load(CASES[0][0]), wikis.RUWIKI, CASES[0][2])
    comments = [c for n in noms for c in n.comments]
    votes = [c for c in comments if c.vote]
    assert len(votes) / len(comments) < 0.05


def test_bots_flagged_not_dropped():
    noms = parse_page(load("ru_ku_2024-03-15.wikitext"), wikis.RUWIKI, CASES[1][2])
    bots = [c for n in noms for c in n.comments if c.is_bot]
    assert bots, "ботовые реплики помечаются, а не выкидываются"
    assert all(c.author not in n.participants for n in noms for c in bots if c in n.comments)


def test_signature_not_left_in_text():
    """Подпись срезана — но пинг в начале реплики это не подпись, его трогать нельзя."""
    noms = parse_page(load(CASES[0][0]), wikis.RUWIKI, CASES[0][2])
    tail = re.compile(r"\[\[\s*(?:У|ОУ|Участник|Обсуждение участника)\s*:[^\]]*\]\]\s*[)\s]*$")
    pinged = 0
    for n in noms:
        for c in n.comments:
            if c.author:
                assert not tail.search(c.text), c.text[-120:]
                pinged += bool(re.search(r"^@\[\[\s*У", c.text))
    assert pinged, "пинги коллег в начале реплики должны сохраняться"
