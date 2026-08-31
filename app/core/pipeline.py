"""Конвейер одного дня: listing → threads → pages → outcome → store → revisions → topics.

Ядро не знает, какой раздел грузит: всё, что различается, лежит в спеке.
Повторный запуск идемпотентен (INSERT IGNORE), но строки не обновляет —
поэтому есть два способа перечитать день: --refresh (всегда) и
--refresh-changed (только если страница на вики менялась с прошлого раза;
правка обсуждения на вики = триггер перечитывания).
"""

from __future__ import annotations

import datetime as dt

from ..api import Api
from ..db import DB
from ..models import Nomination, Revision
from . import revisions as revs
from . import state as pstate
from . import topics as ptopics
from .threads import fetch_page_threads


def daterange(start: dt.date, end: dt.date):
    step = dt.timedelta(days=1)
    while start <= end:
        yield start
        start += step


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def purge_page(db: DB, spec, title: str) -> None:
    """Стереть ранее загруженное по странице обсуждений (кроме снимков тем и судьбы)."""
    row = db.execute(
        "SELECT id FROM pages WHERE wiki = ? AND title = ?", (spec.dbname, title)
    ).fetchone()
    if row:
        page_id = row[0]
        sub = "(SELECT id FROM nominations WHERE page_id = ? AND wiki = ?)"
        for table in ("comments", "nomination_pages", "discussion_outcome"):
            db.execute(f"DELETE FROM {table} WHERE nomination_id IN {sub}", (page_id, spec.dbname))
        db.execute("DELETE FROM nominations WHERE page_id = ? AND wiki = ?", (page_id, spec.dbname))
        db.execute("DELETE FROM pages WHERE id = ?", (page_id,))
    db.execute("DELETE FROM revisions WHERE wiki = ? AND page_title = ?", (spec.dbname, title))


def store_page(db: DB, spec, title: str, day: dt.date, revid: int | None) -> int:
    db.execute(
        db.ignore("INSERT INTO pages (wiki, title, day, revid, fetched_at) VALUES (?, ?, ?, ?, ?)"),
        (spec.dbname, title, day.isoformat(), revid, _now()),
    )
    if revid is not None:
        db.execute("UPDATE pages SET revid = ?, fetched_at = ? WHERE wiki = ? AND title = ?",
                   (revid, _now(), spec.dbname, title))
    return db.execute(
        "SELECT id FROM pages WHERE wiki = ? AND title = ?", (spec.dbname, title)
    ).fetchone()[0]


def store_nominations(db: DB, spec, page_id: int, day: dt.date, noms: list[Nomination]) -> tuple[int, list[int]]:
    stored = 0
    ids: list[int] = []
    for nom in noms:
        db.execute(
            db.ignore("""INSERT INTO nominations
               (page_id, wiki, day, title, struck, opened_at, closed_at, n_comments, kind, source_page)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""),
            (
                page_id, spec.dbname, day.isoformat(), nom.title[:250], int(nom.struck),
                nom.opened_at.isoformat() if nom.opened_at else None,
                nom.closed_at.isoformat() if nom.closed_at else None,
                len(nom.comments), nom.kind, (nom.source_page or "")[:250] or None,
            ),
        )
        nom_id = db.execute(
            "SELECT id FROM nominations WHERE wiki = ? AND page_id = ? AND title = ?",
            (spec.dbname, page_id, nom.title[:250]),
        ).fetchone()[0]
        ids.append(nom_id)
        db.executemany(
            db.ignore("INSERT INTO nomination_pages (nomination_id, wiki, ns, title, resolved_by) VALUES (?, ?, ?, ?, ?)"),
            [(nom_id, spec.dbname, p.ns, p.title[:250], p.resolved_by) for p in nom.pages],
        )
        db.executemany(
            db.ignore("""INSERT INTO comments
               (nomination_id, wiki, idx, author, ts, depth, parent_idx, vote,
                is_outcome, is_bot, text, page, section)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""),
            [
                (
                    nom_id, spec.dbname, c.idx, c.author,
                    c.ts.isoformat() if c.ts else None, c.depth, c.parent, c.vote,
                    int(c.is_outcome), int(c.is_bot), c.text[:60000],
                    (c.page or "")[:250] or None, (c.section or "")[:250] or None,
                )
                for c in nom.comments
            ],
        )
        db.executemany(
            db.ignore("""INSERT INTO discussion_outcome
               (nomination_id, wiki, page, kind, closer, closed_at, source, raw)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""),
            [
                (
                    nom_id, spec.dbname, (o.page or "")[:250], o.kind, o.closer,
                    o.closed_at.isoformat() if o.closed_at else None, o.source, o.raw[:250],
                )
                for o in nom.outcomes
            ],
        )
        stored += len(nom.comments)
    return stored, ids


def store_revisions(db: DB, rows: list[Revision]) -> None:
    db.executemany(
        db.ignore("""INSERT INTO revisions
           (rev_id, wiki, page_title, actor, ts, section, summary, tags, size_delta)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""),
        [
            (
                r.rev_id, r.wiki, r.page_title, r.actor, r.ts.isoformat(),
                r.section, r.summary[:500], ",".join(r.tags), r.size_delta,
            )
            for r in rows
        ],
    )


