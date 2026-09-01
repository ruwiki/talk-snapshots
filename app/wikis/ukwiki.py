"""Українська Вікіпедія: «Статті-кандидати на вилучення» — одна страница на день.

Устройство как в рувики: номинация — секция `==`, итог — подсекция «Підсумок»,
зачёркнутый заголовок = закрыто. Голоса «За / Проти» встречаются чаще, чем в ru.
"""

from ..core.listing import DayPage
from ..core.outcome import OutcomeSection
from ..core.pages import HeadingLinks, Subsections, TitleFromHeading
from ..core.spec import Locale, ReasonClass, WikiSpec
from ..core.stance import VoteWords

MONTHS = {
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5, "червня": 6,
    "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12,
}

WIKI = WikiSpec(
    dbname="ukwiki",
    host="uk.wikipedia.org",
    lang="uk",
    locale=Locale(
        months=MONTHS,
        user_prefixes=("Користувач", "Користувачка", "Обговорення користувача",
                       "Обговорення користувачки", "User", "User talk", "К", "ОК"),
        contrib_prefixes=("Спеціальна:Внесок", "Special:Contributions"),
        namespaces={
            "Вікіпедія": 4, "ВП": 4, "Обговорення": 1, "Користувач": 2, "Користувачка": 2,
            "Обговорення користувача": 3, "Категорія": 14, "Шаблон": 10, "Файл": 6, "Портал": 100,
            "Модуль": 828, "Довідка": 12, "Обговорення Вікіпедії": 5, "Обговорення категорії": 15,
            "Обговорення шаблону": 11, "Wikipedia": 4, "Category": 14, "Template": 10, "File": 6,
        },
        known_bots=frozenset({"WikiBot", "БотКонстантина", "AndriiBot", "TohaomgBot", "BotDR"}),
    ),
    listing=DayPage("Вікіпедія:Статті-кандидати на вилучення/{d} {month} {yyyy}", nomination_level=2),
    pages=(Subsections(), HeadingLinks(), TitleFromHeading()),
    outcome=OutcomeSection(
        section_names=("Підсумок", "Попередній підсумок", "Оскаржений підсумок"),
        kinds={
            r"вилучен[оаі]?\b|вилучити\b|швидко вилучено": "delete",
            r"залишен[оаі]?\b|залишити\b|залишаємо": "keep",
            r"перейменован[оаі]?\b|перейменувати": "rename",
            r"об'?єднан[оаі]?\b|об'?єднати": "merge",
            r"перенаправлен[оаі]?\b|перенаправити|редирект|перенесено до": "redirect",
            r"номінацію знято|знято\b|знімаю": "withdrawn",
        },
    ),
    stance=VoteWords(("За", "Проти", "Залишити", "Вилучити", "Утримуюсь", "Перейменувати", "Об'єднати")),
    reason=ReasonClass(discussion=r"кандидати на вилучення/", speedy=r"ВП:КШВ#?([А-ЯІЇЄ]\d+)?|швидк"),
    common_headings=("По всіх", "Щодо всіх", "Загальне"),
    label="Українська Вікіпедія — кандидати на вилучення",
)
