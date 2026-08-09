"""Общие модели. Их наполняют три независимых источника, см. README:

* threads.py   — DiscussionTools: структура треда глазами самого движка;
* revisions.py — история правок из реплик: кто, когда, в какой секции;
* parse.py     — разбор вики-текста, запасной путь для дампов.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


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

    @property
    def signed(self) -> bool:
        return self.author is not None and self.ts is not None


@dataclass
class Nomination:
    title: str
    heading_raw: str
    struck: bool
    comments: list[Comment] = field(default_factory=list)
    #: страница, с которой номинация транклюдирована (англовики: одна страница на номинацию)
    source_page: str | None = None
    dt_id: str | None = None

    @property
    def participants(self) -> set[str]:
        return {c.author for c in self.comments if c.author and not c.is_bot}

    @property
    def opened_at(self) -> datetime | None:
        stamps = [c.ts for c in self.comments if c.ts]
        return min(stamps) if stamps else None

    @property
    def closed_at(self) -> datetime | None:
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
