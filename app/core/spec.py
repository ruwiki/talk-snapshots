"""Спецификация раздела: локаль + стратегии по каждой оси вариативности.

Оси (см. docs): как перечислить номинации за день (listing), как найти
страницы номинации (pages), где написан исход (outcome), как читается позиция
реплики (stance), как классифицировать причину удаления (reason). Раздел
собирается композицией готовых стратегий — новый раздел не наследует и не
переопределяет методы, а перечисляет, что у него как устроено.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..models import Comment, Nomination, PageRef


@dataclass(frozen=True)
class Locale:
    #: месяц в подписи → номер (полные или сокращённые формы, как в подписях)
    months: dict[str, int]
    #: месяц для названий страниц (если отличается от подписей: de «Juli» vs «Jul.»)
    page_months: dict[str, int] | None = None
    #: псевдонимы пространства участника; talk-варианты приводятся к тому же имени
    user_prefixes: tuple[str, ...] = ("User", "User talk")
    #: префиксы вклада — имя отделяется косой чертой
    contrib_prefixes: tuple[str, ...] = ("Special:Contributions",)
    #: префикс заголовка → номер пространства; всё, чего тут нет, считается статьёй (ns 0)
    namespaces: dict[str, int] = field(default_factory=dict)
    #: метки часового пояса в подписях и сам пояс (для перевода в UTC в запасном парсере)
    tz_labels: tuple[str, ...] = ("UTC",)
    tz: str = "UTC"
    #: собственный шаблон метки времени с именованными группами hh, mm, day, month, year
    signature_pattern: str | None = None
    known_bots: frozenset[str] = field(default_factory=frozenset)
    #: строки-шум: реплика целиком отбрасывается (уведомления ботов и шаблонов)
    noise_patterns: tuple[str, ...] = ()
    #: обвязка, вычищаемая из текста реплики без её отбрасывания (запасной парсер)
    boilerplate_patterns: tuple[str, ...] = ()

    def month_name(self, n: int) -> str:
        table = self.page_months or self.months
        for name, num in table.items():
            if num == n:
                return name
        raise KeyError(n)

    def timestamp_re(self) -> re.Pattern[str]:
        if self.signature_pattern:
            return re.compile(self.signature_pattern)
        months = "|".join(re.escape(m) for m in self.months)
        tz = "|".join(re.escape(t) for t in self.tz_labels)
        return re.compile(
            rf"(?P<hh>\d{{1,2}}):(?P<mm>\d{{2}}), (?P<day>\d{{1,2}})\.? (?P<month>{months})\.? "
            rf"(?P<year>\d{{4}}) \((?:{tz})\)"
        )

    def user_link_re(self) -> re.Pattern[str]:
        colon = "|".join(re.escape(p) for p in self.user_prefixes)
        slash = "|".join(re.escape(p) for p in self.contrib_prefixes)
        return re.compile(
            rf"\[\[\s*(?:(?:{colon})\s*:|(?:{slash})\s*/)\s*([^|\]#]+?)\s*(?:\||\]\])",
            re.IGNORECASE,
        )

    def user_link_full_re(self) -> re.Pattern[str]:
        colon = "|".join(re.escape(p) for p in self.user_prefixes)
        slash = "|".join(re.escape(p) for p in self.contrib_prefixes)
        return re.compile(
            rf"\[\[\s*(?:(?:{colon})\s*:|(?:{slash})\s*/)[^\]]*\]\]", re.IGNORECASE
        )

    def noise_re(self) -> re.Pattern[str] | None:
        return re.compile("|".join(self.noise_patterns)) if self.noise_patterns else None

    def namespace_of(self, title: str) -> tuple[int, str]:
        """«Категория:Х» → (14, «Х»); заголовок без известного префикса — статья."""
        if ":" in title:
            prefix, rest = title.split(":", 1)
            prefix = prefix.strip()
            if prefix in self.namespaces:
                return self.namespaces[prefix], rest.strip()
        return 0, title.strip()


@runtime_checkable
class Listing(Protocol):
    """Где лежат обсуждения за день и как на странице отделены номинации."""

    nomination_level: int

    def page_titles(self, spec: WikiSpec, day) -> list[str]: ...


@runtime_checkable
class PagesStrategy(Protocol):
    """Какие страницы обсуждает номинация (одна или несколько)."""

    def resolve(self, nom: Nomination, spec: WikiSpec) -> list[PageRef]: ...


@runtime_checkable
class OutcomeStrategy(Protocol):
    """Где и как записан исход обсуждения."""

    #: имена подзаголовков, под которыми лежит итог (для движка и запасного парсера)
    section_names: tuple[str, ...]

    def apply(self, nom: Nomination, spec: WikiSpec, wikitext: str | None) -> None: ...


@runtime_checkable
class StanceStrategy(Protocol):
    """Формальная позиция реплики, если раздел её вообще выражает."""

    def of_comment(self, comment: Comment, section: str | None) -> str | None: ...

    def wikitext_re(self) -> re.Pattern[str] | None: ...


@dataclass(frozen=True)
class ReasonClass:
    """Класс основания удаления по комментарию в журнале: по итогу / быстро / иное."""

    discussion: str
    speedy: str

    def classify(self, comment: str) -> tuple[str, str | None]:
        m = re.search(self.speedy, comment or "", re.IGNORECASE)
        if m:
            return "speedy", (m.group(1) if m.groups() else None)
        if re.search(self.discussion, comment or "", re.IGNORECASE):
            return "discussion", None
        return "other", None


@dataclass(frozen=True)
class WikiSpec:
    dbname: str
    host: str
    lang: str
    locale: Locale
    listing: Listing
    pages: tuple[PagesStrategy, ...]
    outcome: OutcomeStrategy
    stance: StanceStrategy
    reason: ReasonClass
    #: подзаголовки внутри номинации, означающие «общее по всем страницам»
    common_headings: tuple[str, ...] = ()
    #: заголовок номинации может быть зачёркнут — это «закрыто» без итога в тексте
    struck_means_closed: bool = True
    #: подпись раздела на витрине
    label: str = ""
    #: регулярка по названию категории с одной группой = тема (en: «AfD debates (X)»)
    topic_pattern: str | None = None

    def __post_init__(self) -> None:
        assert isinstance(self.listing, Listing)
        assert all(isinstance(p, PagesStrategy) for p in self.pages)
        assert isinstance(self.outcome, OutcomeStrategy)
        assert isinstance(self.stance, StanceStrategy)

    @property
    def nomination_level(self) -> int:
        return self.listing.nomination_level

    def resolve_pages(self, nom: Nomination) -> list[PageRef]:
        """Первая стратегия, давшая непустой ответ, побеждает."""
        for strategy in self.pages:
            refs = strategy.resolve(nom, self)
            if refs:
                return _dedupe(refs)
        return []


def _dedupe(refs: list[PageRef]) -> list[PageRef]:
    seen: set[tuple[int, str]] = set()
    out = []
    for r in refs:
        key = (r.ns, r.title)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out
