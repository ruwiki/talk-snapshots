"""Wikipedia in italiano: Pagine da cancellare — дневной лог транклюдирует
страницу на номинацию.

Внутри: фазы «Discussione iniziata…» / «Votazione iniziata…» (уровень 4) и
секции «Mantenere» / «Cancellare» (уровень 5): позиция задаётся секцией, в
которой стоит подпись. Итог отдельной подсекции не имеет — судьба из журнала.
"""

from ..core.listing import DailyLog
from ..core.outcome import NoOutcome
from ..core.pages import HeadingLinks, TitleAfterPrefix, TitleFromHeading
from ..core.spec import Locale, ReasonClass, WikiSpec
from ..core.stance import SectionStance

PAGE_MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}
SIG_MONTHS = {
    "gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6,
    "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12,
    **PAGE_MONTHS,
}

WIKI = WikiSpec(
    dbname="itwiki",
    host="it.wikipedia.org",
    lang="it",
    locale=Locale(
        months=SIG_MONTHS,
        page_months=PAGE_MONTHS,
        user_prefixes=("Utente", "Utenta", "Discussioni utente", "Discussioni utenta", "User", "User talk"),
        contrib_prefixes=("Speciale:Contributi", "Special:Contributions"),
        namespaces={
            "Wikipedia": 4, "WP": 4, "Discussione": 1, "Utente": 2, "Utenta": 2,
            "Discussioni utente": 3, "Categoria": 14, "Template": 10, "File": 6, "Portale": 100,
            "Modulo": 828, "Aiuto": 12, "Bozza": 118, "Progetto": 102, "Discussioni Wikipedia": 5,
            "Discussioni template": 11, "Discussioni categoria": 15, "Category": 14,
        },
        tz_labels=("CEST", "CET"),
        tz="Europe/Rome",
        known_bots=frozenset({"Botcrux", "FrescoBot", "Rotbot", "ValterVBot", "Biobot"}),
    ),
    listing=DailyLog("Wikipedia:Pagine da cancellare/Log/{yyyy} {month} {d}", nomination_level=3),
    pages=(
        TitleAfterPrefix("Wikipedia:Pagine da cancellare/"),
        HeadingLinks(only_articles=True),
        TitleFromHeading(),
    ),
    outcome=NoOutcome(),
    stance=SectionStance({"Mantenere": "Keep", "Cancellare": "Delete"}),
    reason=ReasonClass(discussion=r"Pagine da cancellare/", speedy=r"\bC(\d{1,2})\b|immediata"),
    label="Wikipedia italiana — Pagine da cancellare",
)
