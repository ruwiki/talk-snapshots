"""Покрытие: какие Википедии есть на витрине, какие в очереди, где площадки нет.

Снимок разведки 27.09.2026 (stuff/Projects/toolforge/25, 26; data/cee-survey/<db>.md):
активные участники за 30 дней по siteinfo, площадка и число номинаций за август 2026 —
по API. Это справочная таблица для обзора; обновляется руками при новой разведке.

plan: live — раздел в проде; next — в очереди этапа 3; later — площадка есть, но
объём единицы в месяц; log-only — работающей площадки обсуждений нет, только журнал.
"""

from __future__ import annotations

SURVEYED_ON = "2026-09-27"

#: (dbname, active editors, venue title or None, how nominations are listed, nominations in Aug 2026, plan)
SURVEY: list[tuple[str, int, str | None, str, str, str]] = [
    ("eswiki", 38963, None, "not surveyed yet", "", "next"),
    ("frwiki", 34548, None, "not surveyed yet", "", "next"),
    ("plwiki", 8856, "Wikipedia:Poczekalnia/artykuły", "dated subpages on a permanent hub, monthly archive", "140 + 66 (biographies)", "next"),
    ("nlwiki", 7864, None, "not surveyed yet", "", "next"),
    ("ptwiki", 7598, None, "not surveyed yet", "", "next"),
    ("arwiki", 5600, None, "not surveyed yet", "", "next"),
    ("svwiki", 4891, None, "not surveyed yet", "", "next"),
    ("trwiki", 4213, "Vikipedi:Silinmeye aday sayfalar", "permanent hub, monthly archive", "102", "next"),
    ("cswiki", 4123, "Wikipedie:Diskuse o smazání", "subpages transcluded on a hub list", "16", "next"),
    ("huwiki", 2714, "Wikipédia:Törlésre javasolt lapok", "subpages on a hub grouped by date, monthly archive category", "34", "next"),
    ("elwiki", 2270, "Βικιπαίδεια:Σελίδες για διαγραφή", "discussion on the article's talk subpage, monthly index", "6", "next"),
    ("rowiki", 1703, "Wikipedia:Pagini de șters", "subpages transcluded on a hub, monthly ledger of outcomes", "5", "next"),
    ("bgwiki", 1667, "Уикипедия:Страници за изтриване", "dated subpages on a permanent hub", "7–10", "next"),
    ("srwiki", 1619, "Википедија:Чланци за брисање", "sections on one page, numbered archives; outcome computed from votes", "2", "later"),
    ("skwiki", 1198, "Wikipédia:Stránky na zmazanie", "subpages on a hub, yearly archive", "8", "next"),
    ("etwiki", 976, None, "no central venue: article talk page + queue category (624 pages)", "≈59 queued", "log-only"),
    ("hrwiki", 953, "Wikipedija:Rasprava o brisanju", "one page per month, sections", "22", "next"),
    ("azwiki", 849, "Vikipediya:Silinməyə namizəd səhifələr", "subpages transcluded on a hub", "8–25", "next"),
    ("ltwiki", 624, None, "venue dead since 2009; tag + queue category, voting banned", "0", "log-only"),
    ("slwiki", 591, "Wikipedija:Predlogi za brisanje", "subpages on a hub grouped by month", "2", "later"),
    ("uzwiki", 579, "Vikipediya:Oʻchirishga", "subpages transcluded on a hub", "2", "later"),
    ("hywiki", 552, "Վիքիպեդիա:Ջնջման առաջադրված հոդվածներ", "sections on one page; outcome computed from votes (75 %)", "4", "next"),
    ("lvwiki", 498, None, "PROD tag; the voting hub has not handled articles since 2013", "0", "log-only"),
    ("bewiki", 399, "Вікіпедыя:Да выдалення", "sections on one page, yearly archive", "3", "later"),
    ("sqwiki", 370, "Wikipedia:Forumi i Grisjes", "register page, numbered archives", "≈1", "later"),
    ("kkwiki", 369, None, "no venue: the community declined one in 2020", "—", "log-only"),
    ("kawiki", 346, "ვიკიპედია:წაშლილი გვერდების განხილვები", "link hub → subpages; unused", "0", "log-only"),
    ("mkwiki", 324, "Википедија:Статии за бришење", "one page, dead since 2013", "0", "log-only"),
    ("bswiki", 257, None, "rules page only; tag + article talk", "0", "log-only"),
    ("be_x_oldwiki", 195, "Вікіпэдыя:Кандыдатуры на выдаленьне", "sections on one page, yearly archive", "1", "later"),
]


def host(dbname: str) -> str:
    lang = dbname.removesuffix("wiki").replace("_", "-")
    return f"{lang}.wikipedia.org"


def rows() -> list[dict]:
    out = []
    for db, active, venue, listing, per_month, plan in SURVEY:
        out.append({
            "wiki": db, "active": active, "venue": venue,
            "venue_url": f"https://{host(db)}/wiki/{venue.replace(' ', '_')}" if venue else None,
            "listing": listing, "per_month": per_month, "plan": plan,
        })
    return out
