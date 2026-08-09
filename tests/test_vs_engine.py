"""Сколько запасной парсер проигрывает движку — на одних и тех же страницах.

Тест не требует сети: рядом с вики-текстом лежит сохранённый ответ
DiscussionTools для той же страницы. Смысл не в том, чтобы догнать движок,
а в том, чтобы знать величину разрыва и заметить, если он вырастет.
"""

from __future__ import annotations

import json
import pathlib

from app import wikis
from app.parse import parse_page
from app.threads import _build

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def engine_nominations(dt_file: str, wiki):
    data = json.loads((FIXTURES / dt_file).read_text(encoding="utf-8"))
    info = data["discussiontoolspageinfo"]
    return _build(info.get("threaditemshtml", []), wiki, info.get("transcludedfrom") or {})


def test_ru_fallback_covers_most_of_engine():
    wiki = wikis.RUWIKI
    mine = parse_page(
        (FIXTURES / "ru_ku_2026-07-01.wikitext").read_text(encoding="utf-8"),
        wiki,
        "Википедия:К удалению/1 июля 2026",
    )
    theirs = engine_nominations("dt_ru_ku_2026-07-01.json", wiki)

    assert len(mine) == len(theirs), "число номинаций должно совпадать"

    mine_comments = sum(len(n.comments) for n in mine)
    their_comments = sum(len(n.comments) for n in theirs)
    coverage = mine_comments / their_comments
    # запасной путь заведомо беднее: он не видит транклюзий и нестандартных подписей
    assert 0.7 <= coverage <= 1.05, f"покрытие {coverage:.0%} ({mine_comments}/{their_comments})"


def test_authors_agree_on_the_core():
    """Ядро участников должно совпадать: расхождения допустимы только по краям."""
    wiki = wikis.RUWIKI
    mine = parse_page(
        (FIXTURES / "ru_ku_2026-07-01.wikitext").read_text(encoding="utf-8"),
        wiki,
        "Википедия:К удалению/1 июля 2026",
    )
    theirs = engine_nominations("dt_ru_ku_2026-07-01.json", wiki)

    mine_authors = {a for n in mine for a in n.participants}
    their_authors = {a for n in theirs for a in n.participants}
    common = mine_authors & their_authors
    assert len(common) / len(their_authors) > 0.85


def test_en_engine_gives_votes_and_source_pages():
    wiki = wikis.ENWIKI
    noms = engine_nominations("dt_en_afd_syria.json", wiki)
    assert noms
    comments = [c for n in noms for c in n.comments]
    assert sum(1 for c in comments if c.vote == "Merge") >= 3
    assert all(c.ts is not None for c in comments)
