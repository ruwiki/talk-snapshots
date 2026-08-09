"""Слой 1 через DiscussionTools: структуру треда отдаёт сам движок.

Почему не свой парсер: MediaWiki уже умеет сегментировать обсуждение и делает
это точнее. На дневной странице КУ за 1 июля 2026 движок находит 182 реплики
и 40 авторов, самодельный разбор вики-текста — 102. Вложенность приходит
структурно (replies), автор и время — полями, без регулярок по подписям.

Свой парсер остаётся в parse.py как запасной путь для дампов, где вызывать
API на каждую страницу нельзя.
"""

from __future__ import annotations

import html as html_mod
import re
from datetime import datetime

from .api import Api
from .models import Comment, Nomination
from .wikis import Wiki

TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"[ \t ]+")


def html_to_text(fragment: str) -> str:
    text = TAG.sub("", fragment or "")
    text = html_mod.unescape(text)
    return WS.sub(" ", text).strip()


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def fetch_page_threads(
    api: Api, wiki: Wiki, page: str | None = None, oldid: int | None = None
) -> list[Nomination]:
    """Забрать номинации со страницы обсуждений и разложить в модели."""
    params = dict(action="discussiontoolspageinfo", prop="threaditemshtml|transcludedfrom")
    if oldid is not None:
        params["oldid"] = oldid
    else:
        params["page"] = page
    data = api.get(**params).get("discussiontoolspageinfo", {})
    transcluded = data.get("transcludedfrom") or {}
    return _build(data.get("threaditemshtml", []), wiki, transcluded)


def _build(items: list[dict], wiki: Wiki, transcluded: dict) -> list[Nomination]:
    nominations: list[Nomination] = []
    for item in items:
        if item.get("type") != "heading":
            # реплики вне заголовков (шапка страницы) в номинации не входят
            continue
        if item.get("headingLevel") not in (0, wiki.nomination_level):
            continue
        nominations.append(_nomination(item, wiki, transcluded))
    return nominations


def _nomination(heading: dict, wiki: Wiki, transcluded: dict) -> Nomination:
    raw = html_to_text(heading.get("html", "")) or (heading.get("name") or "")
    nom = Nomination(
        title=raw.strip(),
        heading_raw=heading.get("html", ""),
        struck="<s>" in (heading.get("html") or "").lower(),
        dt_id=heading.get("id"),
        source_page=_source_page(heading, transcluded),
    )
    _collect(heading.get("replies", []), nom, wiki, depth=0, parent=None)
    return nom


def _source_page(heading: dict, transcluded: dict) -> str | None:
    """Откуда транклюдирована номинация.

    В англовики дневной лог только подключает подстраницы-номинации, и без
    этого поля непонятно, к какой из них относится реплика.
    """
    src = transcluded.get(heading.get("id"))
    if isinstance(src, str):
        return src
    for reply in heading.get("replies", []):
        src = transcluded.get(reply.get("id"))
        if isinstance(src, str):
            return src
    return None


def _collect(
    items: list[dict],
    nom: Nomination,
    wiki: Wiki,
    depth: int,
    parent: int | None,
    in_outcome: bool = False,
) -> None:
    vote_re = wiki.vote_plain_re()
    for item in items:
        if item.get("type") == "heading":
            # подзаголовок внутри номинации: «Итог» в рувики
            name = html_to_text(item.get("html", "")) or (item.get("name") or "")
            outcome = in_outcome or name.strip() in wiki.outcome_headings
            _collect(item.get("replies", []), nom, wiki, depth, parent, outcome)
            continue

        author = item.get("author")
        text = html_to_text(item.get("html", ""))
        comment = Comment(
            idx=len(nom.comments),
            author=author,
            ts=_ts(item.get("timestamp")),
            depth=depth,
            parent=parent,
            text=text,
            dt_id=item.get("id"),
            is_outcome=in_outcome,
            is_bot=bool(author and author in wiki.known_bots),
        )
        if vote_re:
            m = vote_re.match(text)
            if m:
                comment.vote = m.group(1).capitalize()
        nom.comments.append(comment)
        _collect(item.get("replies", []), nom, wiki, depth + 1, comment.idx, in_outcome)
