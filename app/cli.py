"""Командная строка: ingest | state | quality | daily.

`daily` — то, что крутит крон на Toolforge: по каждому разделу из TS_WIKIS
перечитать последние N дней (только изменившиеся страницы), пересчитать судьбу
страниц по журналам и посчитать метрики качества. Код возврата ненулевой, если
метрики вышли за пороги, — сбой виден в логе джобы.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

from . import wikis
from .api import Api
from .core import pipeline, quality
from .db import open_db


def _days(args) -> tuple[dt.date, dt.date]:
    if args.recent:
        end = dt.datetime.now(dt.UTC).date()
        return end - dt.timedelta(days=args.recent - 1), end
    if args.start:
        start = dt.date.fromisoformat(args.start)
        return start, (dt.date.fromisoformat(args.end) if args.end else start)
    raise SystemExit("нужен либо --from, либо --recent")


def _wikis(arg: str | None) -> list[str]:
    raw = arg or os.environ.get("TS_WIKIS", "ruwiki,enwiki")
    return [w.strip() for w in raw.split(",") if w.strip()]


def cmd_ingest(args) -> int:
    start, end = _days(args)
    with open_db(args.db) as db:
        db.init_schema()
        for name in _wikis(args.wiki):
            spec = wikis.get(name)
            api = Api(spec.host)
            for day in pipeline.daterange(start, end):
                r = pipeline.ingest_day(
                    db, spec, api, day, with_revisions=not args.no_revisions,
                    refresh=args.refresh, refresh_changed=args.refresh_changed,
                    with_topics=not args.no_topics,
                )
                print(f"{spec.dbname:7s} {r['day']}  номинаций {r['nominations']:>3}  реплик {r['comments']:>4}  "
                      f"правок {r['revisions']:>4}  тем {r['topics']:>4}  пропущено {r['skipped']}")
    return 0


def cmd_state(args) -> int:
    with open_db(args.db) as db:
        db.init_schema()
        for name in _wikis(args.wiki):
            spec = wikis.get(name)
            n = pipeline.refresh_states(db, spec, Api(spec.host))
            print(f"{spec.dbname:7s} судьба пересчитана для {n} страниц")
    return 0


def cmd_quality(args) -> int:
    ok_all = True
    since = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=args.window)
    with open_db(args.db) as db:
        db.init_schema()
        for name in _wikis(args.wiki):
            metrics = quality.compute(db, name, since)
            quality.store(db, name, metrics)
            ok_all &= quality.report(name, metrics)
    return 0 if ok_all else 1


def cmd_daily(args) -> int:
    args.start = args.end = None
    args.refresh = False
    args.refresh_changed = True
    args.no_revisions = False
    args.no_topics = False
    cmd_ingest(args)
    cmd_state(args)
    return cmd_quality(args)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="talk-snapshots")
    ap.add_argument("--db", default=None, help="файл SQLite или toolsdb:<база>")
    ap.add_argument("--wiki", default=None, help="раздел(ы) через запятую; по умолчанию TS_WIKIS")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingest", help="загрузить обсуждения за дни")
    p.add_argument("--from", dest="start")
    p.add_argument("--to", dest="end")
    p.add_argument("--recent", type=int, help="последние N дней, считая сегодняшний")
    p.add_argument("--no-revisions", action="store_true")
    p.add_argument("--no-topics", action="store_true")
    p.add_argument("--refresh", action="store_true", help="перезалить дни заново")
    p.add_argument("--refresh-changed", action="store_true",
                   help="перечитать только те страницы, что менялись на вики")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("state", help="пересчитать судьбу страниц по журналам")
    p.set_defaults(func=cmd_state)

    p = sub.add_parser("quality", help="метрики качества и пороги")
    p.add_argument("--window", type=int, default=60, help="дней назад для метрик")
    p.set_defaults(func=cmd_quality)

    p = sub.add_parser("daily", help="ingest --recent N --refresh-changed + state + quality")
    p.add_argument("--recent", type=int, default=int(os.environ.get("TS_RECENT_DAYS", "21")))
    p.add_argument("--window", type=int, default=60)
    p.set_defaults(func=cmd_daily)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
