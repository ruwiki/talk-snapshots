"""English Wikipedia: AfD — дневной лог транклюдирует страницу на номинацию.

Позиция — жирное слово в начале реплики (Keep/Delete/Merge…). Итог пишется
шаблоном {{afd top}} в вики-тексте страницы номинации: «The result was keep».
"""

from ..core.listing import DailyLog
from ..core.outcome import ClosingTemplate
from ..core.pages import HeadingLinks, TitleAfterPrefix, TitleFromHeading
from ..core.spec import Locale, ReasonClass, WikiSpec
from ..core.stance import VoteWords

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}

WIKI = WikiSpec(
    dbname="enwiki",
    host="en.wikipedia.org",
    lang="en",
    locale=Locale(
        months=MONTHS,
        user_prefixes=("User", "User talk"),
        contrib_prefixes=("Special:Contributions", "Special:Contribs"),
        namespaces={
            "Wikipedia": 4, "WP": 4, "Talk": 1, "User": 2, "User talk": 3, "Category": 14,
            "Template": 10, "File": 6, "Portal": 100, "Module": 828, "Draft": 118, "Help": 12,
            "Wikipedia talk": 5, "Template talk": 11, "Category talk": 15, "Book": 108,
        },
        known_bots=frozenset({"Legobot", "SodiumBot", "AnomieBOT", "Cyberbot I", "Cewbot", "XFDcloser"}),
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
    ),
    listing=DailyLog("Wikipedia:Articles for deletion/Log/{yyyy} {month} {d}", nomination_level=3),
    pages=(
        TitleAfterPrefix("Wikipedia:Articles for deletion/"),
        HeadingLinks(only_articles=True),
        TitleFromHeading(),
    ),
    outcome=ClosingTemplate(
        pattern=r"The result was\s*'*\s*(?:\[\[[^]|]*\|)?([^'\].\n]{2,60})",
        kinds={
            r"delet": "delete",
            r"keep|no consensus|not merged": "keep",
            r"merge": "merge",
            r"redirect|BLAR": "redirect",
            r"draftif|userf|incubat|move": "moved",
            r"withdraw|procedural close": "withdrawn",
            r"rename": "rename",
        },
    ),
    # «Comment» сюда не входит: это пометка «просто замечание», а не позиция.
    # С ним доля реплик с позицией завышалась на 4 процентных пункта.
    stance=VoteWords((
        "Keep", "Delete", "Merge", "Redirect", "Speedy keep", "Speedy delete",
        "Speedy close", "Draftify", "Userfy", "Weak keep", "Weak delete",
        "Strong keep", "Strong delete",
    )),
    reason=ReasonClass(discussion=r"Articles for deletion/", speedy=r"CSD#([A-Z]\d+)"),
)
