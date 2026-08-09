"""Создание и обновление схемы. Отдельный процесс: гоняется перед рестартом."""

from __future__ import annotations

from .db import open_db


def main() -> None:
    with open_db() as db:
        db.init_schema()
        print("схема применена:", db.flavour)


if __name__ == "__main__":
    main()
