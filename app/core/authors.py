"""Снимок существенных авторов статьи в момент номинации.

После удаления история статьи недоступна никому, кроме администраторов, а звать
в обсуждение удаления надо именно тех, кто статью писал (en: WP:APPNOTE —
уведомление существенных авторов разрешено; ru: номинатор обязан уведомить
автора). Снимок — та же джоба и тот же момент, что у категорий и Викиданных.

Источник — история правок страницы (реплика на Toolforge, API снаружи — как в
`revisions.py`; через API это первые 500 правок). Хранится по странице, не по
номинации: авторы у статьи одни, сколько бы раз её ни номинировали.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..api import Api
from . import revisions as revs


@dataclass(frozen=True)
class Author:
    ns: int
    title: str
    user: str
    edits: int
    bytes_added: int
    first_ts: datetime
    last_ts: datetime
    is_bot: bool


def snapshot(spec, refs: list[tuple[int, str]], api: Api | None = None) -> list[Author]:
    """refs: (ns, title) страниц номинаций. → по одной строке на (страница, автор)."""
    from .state import _full_title

    out: list[Author] = []
    for ns, title in refs:
        rows = revs.fetch(spec, _full_title(spec, ns, title), api)
        agg: dict[str, list] = {}
        for r in rows:
            if not r.actor:
                continue
            a = agg.setdefault(r.actor, [0, 0, r.ts, r.ts])
            a[0] += 1
            a[1] += max(r.size_delta, 0)
            a[2] = min(a[2], r.ts)
            a[3] = max(a[3], r.ts)
        for user, (edits, added, first, last) in agg.items():
            out.append(Author(ns, title, user, edits, added, first, last,
                              user in spec.locale.known_bots or user.lower().endswith("bot")))
    return out
