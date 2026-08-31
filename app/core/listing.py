"""Стратегии «где лежат обсуждения за день».

Два семейства, для движка неразличимые: дневная страница с номинациями-секциями
(ru, de, uk, zh) и дневной лог, транклюдирующий страницы-номинации (en, it, ja).
DiscussionTools сам раскрывает транклюзии и говорит, откуда взята реплика, —
поэтому обе стратегии отдают один заголовок страницы на день.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


def _format(fmt: str, spec, day: dt.date) -> str:
    return fmt.format(
        d=day.day, dd=f"{day.day:02d}", m=day.month, mm=f"{day.month:02d}",
        yyyy=day.year, month=spec.locale.month_name(day.month),
    )


@dataclass(frozen=True)
class DayPage:
    """Одна страница на день, номинации — секции уровня nomination_level.

    group_level: уровень заголовков-групп над номинациями (de: «= Artikel =»),
    сами группы номинациями не являются.
    """

    fmt: str
    nomination_level: int = 2
    group_level: int | None = None

    def page_titles(self, spec, day: dt.date) -> list[str]:
        return [_format(self.fmt, spec, day)]


@dataclass(frozen=True)
class DailyLog:
    """Дневной лог транклюдирует страницы-номинации; заголовок номинации приходит
    из подстраницы, source_page говорит, из какой."""

    fmt: str
    nomination_level: int = 3
    group_level: int | None = None

    def page_titles(self, spec, day: dt.date) -> list[str]:
        return [_format(self.fmt, spec, day)]
