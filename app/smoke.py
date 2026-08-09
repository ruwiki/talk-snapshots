"""Проверка после деплоя: гоняется джобом на Toolforge, а не в GitHub Actions.

В CI такое не проверить — ни реплик, ни Toolsdb снаружи Cloud VPS нет.
Ненулевой код возврата означает, что раскатывать дальше нельзя.
"""

from __future__ import annotations

import sys

from .api import Api
from .db import open_db
from . import revisions as revs
from . import wikis


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'ok ' if ok else 'СБОЙ'}] {label}{(' — ' + detail) if detail else ''}")
    return ok


def main() -> int:
    results = []

    with open_db() as db:
        db.init_schema()
        n_noms = db.execute("SELECT COUNT(*) FROM nominations").fetchone()[0]
        n_comments = db.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
        n_revs = db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0]
        results.append(check("база отвечает и схема на месте", True,
                             f"номинаций {n_noms}, реплик {n_comments}, правок {n_revs}"))

    wiki = wikis.RUWIKI
    api = Api(wiki.host)
    from .threads import fetch_page_threads

    noms = fetch_page_threads(api, wiki, page="Википедия:К удалению/1 июля 2026")
    results.append(check("DiscussionTools отдаёт треды", bool(noms), f"номинаций {len(noms)}"))

    if revs.replicas_available():
        results.append(check("креды реплик на месте", True))
    elif revs.on_toolforge():
        results.append(check("креды реплик на месте", False,
                             "на Toolforge их обязана подставлять платформа"))
    else:
        print("[проп] реплики — запуск вне Toolforge, проверять нечего")
    if revs.replicas_available():
        rows = revs.fetch(wiki, "Википедия:К удалению/1 июля 2026")
        tagged = sum(1 for r in rows if r.added_comment)
        results.append(check("история правок читается", bool(rows),
                             f"правок {len(rows)}, из них с тегом реплики {tagged}"))

    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
