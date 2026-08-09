"""Загрузка: раздел + диапазон дат → база.

Каждый день грузится дважды и с двух сторон: треды от движка (что написано)
и история правок (что происходило). Расхождения между ними — не ошибка,
а материал: реплика без правки означает транклюзию, правка без реплики —
редактирование чужого текста, перенос или подведение итога.
"""

from __future__ import annotations

import argparse
import datetime as dt

from .api import Api
from .db import DB, open_db
from .models import Nomination, Revision
from .threads import fetch_page_threads
from . import revisions as revs
from . import wikis


def day_page_title(wiki: wikis.Wiki, day: dt.date) -> str:
    months = {v: k for k, v in wiki.months.items()}
    return wiki.deletion_page.format(d=day.day, month=months[day.month], y=day.year)


def daterange(start: dt.date, end: dt.date):
    step = dt.timedelta(days=1)
    while start <= end:
        yield start
        start += step


def purge_page(db: DB, wiki: wikis.Wiki, title: str) -> None:
    """Стереть ранее загруженное по странице.

    Вставки идемпотентны, поэтому повторная загрузка сама по себе НЕ обновляет
    старые строки: `vote`, `is_bot` и разбор итогов вычисляются в момент
    загрузки. После изменения правил разбора данные надо перезалить, иначе
    отчёты продолжат показывать прежние числа.
    """
    row = db.execute(
        "SELECT id FROM pages WHERE wiki = ? AND title = ?", (wiki.dbname, title)
    ).fetchone()
    if row:
        page_id = row[0]
        db.execute(
            """DELETE FROM comments WHERE nomination_id IN
               (SELECT id FROM nominations WHERE page_id = ? AND wiki = ?)""",
            (page_id, wiki.dbname),
        )
        db.execute(
            "DELETE FROM nominations WHERE page_id = ? AND wiki = ?", (page_id, wiki.dbname)
        )
    db.execute(
        "DELETE FROM revisions WHERE wiki = ? AND page_title = ?", (wiki.dbname, title)
    )


def store_page(db: DB, wiki: wikis.Wiki, title: str, day: dt.date) -> int:
    db.execute(
        db.ignore("INSERT INTO pages (wiki, title, day, fetched_at) VALUES (?, ?, ?, ?)"),
        (wiki.dbname, title, day.isoformat(), dt.datetime.now(dt.timezone.utc).isoformat()),
    )
    cur = db.execute(
        "SELECT id FROM pages WHERE wiki = ? AND title = ?", (wiki.dbname, title)
    )
    return cur.fetchone()[0]


def store_nominations(
    db: DB, wiki: wikis.Wiki, page_id: int, day: dt.date, noms: list[Nomination]
) -> int:
    stored = 0
    for nom in noms:
        db.execute(
            db.ignore("""INSERT INTO nominations
               (page_id, wiki, day, title, struck, opened_at, closed_at, n_comments)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""),
            (
                page_id, wiki.dbname, day.isoformat(), nom.title[:250], int(nom.struck),
                nom.opened_at.isoformat() if nom.opened_at else None,
                nom.closed_at.isoformat() if nom.closed_at else None,
                len(nom.comments),
            ),
        )
        nom_id = db.execute(
            "SELECT id FROM nominations WHERE wiki = ? AND page_id = ? AND title = ?",
            (wiki.dbname, page_id, nom.title[:250]),
        ).fetchone()[0]
        db.executemany(
            db.ignore("""INSERT INTO comments
               (nomination_id, wiki, idx, author, ts, depth, parent_idx, vote,
                is_outcome, is_bot, text)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""),
            [
                (
                    nom_id, wiki.dbname, c.idx, c.author,
                    c.ts.isoformat() if c.ts else None, c.depth, c.parent, c.vote,
                    int(c.is_outcome), int(c.is_bot), c.text[:60000],
                )
                for c in nom.comments
            ],
        )
        stored += len(nom.comments)
    return stored


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


def ingest_day(
    db: DB, wiki: wikis.Wiki, api: Api, day: dt.date,
    with_revisions: bool = True, refresh: bool = False,
):
    title = day_page_title(wiki, day)
    noms = fetch_page_threads(api, wiki, page=title)
    if not noms:
        return dict(day=day.isoformat(), page=title, nominations=0, comments=0, revisions=0)

    if refresh:
        purge_page(db, wiki, title)
    page_id = store_page(db, wiki, title, day)
    n_comments = store_nominations(db, wiki, page_id, day, noms)
    n_revs = 0
    if with_revisions:
        rows = revs.fetch(wiki, title, api=api)
        store_revisions(db, rows)
        n_revs = len(rows)
    db.commit()
    return dict(
        day=day.isoformat(), page=title, nominations=len(noms),
        comments=n_comments, revisions=n_revs,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="загрузить обсуждения об удалении в базу")
    ap.add_argument("--wiki", default="ruwiki", help="ruwiki | enwiki")
    ap.add_argument("--from", dest="start", help="ГГГГ-ММ-ДД")
    ap.add_argument("--recent", type=int, help="последние N дней, считая сегодняшний")
    ap.add_argument("--to", dest="end", help="ГГГГ-ММ-ДД, по умолчанию = --from")
    ap.add_argument("--db", default=None, help="файл SQLite или toolsdb:<база>")
    ap.add_argument("--no-revisions", action="store_true", help="только треды, без истории правок")
    ap.add_argument("--refresh", action="store_true",
                    help="перезалить дни заново: нужно после изменения правил разбора")
    args = ap.parse_args()

    if args.recent:
        end = dt.datetime.now(dt.timezone.utc).date()
        start = end - dt.timedelta(days=args.recent - 1)
    elif args.start:
        start = dt.date.fromisoformat(args.start)
        end = dt.date.fromisoformat(args.end) if args.end else start
    else:
        ap.error("нужен либо --from, либо --recent")
    wiki = wikis.get(args.wiki)
    api = Api(wiki.host)

    with open_db(args.db) as db:
        db.init_schema()
        for day in daterange(start, end):
            res = ingest_day(db, wiki, api, day, with_revisions=not args.no_revisions,
                             refresh=args.refresh)
            print(
                f"{res['day']}  номинаций {res['nominations']:>3}  "
                f"реплик {res['comments']:>4}  правок {res['revisions']:>4}  {res['page']}"
            )


if __name__ == "__main__":
    main()
