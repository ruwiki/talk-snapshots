"""Deutschsprachige Wikipedia: Löschkandidaten — одна страница на день.

`= =` — группы (Kategorien, Vorlagen, Artikel…), `== ==` — объекты. Исход
вписывается прямо в заголовок: «Emily Gretel (gelöscht)», «(bleibt)», «(LAE)»,
«(LAZ nach Diskussion)», «(SLA)» — формальнее, чем где-либо ещё. Подписи в
CEST/CET и с сокращённым месяцем: «09:15, 1. Jul. 2026 (CEST)».
"""

from ..core.listing import DayPage
from ..core.outcome import HeadingSuffix
from ..core.pages import HeadingLinks, TitleFromHeading
from ..core.spec import Locale, ReasonClass, WikiSpec
from ..core.stance import VoteWords

PAGE_MONTHS = {
    "Januar": 1, "Februar": 2, "März": 3, "April": 4, "Mai": 5, "Juni": 6,
    "Juli": 7, "August": 8, "September": 9, "Oktober": 10, "November": 11, "Dezember": 12,
}
SIG_MONTHS = {
    "Jan": 1, "Feb": 2, "Mär": 3, "Apr": 4, "Mai": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Okt": 10, "Nov": 11, "Dez": 12,
    **PAGE_MONTHS,
}

SUFFIX = (r"\(\s*((?:erl\.?|erledigt|gelöscht|bleibt|LAE|LAZ|SLA|SLA ausgeführt|"
          r"zurückgezogen|Weiterleitung|WL|verschoben|bleibt vorerst|gel\.|bleibt, LAE|"
          r"LAE, bleibt|Redirect|Löschantrag zurückgezogen)[^)]*)\)\s*$")

WIKI = WikiSpec(
    dbname="dewiki",
    host="de.wikipedia.org",
    lang="de",
    locale=Locale(
        months=SIG_MONTHS,
        page_months=PAGE_MONTHS,
        user_prefixes=("Benutzer", "Benutzerin", "Benutzer Diskussion", "Benutzerin Diskussion",
                       "BD", "User", "User talk"),
        contrib_prefixes=("Spezial:Beiträge", "Special:Contributions"),
        namespaces={
            "Wikipedia": 4, "WP": 4, "Diskussion": 1, "Benutzer": 2, "Benutzerin": 2,
            "Benutzer Diskussion": 3, "Kategorie": 14, "Vorlage": 10, "Datei": 6, "Portal": 100,
            "Modul": 828, "Hilfe": 12, "Wikipedia Diskussion": 5, "Kategorie Diskussion": 15,
            "Vorlage Diskussion": 11, "Category": 14, "Template": 10, "File": 6,
        },
        tz_labels=("CEST", "CET", "MESZ", "MEZ"),
        tz="Europe/Berlin",
        known_bots=frozenset({"TaxonBot", "Xqbot", "GiftBot", "CactusBot", "APPERbot", "Krdbot"}),
    ),
    listing=DayPage("Wikipedia:Löschkandidaten/{d}. {month} {yyyy}", nomination_level=2, group_level=1),
    pages=(HeadingLinks(), TitleFromHeading(strip=SUFFIX)),
    outcome=HeadingSuffix(
        pattern=SUFFIX,
        kinds={
            r"gel(?:öscht|\.)|\bSLA\b": "delete",
            r"bleibt|\bLAE\b|behalten": "keep",
            r"\bLAZ\b|zurückgezogen": "withdrawn",
            r"Weiterleitung|\bWL\b|Redirect": "redirect",
            r"verschoben": "moved",
        },
    ),
    stance=VoteWords(("Löschen", "Behalten", "LAE", "LAZ", "Schnelllöschen", "SLA", "Neutral")),
    reason=ReasonClass(discussion=r"Löschkandidaten/", speedy=r"\b(SLA|Schnelllösch\w*)\b"),
    label="Deutsche Wikipedia — Löschkandidaten",
)
