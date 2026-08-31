"""Общие модели. Их наполняют три независимых источника, см. README:

* core/threads.py   — DiscussionTools: структура треда глазами самого движка;
* core/revisions.py — история правок из реплик: кто, когда, в какой секции;
* core/parse.py     — разбор вики-текста, запасной путь для дампов.

Номинация ↔ страница — отношение 1:N: групповая номинация обсуждает пачку
статей, и судьба у каждой своя. Поэтому у номинации список PageRef, а у
реплики — страница, под чьим подзаголовком она стоит (None = общее).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class PageRef:
    ns: int
    title: str
    #: как страница найдена: heading-link | subsection | title | source-page
    resolved_by: str = ""

    @property
    def is_article(self) -> bool:
        return self.ns == 0


@dataclass
class Comment:
    idx: int
    author: str | None
    ts: datetime | None
    depth: int
    parent: int | None
    text: str
    #: идентификатор реплики от DiscussionTools, если источник — движок
    dt_id: str | None = None
    is_outcome: bool = False
    vote: str | None = None
    is_bot: bool = False
    #: страница внутри групповой номинации, под чьим подзаголовком стоит реплика
    page: str | None = None
    #: подзаголовок, под которым стоит реплика (для позиций «по секции»)
    section: str | None = None

    @property
    def signed(self) -> bool:
        return self.author is not None and self.ts is not None


@dataclass
class DiscussionOutcome:
    #: delete | keep | redirect | merge | rename | withdrawn | speedy | other
    kind: str
    #: страница, к которой относится; None = общий итог по номинации
    page: str | None = None
    closer: str | None = None
    closed_at: datetime | None = None
    #: откуда взято: section | heading | template
    source: str = ""
    raw: str = ""


@dataclass
class Nomination:
    title: str
    heading_raw: str
    struck: bool
    comments: list[Comment] = field(default_factory=list)
    #: страница, с которой номинация транклюдирована (одна страница на номинацию)
    source_page: str | None = None
    dt_id: str | None = None
    #: подзаголовки внутри номинации: (уровень, текст, html) — сырьё для стратегий
    subheadings: list[tuple[int, str, str]] = field(default_factory=list)
    pages: list[PageRef] = field(default_factory=list)
    outcomes: list[DiscussionOutcome] = field(default_factory=list)

    @property
    def kind(self) -> str:
        """single | group | not_article | unknown."""
        if not self.pages:
            return "unknown"
        articles = [p for p in self.pages if p.is_article]
        if not articles:
            return "not_article"
        return "group" if len(articles) > 1 else "single"

    @property
    def participants(self) -> set[str]:
        return {c.author for c in self.comments if c.author and not c.is_bot}

    @property
    def opened_at(self) -> datetime | None:
        stamps = [c.ts for c in self.comments if c.ts]
        return min(stamps) if stamps else None

    @property
    def closed_at(self) -> datetime | None:
        stamps = [o.closed_at for o in self.outcomes if o.closed_at]
        if stamps:
            return max(stamps)
        stamps = [c.ts for c in self.comments if c.ts and c.is_outcome]
        return max(stamps) if stamps else None


@dataclass
class Revision:
    """Строка истории правок — то, чего нет ни в тексте, ни в API тредов.

    Именно отсюда видно, кто правил чужие реплики, кто удалял и кто подводил
    итог: подпись такие действия не оставляют.
    """

    rev_id: int
    page_title: str
    wiki: str
    actor: str
    ts: datetime
    section: str | None
    summary: str
    tags: tuple[str, ...] = ()
    size_delta: int = 0

    @property
    def added_comment(self) -> bool:
        return "discussiontools-added-comment" in self.tags
