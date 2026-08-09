"""Отчёты по загруженным обсуждениям.

Часть метрик считается по репликам, часть — только по истории правок.
Второе важнее: правка в чужой секции без собственной реплики — это
подведение итога, перенос или вмешательство в чужой текст, и в тексте
обсуждения такого следа нет.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict

from .db import DB, open_db


def overview(db: DB) -> None:
    rows = db.execute(
        """SELECT wiki, COUNT(DISTINCT id) FROM nominations GROUP BY wiki"""
    ).fetchall()
    print("номинаций по разделам:", ", ".join(f"{w}: {n}" for w, n in rows))
    rows = db.execute(
        """SELECT wiki, COUNT(*), COUNT(DISTINCT author) FROM comments
           WHERE is_bot = 0 GROUP BY wiki"""
    ).fetchall()
    for wiki, n, authors in rows:
        print(f"{wiki}: реплик {n}, участников {authors}")
    rows = db.execute(
        """SELECT wiki, COUNT(*), SUM(CASE WHEN vote IS NOT NULL THEN 1 ELSE 0 END)
           FROM comments GROUP BY wiki"""
    ).fetchall()
    for wiki, n, voted in rows:
        share = (voted or 0) / n * 100 if n else 0
        print(f"{wiki}: доля реплик с формальной позицией {share:.1f}%")
    rows = db.execute("SELECT wiki, COUNT(*) FROM revisions GROUP BY wiki").fetchall()
    print("правок в истории:", ", ".join(f"{w}: {n}" for w, n in rows))


def top_participants(db: DB, limit: int = 20) -> None:
    rows = db.execute(
        """SELECT wiki, author, COUNT(*) c, COUNT(DISTINCT nomination_id) noms,
                  SUM(is_outcome) outcomes
             FROM comments
            WHERE is_bot = 0 AND author IS NOT NULL
            GROUP BY wiki, author ORDER BY c DESC"""
    ).fetchall()
    print(f"{'раздел':<8} {'участник':<28} {'реплик':>7} {'номинаций':>10} {'итогов':>7}")
    for wiki, author, c, noms, outcomes in rows[:limit]:
        print(f"{wiki:<8} {author[:28]:<28} {c:>7} {noms:>10} {outcomes or 0:>7}")


def reply_edges(db: DB, limit: int = 20) -> None:
    """Кто кому отвечает: ребро графа взаимодействия."""
    rows = db.execute(
        """SELECT c.wiki, p.author AS dst, c.author AS src, COUNT(*) n
             FROM comments c
             JOIN comments p
               ON p.nomination_id = c.nomination_id AND p.idx = c.parent_idx
            WHERE c.parent_idx IS NOT NULL AND c.is_bot = 0 AND p.is_bot = 0
              AND c.author IS NOT NULL AND p.author IS NOT NULL AND c.author <> p.author
            GROUP BY c.wiki, dst, src ORDER BY n DESC"""
    ).fetchall()
    print(f"{'раздел':<8} {'отвечает':<26} → {'кому':<26} {'раз':>5}")
    for wiki, dst, src, n in rows[:limit]:
        print(f"{wiki:<8} {src[:26]:<26} → {dst[:26]:<26} {n:>5}")


def co_participation(db: DB, limit: int = 20) -> None:
    """Кто с кем встречается в одних и тех же номинациях."""
    rows = db.execute(
        """SELECT wiki, nomination_id, author FROM comments
            WHERE is_bot = 0 AND author IS NOT NULL"""
    ).fetchall()
    by_nom: dict[tuple, set] = defaultdict(set)
    for wiki, nom_id, author in rows:
        by_nom[(wiki, nom_id)].add(author)
    pairs: Counter = Counter()
    for (wiki, _), authors in by_nom.items():
        ordered = sorted(authors)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                pairs[(wiki, a, b)] += 1
    print(f"{'раздел':<8} {'пара':<52} {'номинаций вместе':>17}")
    for (wiki, a, b), n in pairs.most_common(limit):
        print(f"{wiki:<8} {a[:24] + ' / ' + b[:24]:<52} {n:>17}")


def closers(db: DB, limit: int = 15) -> None:
    """Кто подводит итоги — видно по репликам в секции «Итог»."""
    rows = db.execute(
        """SELECT wiki, author, COUNT(*) n FROM comments
            WHERE is_outcome = 1 AND is_bot = 0 AND author IS NOT NULL
            GROUP BY wiki, author ORDER BY n DESC"""
    ).fetchall()
    print(f"{'раздел':<8} {'подводящий итоги':<30} {'итогов':>7}")
    for wiki, author, n in rows[:limit]:
        print(f"{wiki:<8} {author[:30]:<30} {n:>7}")


def silent_editors(db: DB, limit: int = 15) -> None:
    """Правил секцию, но не оставил в ней ни одной реплики.

    Ровно тот случай, ради которого нужна история правок: в тексте
    обсуждения этих людей не видно вообще.
    """
    revs = db.execute(
        """SELECT wiki, actor, section FROM revisions
            WHERE section IS NOT NULL AND section <> ''"""
    ).fetchall()
    spoke = {
        (w, a, t)
        for w, a, t in db.execute(
            """SELECT c.wiki, c.author, n.title FROM comments c
                 JOIN nominations n ON n.id = c.nomination_id
                WHERE c.author IS NOT NULL"""
        ).fetchall()
    }
    silent: Counter = Counter()
    for wiki, actor, section in revs:
        if (wiki, actor, section) not in spoke:
            silent[(wiki, actor)] += 1
    print(f"{'раздел':<8} {'правил молча':<30} {'правок':>7}")
    for (wiki, actor), n in silent.most_common(limit):
        print(f"{wiki:<8} {actor[:30]:<30} {n:>7}")


def tag_breakdown(db: DB, limit: int = 12) -> None:
    """Чем именно правят: теги движка о способе внесения правки."""
    counter: Counter = Counter()
    for (wiki, tags) in db.execute("SELECT wiki, tags FROM revisions").fetchall():
        for tag in (tags or "").split(","):
            if tag:
                counter[(wiki, tag)] += 1
    print(f"{'раздел':<8} {'тег правки':<40} {'правок':>7}")
    for (wiki, tag), n in counter.most_common(limit):
        print(f"{wiki:<8} {tag[:40]:<40} {n:>7}")


REPORTS = {
    "overview": overview,
    "top": top_participants,
    "edges": reply_edges,
    "pairs": co_participation,
    "closers": closers,
    "silent": silent_editors,
    "tags": tag_breakdown,
}


def main() -> None:
    ap = argparse.ArgumentParser(description="отчёты по обсуждениям об удалении")
    ap.add_argument("--db", default=None)
    ap.add_argument("--report", default="overview", choices=sorted(REPORTS))
    args = ap.parse_args()
    with open_db(args.db) as db:
        REPORTS[args.report](db)


if __name__ == "__main__":
    main()
