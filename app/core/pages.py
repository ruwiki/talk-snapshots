"""Стратегии «какие страницы обсуждает номинация».

Заголовок номинации в DiscussionTools приходит как HTML: ссылки на статьи
там уже отрисованы (`<a rel="mw:WikiLink" href="./Название" title="Название">`),
поэтому статью не надо угадывать по тексту — она берётся из ссылки. Групповые
номинации перечисляют статьи подзаголовками следующего уровня.
"""

from __future__ import annotations

import html as html_mod
import re
from dataclasses import dataclass
from urllib.parse import unquote

from ..models import Nomination, PageRef

WIKILINK = re.compile(r"<a\b[^>]*\brel=\"mw:WikiLink\"[^>]*>", re.IGNORECASE)
HREF = re.compile(r"\bhref=\"\./([^\"#]+)", re.IGNORECASE)
TITLE_ATTR = re.compile(r"\btitle=\"([^\"]+)\"", re.IGNORECASE)
TAG = re.compile(r"<[^>]+>")


def _text(fragment: str) -> str:
    return html_mod.unescape(TAG.sub("", fragment or "")).replace("\xa0", " ").strip()


def links_in(fragment: str) -> list[str]:
    """Цели вики-ссылок в порядке появления; титульная форма (с пробелами)."""
    out = []
    for m in WIKILINK.finditer(fragment or ""):
        tag = m.group(0)
        t = TITLE_ATTR.search(tag)
        if t:
            out.append(html_mod.unescape(t.group(1)))
            continue
        h = HREF.search(tag)
        if h:
            out.append(unquote(h.group(1)).replace("_", " "))
    return out


def _ref(title: str, spec, resolved_by: str) -> PageRef:
    ns, rest = spec.locale.namespace_of(title)
    return PageRef(ns=ns, title=rest if ns else title.strip(), resolved_by=resolved_by)


@dataclass(frozen=True)
class HeadingLinks:
    """Все вики-ссылки из заголовка номинации; ссылки на участников не считаются."""

    only_articles: bool = False

    def resolve(self, nom: Nomination, spec) -> list[PageRef]:
        refs = []
        for title in links_in(nom.heading_raw):
            ref = _ref(title, spec, "heading-link")
            if ref.ns in (2, 3):
                continue
            if self.only_articles and not ref.is_article:
                continue
            refs.append(ref)
        return refs


@dataclass(frozen=True)
class Subsections:
    """Подзаголовки следующего уровня = страницы (групповая номинация).

    Подзаголовки итогов и «общее по всем» страницами не являются — их имена
    берутся из стратегии исхода и common_headings спека.
    """

    def resolve(self, nom: Nomination, spec) -> list[PageRef]:
        skip = set(spec.outcome.section_names) | set(spec.common_headings)
        level = spec.nomination_level + 1
        refs = []
        for lvl, text, html in nom.subheadings:
            if lvl != level or text in skip:
                continue
            links = links_in(html)
            if links:
                refs.append(_ref(links[0], spec, "subsection"))
            elif text:
                refs.append(_ref(text, spec, "subsection"))
        return refs


@dataclass(frozen=True)
class TitleFromHeading:
    """Текст заголовка как название страницы; суффикс исхода отрезается."""

    strip: str | None = None

    def resolve(self, nom: Nomination, spec) -> list[PageRef]:
        text = _text(nom.heading_raw) or nom.title
        if self.strip:
            text = re.sub(self.strip, "", text).strip()
        text = re.sub(r"^\s*(?:</?s>)?\s*", "", text)
        return [_ref(text, spec, "title")] if text else []


@dataclass(frozen=True)
class TitleAfterPrefix:
    """Страница-номинация «Prefix/Название (2nd nomination)» → «Название»."""

    prefix: str
    strip: str = r"\s*\((?:\d+(?:st|nd|rd|th)|\d+\.ª|2\.|second|third)\s+[^)]*\)\s*$"

    def resolve(self, nom: Nomination, spec) -> list[PageRef]:
        src = nom.source_page or ""
        if not src.startswith(self.prefix):
            return []
        title = src[len(self.prefix):]
        title = re.sub(self.strip, "", title).strip()
        return [_ref(title, spec, "source-page")] if title else []
