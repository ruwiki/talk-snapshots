"""Создание и обновление схемы. Отдельный процесс: гоняется перед рестартом."""

from __future__ import annotations

from .core.pipeline import migrate_topics
from .db import open_db


def main() -> None:
    with open_db() as db:
        db.init_schema()
        print("схема применена:", db.flavour)
        n = migrate_topics(db)
        if n:
            print("снимки тем перенесены в page_topics:", n)


if __name__ == "__main__":
    main()