def store_topics(db: DB, spec, noms: list[Nomination], ids: list[int], api: Api | None) -> int:
    """Снимок тем по страницам номинаций дня + категории страниц-номинаций (DELSORT)."""
    refs: list[tuple[int, str]] = []
    owners: dict[tuple[int, str], list[int]] = {}
    for nom, nom_id in zip(noms, ids, strict=True):
        for p in nom.pages:
            key = (p.ns, p.title)
            if key not in owners:
                refs.append(key)
            owners.setdefault(key, []).append(nom_id)
        if nom.source_page:
            ns, title = revs.split_title(spec, nom.source_page)
            key = (ns, title.replace("_", " "))
            if key not in owners:
                refs.append(key)
            owners.setdefault(key, []).append(nom_id)
    rows = []
    for ns, title, source, value in ptopics.snapshot(spec, refs, api):
        for nom_id in owners.get((ns, title), ()):
            rows.append((nom_id, spec.dbname, ns, title[:250], source, value[:250], _now()))
    db.executemany(
        db.ignore("INSERT INTO topics (nomination_id, wiki, ns, title, source, value, taken_at) VALUES (?, ?, ?, ?, ?, ?, ?)"),
        rows,
    )
    return len(rows)


def _wikitext_by_nomination(api: Api, spec, page_title: str, noms: list[Nomination]) -> dict[int, str]:
    """Вики-текст секции каждой номинации, если стратегия исхода его требует."""
    from .parse import split_sections

    out: dict[int, str] = {}
    if all(n.source_page for n in noms):
        # дневной лог: у каждой номинации своя страница
        for i, n in enumerate(noms):
            data = api.get(action="parse", page=n.source_page, prop="wikitext")
            out[i] = data.get("parse", {}).get("wikitext", "") or ""
        return out
    data = api.get(action="parse", page=page_title, prop="wikitext")
    text = data.get("parse", {}).get("wikitext", "") or ""
    from .parse import heading_title

    sections = {heading_title(s.heading): s.body for s in split_sections(text, spec.nomination_level)}
    for i, n in enumerate(noms):
        body = sections.get(n.title)
        if body is None:
            # заголовок движка может отличаться от вики-текста оформлением — ищем по вхождению
            for k, v in sections.items():
                if n.title and (n.title in k or k in n.title):
                    body = v
                    break
        if body is not None:
            out[i] = body
    return out


def ingest_day(
    db: DB, spec, api: Api, day: dt.date,
    with_revisions: bool = True, refresh: bool = False, refresh_changed: bool = False,
    with_topics: bool = True,
) -> dict:
    result = dict(day=day.isoformat(), pages=0, nominations=0, comments=0, revisions=0, topics=0, skipped=0)
    for title in spec.listing.page_titles(spec, day):
        latest = None
        if refresh_changed or not refresh:
            latest = revs.latest_revid(spec, title, api)
        if refresh_changed and not refresh:
            row = db.execute("SELECT revid FROM pages WHERE wiki = ? AND title = ?",
                             (spec.dbname, title)).fetchone()
            if row and row[0] is not None and latest is not None and int(row[0]) == int(latest):
                result["skipped"] += 1
                continue
            if row:
                purge_page(db, spec, title)
        elif refresh:
            purge_page(db, spec, title)

        noms = fetch_page_threads(api, spec, page=title)
        if not noms:
            continue
        if getattr(spec.outcome, "needs_wikitext", False):
            texts = _wikitext_by_nomination(api, spec, title, noms)
            for i, nom in enumerate(noms):
                nom.outcomes.clear()
                spec.outcome.apply(nom, spec, texts.get(i))
        page_id = store_page(db, spec, title, day, latest)
        n_comments, ids = store_nominations(db, spec, page_id, day, noms)
        result["pages"] += 1
        result["nominations"] += len(noms)
        result["comments"] += n_comments
        if with_revisions:
            rows = revs.fetch(spec, title, api=api)
            store_revisions(db, rows)
            result["revisions"] += len(rows)
        if with_topics:
            result["topics"] += store_topics(db, spec, noms, ids, api)
        db.commit()
    return result


def refresh_states(db: DB, spec, api: Api | None = None, since: dt.date | None = None) -> int:
    """Пересчитать судьбу всех страниц раздела по журналам — по всему объёму, без окна."""
    rows = db.execute(
        """SELECT DISTINCT np.ns, np.title, MIN(n.day)
             FROM nomination_pages np JOIN nominations n ON n.id = np.nomination_id
            WHERE np.wiki = ? GROUP BY np.ns, np.title""",
        (spec.dbname,),
    ).fetchall()
    if not rows:
        return 0
    first_day = min(dt.date.fromisoformat(r[2]) for r in rows if r[2])
    since = since or (first_day - dt.timedelta(days=1))
    states = pstate.page_states(spec, [(r[0], r[1]) for r in rows], since, api)
    q = db.upsert(
        """INSERT INTO page_state
           (wiki, ns, title, state, deleted_at, deleted_by, reason_class, reason_code, reason_raw, moved_to, checked_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        keys=("wiki", "ns", "title"),
        cols=("wiki", "ns", "title", "state", "deleted_at", "deleted_by", "reason_class",
              "reason_code", "reason_raw", "moved_to", "checked_at"),
    )
    db.executemany(
        q,
        [
            (
                spec.dbname, s.ns, s.title[:250], s.state,
                s.deleted_at.isoformat() if s.deleted_at else None, s.deleted_by,
                s.reason_class, s.reason_code, s.reason_raw, s.moved_to, _now(),
            )
            for s in states
        ],
    )
    db.commit()
    return len(states)
