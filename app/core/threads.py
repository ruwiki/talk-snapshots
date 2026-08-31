"""Слой 1 через DiscussionTools: структуру треда отдаёт сам движок.

Почему не свой парсер: MediaWiki уже умеет сегментировать обсуждение и делает
это точнее. На дневной странице КУ за 1 июля 2026 движок находит 182 реплики
и 40 авторов, самодельный разбор вики-текста — 102. Вложенность приходит
структурно (replies), автор и время — полями, без регулярок по подписям.

Подзаголовки внутри номинации движок тоже отдаёт как вложенные элементы.
Что они значат — решает спек: подсекция итога, «по всем», страница групповой
номинации или просто фаза обсуждения (it: «Votazione…» → «Mantenere»).
"""

from __future__ import annotations

import html as html_mod
import re
from dataclasses import dataclass, replace
from datetime import datetime

from ..api import Api
from ..models import Comment, Nomination
from .pages import Subsections, _ref, links_in

TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"[ \t ]+")
STRUCK = re.compile(r"<(?:s|strike|del)\b", re.IGNORECASE)


def html_to_text(fragment: str) -> str:
    text = TAG.sub("", fragment or "")
    text = html_mod.unescape(text)
    return WS.sub(" ", text).replace("\xa0", " ").strip()


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def fetch_page_threads(
    api: Api, spec, page: str | None = None, oldid: int | None = None
) -> list[Nomination]:
    """Забрать номинации со страницы обсуждений и разложить в модели."""
    params = dict(action="discussiontoolspageinfo", prop="threaditemshtml|transcludedfrom")
    if oldid is not None:
        params["oldid"] = oldid
    else:
        params["page"] = page
    data = api.get(**params).get("discussiontoolspageinfo", {})
    transcluded = data.get("transcludedfrom") or {}
    return build(data.get("threaditemshtml", []), spec, transcluded)


def build(items: list[dict], spec, transcluded: dict) -> list[Nomination]:
    """Верхний уровень: номинации — заголовки уровня nomination_level.

    Движок перечисляет заголовки и плоско, и вложенно; берём плоский список
    нужного уровня, а подзаголовки — из вложенности внутри каждой номинации.
    """
    nominations: list[Nomination] = []
    for item in items:
        if item.get("type") != "heading":
            continue
        if item.get("headingLevel") not in (0, spec.nomination_level):
            continue
        nominations.append(_nomination(item, spec, transcluded))
    return nominations


@dataclass(frozen=True)
class _Ctx:
    page: str | None = None
    section: str | None = None
    in_outcome: bool = False


def _nomination(heading: dict, spec, transcluded: dict) -> Nomination:
    html = heading.get("html", "") or ""
    nom = Nomination(
        title=(html_to_text(html) or (heading.get("name") or "")).strip(),
        heading_raw=html,
        struck=bool(STRUCK.search(html)),
        dt_id=heading.get("id"),
        source_page=_source_page(heading, transcluded),
    )
    _collect(heading.get("replies", []), nom, spec, depth=0, parent=None, ctx=_Ctx())
    nom.pages = spec.resolve_pages(nom)
    spec.outcome.apply(nom, spec, None)
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


def _subheading_ctx(item: dict, nom: Nomination, spec, ctx: _Ctx) -> _Ctx:
    level = item.get("headingLevel") or 0
    html = item.get("html", "") or ""
    text = html_to_text(html) or (item.get("name") or "")
    text = text.strip()
    nom.subheadings.append((level, text, html))
    if text in spec.outcome.section_names or ctx.in_outcome:
        return replace(ctx, in_outcome=True, section=text)
    if text in spec.common_headings:
        return _Ctx(page=None, section=text)
    groups = any(isinstance(p, Subsections) for p in spec.pages)
    if groups and level == spec.nomination_level + 1:
        links = links_in(html)
        page = _ref(links[0] if links else text, spec, "subsection").title
        return _Ctx(page=page, section=text)
    return replace(ctx, section=text)


def _collect(
    items: list[dict], nom: Nomination, spec, depth: int, parent: int | None, ctx: _Ctx
) -> None:
    for item in items:
        if item.get("type") == "heading":
            _collect(item.get("replies", []), nom, spec, depth, parent,
                     _subheading_ctx(item, nom, spec, ctx))
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
            is_outcome=ctx.in_outcome,
            is_bot=bool(author and author in spec.locale.known_bots),
            page=ctx.page,
            section=ctx.section,
        )
        comment.vote = spec.stance.of_comment(comment, ctx.section)
        nom.comments.append(comment)
        _collect(item.get("replies", []), nom, spec, depth + 1, comment.idx, ctx)
