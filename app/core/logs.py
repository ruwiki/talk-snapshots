"""Счётчики из `logging` — исход, а не обсуждение.

Парсер обсуждений даёт вход (номинация, реплики, итог текстом); журнал — исход
(удалено / восстановлено / переименовано / защищено). Здесь считаются записи
журнала по дням, без привязки к номинациям: это общий фон, на котором видно,
какая доля удалений вообще проходит через обсуждение.

Канал удаления — по строке причины (`spec.log_channels`); пространство имён —
по `ns_groups`. Считаются записи, не страницы: удалённая дважды считается дважды.
Только реплики: вне Toolforge функция возвращает пусто и ничего не ломает.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter

from . import revisions as revs

KINDS = ("delete", "restore", "move", "protect")

DELETE_SQL = """
SELECT LEFT(log_timestamp, 8), log_namespace, log_action, comment_text
FROM logging JOIN comment_logging ON log_comment_id = comment_id
WHERE log_type = 'delete' AND log_action IN ('delete', 'restore')
  AND log_timestamp >= %s AND log_timestamp < %s
"""

PLAIN_SQL = """
SELECT LEFT(log_timestamp, 8), log_namespace, log_type, COUNT(*)
FROM logging
WHERE ((log_type = 'move' AND log_action = 'move') OR (log_type = 'protect' AND log_action = 'protect'))
  AND log_timestamp >= %s AND log_timestamp < %s
GROUP BY 1, 2, 3
"""


def _day(ts) -> str:
    s = revs.dec(ts)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def count(spec, start: dt.date, end: dt.date) -> list[tuple]:
    """Строки (day, kind, ns_group, channel, n) за [start, end]; пусто без реплик."""
    if not revs.replicas_available():
        return []
    ch = spec.log_channels
    a = start.strftime("%Y%m%d") + "000000"
    b = (end + dt.timedelta(days=1)).strftime("%Y%m%d") + "000000"
    acc: Counter = Counter()
    conn = revs.replica_connect(spec)
    try:
        with conn.cursor() as cur:
            cur.execute(DELETE_SQL, (a, b))
            for ts, ns, action, comment in cur.fetchall():
                kind = revs.dec(action)
                chan = ch.classify(revs.dec(comment)) if kind == "delete" else "-"
                acc[(_day(ts), kind, ch.group(int(ns)), chan)] += 1
            cur.execute(PLAIN_SQL, (a, b))
            for ts, ns, kind, n in cur.fetchall():
                acc[(_day(ts), revs.dec(kind), ch.group(int(ns)), "-")] += int(n)
    finally:
        conn.close()
    return [(*k, n) for k, n in sorted(acc.items())]


def store(db, spec, start: dt.date, end: dt.date) -> int:
    rows = count(spec, start, end)
    if not rows:
        return 0
    w = spec.dbname
    db.execute("DELETE FROM log_counts WHERE wiki = ? AND day >= ? AND day <= ?",
               (w, start.isoformat(), end.isoformat()))
    db.executemany(db.ignore("INSERT INTO log_counts (wiki, day, kind, ns_group, channel, n) VALUES (?, ?, ?, ?, ?, ?)"),
                   [(w, *r) for r in rows])
    db.commit()
    return len(rows)
