"""Стратегии «где записан исход обсуждения».

Исход обсуждения и судьба страницы — разные вещи. Судьбу даёт журнал
удалений (core/state.py, одинаково для всех разделов). Здесь — только то,
что решили люди в самом обсуждении, и это в каждом разделе записано по-своему:
подсекцией «Итог» (ru, uk), суффиксом заголовка «(gelöscht)» (de), шаблоном
закрытия в вики-тексте (zh, en). Стратегия заполняет nom.outcomes и помечает
реплики итога (is_outcome).
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field

from ..models import DiscussionOutcome, Nomination

_MIN = _dt.datetime.min.replace(tzinfo=_dt.UTC)


def _classify(text: str, kinds: dict[str, str]) -> str:
    """Класс исхода — по последнему упоминанию: итог заканчивается решением
    («…источников нет. Удалено»), а начинается с обоснования."""
    best, best_pos = "other", -1
    for pattern, kind in kinds.items():
        for m in re.finditer(pattern, text or "", re.IGNORECASE):
            if m.start() > best_pos:
                best, best_pos = kind, m.start()
    return best


@dataclass(frozen=True)
class NoOutcome:
    """Исход в тексте не ищем — судьба страницы придёт из журнала."""

    section_names: tuple[str, ...] = ()

    def apply(self, nom: Nomination, spec, wikitext: str | None) -> None:
        return None


@dataclass(frozen=True)
class OutcomeSection:
    """Итог — подсекция с одним из известных имён; реплики в ней уже помечены
    движком/парсером как is_outcome. Класс исхода — по первым словам итога."""

    section_names: tuple[str, ...]
    kinds: dict[str, str] = field(default_factory=dict)

    def apply(self, nom: Nomination, spec, wikitext: str | None) -> None:
        by_page: dict[str | None, list] = {}
        for c in nom.comments:
            if c.is_outcome and c.author and not c.is_bot:
                by_page.setdefault(c.page, []).append(c)
        for page, comments in by_page.items():
            last = max(comments, key=lambda c: c.ts or _MIN)
            first = min(comments, key=lambda c: c.ts or _MIN)
            nom.outcomes.append(
                DiscussionOutcome(
                    kind=_classify(first.text, self.kinds),
                    page=page,
                    closer=last.author,
                    closed_at=last.ts,
                    source="section",
                    raw=first.text[:200],
                )
            )


@dataclass(frozen=True)
class HeadingSuffix:
    """Исход вписан в заголовок: «Emily Gretel (gelöscht)»."""

    pattern: str
    kinds: dict[str, str] = field(default_factory=dict)
    section_names: tuple[str, ...] = ()

    def apply(self, nom: Nomination, spec, wikitext: str | None) -> None:
        text = re.sub(r"<[^>]+>", "", nom.heading_raw or "")
        m = re.search(self.pattern, text, re.IGNORECASE)
        if not m:
            return
        raw = m.group(1) if m.groups() else m.group(0)
        nom.outcomes.append(
            DiscussionOutcome(kind=_classify(raw, self.kinds), source="heading", raw=raw)
        )


@dataclass(frozen=True)
class ClosingTemplate:
    """Исход — в шаблоне закрытия в вики-тексте секции: {{delh|結果}}, {{afd top}}.

    Требует вики-текста: конвейер отдаёт его, если стратегия объявила needs_wikitext.
    """

    pattern: str
    kinds: dict[str, str] = field(default_factory=dict)
    section_names: tuple[str, ...] = ()
    needs_wikitext: bool = True

    def apply(self, nom: Nomination, spec, wikitext: str | None) -> None:
        if not wikitext:
            return
        m = re.search(self.pattern, wikitext, re.IGNORECASE | re.DOTALL)
        if not m:
            return
        raw = (m.group(1) if m.groups() else m.group(0)).strip()
        nom.outcomes.append(
            DiscussionOutcome(kind=_classify(raw, self.kinds), source="template", raw=raw[:200])
        )


@dataclass(frozen=True)
class CommentPattern:
    """Исход — реплика с характерной фразой: «議論の結果、削除 に決定しました»,
    «The result was keep». Реплика помечается итогом, её автор — закрывший."""

    pattern: str
    kinds: dict[str, str] = field(default_factory=dict)
    section_names: tuple[str, ...] = ()

    def apply(self, nom: Nomination, spec, wikitext: str | None) -> None:
        rx = re.compile(self.pattern, re.IGNORECASE | re.DOTALL)
        for c in nom.comments:
            m = rx.search(c.text or "")
            if not m:
                continue
            c.is_outcome = True
            raw = (m.group(1) if m.groups() else m.group(0)).strip()
            nom.outcomes.append(
                DiscussionOutcome(
                    kind=_classify(raw, self.kinds), page=c.page, closer=c.author,
                    closed_at=c.ts, source="comment", raw=raw[:200],
                )
            )


