"""Адаптеры разделов: всё, что отличает разбор одной вики от другой.

Слой 1 (кто, когда, кому отвечает) одинаков везде — различаются только
названия месяцев, псевдонимы пространства участников и то, где лежат
обсуждения об удалении. Новый раздел = одна запись в WIKIS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
EN_MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}


@dataclass(frozen=True)
class Wiki:
    dbname: str
    host: str
    lang: str
    months: dict[str, int]
    #: псевдонимы, ведущие на страницу участника; talk-варианты нормализуются к тому же имени
    user_prefixes: tuple[str, ...]
    #: префиксы вклада — имя отделяется косой чертой, а не двоеточием
    contrib_prefixes: tuple[str, ...]
    #: как называется страница обсуждений об удалении за дату
    deletion_page: str
    #: одна страница на день (рувики) или одна страница на номинацию (англовики)
    day_page: bool
    #: уровень заголовка, которым разделены номинации внутри страницы
    nomination_level: int
    #: заголовок подытога, если он выделен отдельной секцией
    outcome_headings: tuple[str, ...] = ()
    #: маркеры позиции в начале реплики (там, где раздел их использует)
    vote_words: tuple[str, ...] = ()
    #: строки-шум: служебные уведомления ботов и шаблонов — реплика целиком отбрасывается
    noise_patterns: tuple[str, ...] = ()
    #: обвязка страницы, которую надо вычистить из текста реплики, не отбрасывая её
    boilerplate_patterns: tuple[str, ...] = ()
    known_bots: frozenset[str] = field(default_factory=frozenset)

    def timestamp_re(self) -> re.Pattern[str]:
        months = "|".join(re.escape(m) for m in self.months)
        return re.compile(rf"(\d{{1,2}}):(\d{{2}}), (\d{{1,2}}) ({months}) (\d{{4}}) \(UTC\)")

    def user_link_re(self) -> re.Pattern[str]:
        colon = "|".join(re.escape(p) for p in self.user_prefixes)
        slash = "|".join(re.escape(p) for p in self.contrib_prefixes)
        return re.compile(
            rf"\[\[\s*(?:(?:{colon})\s*:|(?:{slash})\s*/)\s*([^|\]#]+?)\s*(?:\||\]\])",
            re.IGNORECASE,
        )

    def user_link_full_re(self) -> re.Pattern[str]:
        """Ссылка на участника целиком, вместе с закрывающими скобками.

        Нужна отдельно от user_link_re: при срезании подписи нельзя трогать
        обычные ссылки — реплика вида «[[ВП:КОПИВИО]] ~~~~» иначе исчезает.
        """
        colon = "|".join(re.escape(p) for p in self.user_prefixes)
        slash = "|".join(re.escape(p) for p in self.contrib_prefixes)
        return re.compile(
            rf"\[\[\s*(?:(?:{colon})\s*:|(?:{slash})\s*/)[^\]]*\]\]", re.IGNORECASE
        )

    def vote_re(self) -> re.Pattern[str] | None:
        if not self.vote_words:
            return None
        words = "|".join(re.escape(w) for w in self.vote_words)
        return re.compile(rf"^[\s*:#]*'''\s*(?:\[\[[^]]*\|)?({words})\b", re.IGNORECASE)

    def vote_plain_re(self) -> re.Pattern[str] | None:
        """То же, но для уже отрисованного текста: разметка жирного там снята."""
        if not self.vote_words:
            return None
        words = "|".join(re.escape(w) for w in self.vote_words)
        return re.compile(rf"^\s*({words})\b[\s.:,!—-]", re.IGNORECASE)

    def noise_re(self) -> re.Pattern[str] | None:
        if not self.noise_patterns:
            return None
        return re.compile("|".join(self.noise_patterns))


RUWIKI = Wiki(
    dbname="ruwiki",
    host="ru.wikipedia.org",
    lang="ru",
    months=RU_MONTHS,
    user_prefixes=(
        "Участник", "Участница", "У", "Обсуждение участника", "Обсуждение участницы",
        "ОУ", "User", "User talk",
    ),
    contrib_prefixes=("Служебная:Вклад", "Special:Contributions", "Служебная:Contributions"),
    deletion_page="Википедия:К удалению/{d} {month} {y}",
    day_page=True,
    nomination_level=2,
    outcome_headings=("Итог", "Автоитог", "Предварительный итог", "Оспоренный итог"),
    # в рувики формального голосования нет — маркеры встречаются, но редко
    vote_words=("За", "Против", "Оставить", "Удалить", "Переименовать", "Объединить"),
    noise_patterns=(
        r"ruwiki-previous\w*",          # уведомления бота о прошлых номинациях и тёзках
        r"\{\{Автоперенос с КБУ",
        r"Автоматический перенос статьи с быстрого удаления",
    ),
    boilerplate_patterns=(
        r"\{\{КУ-Навигация\}\}",
        r"\{\{(?:subst:)?Пропущенный итог[^}]*\}\}",
    ),
    known_bots=frozenset({"QBA-II-bot", "KrBot", "BotDR", "Bot", "ClaymoreBot"}),
)

ENWIKI = Wiki(
    dbname="enwiki",
    host="en.wikipedia.org",
    lang="en",
    months=EN_MONTHS,
    user_prefixes=("User", "User talk"),
    contrib_prefixes=("Special:Contributions", "Special:Contribs"),
    deletion_page="Wikipedia:Articles for deletion/Log/{y} {month} {d}",
    day_page=False,  # дневной лог только транклюдирует номинации-подстраницы
    nomination_level=3,
    outcome_headings=(),
    # «Comment» сюда не входит: это пометка «просто замечание», а не позиция.
    # С ним доля реплик с позицией завышалась на 4 процентных пункта.
    vote_words=(
        "Keep", "Delete", "Merge", "Redirect", "Speedy keep", "Speedy delete",
        "Speedy close", "Draftify", "Userfy", "Weak keep", "Weak delete",
        "Strong keep", "Strong delete",
    ),
    noise_patterns=(r"delsort-notice", r"xfd_relist", r"class=\"?xfd_relist"),
    boilerplate_patterns=(
        r"\{\{REMOVE THIS TEMPLATE[^}]*\}\}",
        r"<noinclude>.*?</noinclude>",
        r"<includeonly>.*?</includeonly>",
        r"\{\{AFD help\}\}",
        r"\{\{la\|[^}]*\}\}",
        r"\{\{Find sources AFD\|[^}]*\}\}",
        r"^[^\n]*edits since nomination[^\n]*$",  # шапка номинации после вычистки шаблонов
        r"^\s*:?\s*\(\s*\)\s*$",           # то, что от неё осталось
    ),
    known_bots=frozenset({"Legobot", "SodiumBot", "AnomieBOT", "Cyberbot I"}),
)

WIKIS: dict[str, Wiki] = {w.dbname: w for w in (RUWIKI, ENWIKI)}


def get(dbname: str) -> Wiki:
    try:
        return WIKIS[dbname]
    except KeyError:
        raise SystemExit(f"неизвестный раздел: {dbname}; есть {', '.join(WIKIS)}") from None
