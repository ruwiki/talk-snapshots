"""Несовпадения между обсуждением и журналом — списком, со ссылками.

Витрина показывает доли; здесь — третий уровень: конкретные случаи, в которые можно
провалиться. Только проверяемое алгоритмически, по уже собранным таблицам:

  deleted_open    страница удалена по журналу, а обсуждение не закрыто (нет итога, заголовок не зачёркнут)
  kept_deleted    итог «оставить», страница удалена
  delete_exists   итог «удалить», страница живёт (не редирект, не пересоздана)
  redirect_exists итог «перенаправить», страница живёт обычной статьёй
  no_pages        у номинации не распознано ни одной страницы
  missing         страницы нет ни в `page`, ни в журнале (ошибка сопоставления заголовка)

Каждый случай несёт ссылки на обсуждение, страницу и журнал удалений — чтобы человек
проверил глазами и починил либо данные, либо правило.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from urllib.parse import quote

from ..db import DB
from .state import _full_title

KINDS = ("deleted_open", "kept_deleted", "delete_exists", "redirect_exists", "no_pages", "missing")
_SAFE = ":/()!,'"


@dataclass
class Case:
    kind: str
    nomination_id: int
    day: str
    nomination: str
    discussion_url: str
    ns: int | None = None
    title: str | None = None
    page_url: str | None = None
    log_url: str | None = None
    state: str | None = None
    deleted_at: str | None = None
    reason: str | None = None
    outcome: str | None = None
    closer: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _wiki_url(spec, title: str) -> str:
    return f"https://{spec.host}/wiki/{quote(title.replace(' ', '_'), safe=_SAFE)}"


def discussion_url(spec, listing_page: str, source_page: str | None, heading: str) -> str:
    if source_page:
        return _wiki_url(spec, source_page)
    return _wiki_url(spec, listing_page) + "#" + quote(heading.replace(" ", "_"), safe=_SAFE)


def page_url(spec, ns: int, title: str) -> str:
    return _wiki_url(spec, _full_title(spec, ns, title))


def log_url(spec, ns: int, title: str) -> str:
    full = _full_title(spec, ns, title).replace(" ", "_")
    return f"https://{spec.host}/w/index.php?title=Special:Log&type=delete&page={quote(full, safe=_SAFE)}"


def find(db: DB, spec, limit: int = 300) -> tuple[dict[str, list[Case]], dict[str, int]]:
    """Случаи по видам (не больше `limit` на вид, свежие первыми) и полные счётчики."""
    w = spec.dbname
    listing = dict(db.execute("SELECT id, title FROM pages WHERE wiki = ?", (w,)).fetchall())
    noms = db.execute(
        "SELECT id, page_id, day, title, source_page, struck, closed_at FROM nominations WHERE wiki = ?", (w,)
    ).fetchall()
    pages = defaultdict(list)
    for nid, ns, title in db.execute(
        "SELECT nomination_id, ns, title FROM nomination_pages WHERE wiki = ?", (w,)
    ).fetchall():
        pages[nid].append((ns, title))
    states = {
        (ns, title): (state, deleted_at, rclass, rcode)
        for ns, title, state, deleted_at, rclass, rcode in db.execute(
            "SELECT ns, title, state, deleted_at, reason_class, reason_code FROM page_state WHERE wiki = ?", (w,)
        ).fetchall()
    }
    outs: dict[int, dict[str | None, tuple[str, str | None]]] = defaultdict(dict)
    for nid, page, kind, closer in db.execute(
        "SELECT nomination_id, page, kind, closer FROM discussion_outcome WHERE wiki = ?", (w,)
    ).fetchall():
        outs[nid][page or None] = (kind, closer)

    found: dict[str, list[Case]] = {k: [] for k in KINDS}
    for nid, page_id, day, heading, source_page, struck, closed_at in noms:
        base = dict(nomination_id=nid, day=day or "", nomination=heading,
                    discussion_url=discussion_url(spec, listing.get(page_id, ""), source_page, heading))
        if not pages.get(nid):
            found["no_pages"].append(Case(kind="no_pages", **base))
            continue
        for ns, title in pages[nid]:
            state, deleted_at, rclass, rcode = states.get((ns, title), ("missing", None, None, None))
            okind, closer = outs[nid].get(title) or outs[nid].get(None) or (None, None)
            if state == "missing":
                kind = "missing"
            elif state == "deleted" and okind is None and not closed_at and not struck:
                kind = "deleted_open"
            elif state == "deleted" and okind == "keep":
                kind = "kept_deleted"
            elif state == "exists" and okind == "delete":
                kind = "delete_exists"
            elif state == "exists" and okind == "redirect":
                kind = "redirect_exists"
            else:
                continue
            reason = " ".join(x for x in (rclass, rcode) if x) or None
            found[kind].append(Case(kind=kind, ns=ns, title=title, page_url=page_url(spec, ns, title),
                                    log_url=log_url(spec, ns, title), state=state, deleted_at=deleted_at,
                                    reason=reason, outcome=okind, closer=closer, **base))
    counts = {k: len(v) for k, v in found.items()}
    for k in found:
        found[k].sort(key=lambda c: c.day, reverse=True)
        del found[k][limit:]
    return found, counts
