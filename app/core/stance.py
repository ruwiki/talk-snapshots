"""Стратегии формальной позиции реплики.

Позиция — не универсальное свойство обсуждения: англовики выделяет её жирным
словом в начале реплики, итальянская — секцией, в которой стоит подпись,
русская не выражает вовсе. Ядро об этом не знает; стратегия отвечает
«какая позиция у этой реплики» или «никакой».
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import Comment


@dataclass(frozen=True)
class NoStance:
    def of_comment(self, comment: Comment, section: str | None) -> str | None:
        return None

    def wikitext_re(self) -> re.Pattern[str] | None:
        return None


@dataclass(frozen=True)
class VoteWords:
    """Жирное слово-маркер в начале реплики: Keep / Delete / Löschen / 削除."""

    words: tuple[str, ...]
    #: нужен ли разделитель после слова (для иероглифических маркеров — нет)
    boundary: bool = True
    #: что может стоять перед словом: значок-шаблон вроде «(▲)» или «(+)»
    prefix: str = r"[（(]?"

    def _plain_re(self) -> re.Pattern[str]:
        words = "|".join(re.escape(w) for w in self.words)
        tail = r"\b[\s.:,!—-]" if self.boundary else r"\s*[\s.:,!—:：、。-]?"
        return re.compile(rf"^\s*{self.prefix}\s*({words})[）)]?{tail}", re.IGNORECASE)

    def of_comment(self, comment: Comment, section: str | None) -> str | None:
        m = self._plain_re().match(comment.text)
        return _canon(m.group(1)) if m else None

    def wikitext_re(self) -> re.Pattern[str] | None:
        words = "|".join(re.escape(w) for w in self.words)
        tail = r"\b" if self.boundary else ""
        return re.compile(rf"^[\s*:#]*'''\s*(?:\[\[[^]]*\|)?({words}){tail}", re.IGNORECASE)


@dataclass(frozen=True)
class SectionStance:
    """Позиция задаётся секцией: «Mantenere» / «Cancellare», «Conserver» / «Supprimer»."""

    sections: dict[str, str]

    def of_comment(self, comment: Comment, section: str | None) -> str | None:
        if section is None:
            return None
        return self.sections.get(section.strip())

    def wikitext_re(self) -> re.Pattern[str] | None:
        return None


def _canon(word: str) -> str:
    return word[:1].upper() + word[1:] if word.isascii() else word
