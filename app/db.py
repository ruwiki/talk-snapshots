"""Хранилище: SQLite при локальной разработке, Toolsdb на Toolforge.

Различие спрятано в одном месте — плейсхолдеры и типы. Схема одна, чтобы
локальный прогон и продовый работали с одинаковыми запросами.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS pages (
        id          {pk},
        wiki        VARCHAR(32)  NOT NULL,
        title       VARCHAR(255) NOT NULL,
        day         VARCHAR(10),
        revid       BIGINT,
        fetched_at  VARCHAR(32)  NOT NULL,
        UNIQUE {uniq_pages} (wiki, title)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nominations (
        id          {pk},
        page_id     BIGINT       NOT NULL,
        wiki        VARCHAR(32)  NOT NULL,
        day         VARCHAR(10),
        title       VARCHAR(255) NOT NULL,
        struck      {bool_t}     NOT NULL,
        opened_at   VARCHAR(32),
        closed_at   VARCHAR(32),
        n_comments  INT          NOT NULL,
        UNIQUE {uniq_noms} (wiki, page_id, title)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS comments (
        id            {pk},
        nomination_id BIGINT       NOT NULL,
        wiki          VARCHAR(32)  NOT NULL,
        idx           INT          NOT NULL,
        author        VARCHAR(255),
        ts            VARCHAR(32),
        depth         INT          NOT NULL,
        parent_idx    INT,
        vote          VARCHAR(32),
        is_outcome    {bool_t}     NOT NULL,
        is_bot        {bool_t}     NOT NULL,
        text          {text_t},
        UNIQUE {uniq_comments} (nomination_id, idx)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS revisions (
        rev_id      BIGINT       NOT NULL,
        wiki        VARCHAR(32)  NOT NULL,
        page_title  VARCHAR(255) NOT NULL,
        actor       VARCHAR(255) NOT NULL,
        ts          VARCHAR(32)  NOT NULL,
        section     VARCHAR(255),
        summary     VARCHAR(500),
        tags        VARCHAR(500),
        size_delta  INT,
        PRIMARY KEY (wiki, rev_id)
    )
    """,
    "CREATE INDEX {ine} idx_revisions_actor ON revisions (actor)",
    "CREATE INDEX {ine} idx_revisions_section ON revisions (wiki, page_title, section)",
    "CREATE INDEX {ine} idx_comments_author ON comments (author)",
    "CREATE INDEX {ine} idx_comments_ts ON comments (ts)",
    "CREATE INDEX {ine} idx_noms_day ON nominations (wiki, day)",
]


@dataclass
class DB:
    conn: object
    flavour: str  # sqlite | mysql

    @property
    def ph(self) -> str:
        return "?" if self.flavour == "sqlite" else "%s"

    def sql(self, query: str) -> str:
        return query if self.flavour == "sqlite" else query.replace("?", "%s")

    def ignore(self, query: str) -> str:
        """Повторная загрузка того же дня не должна падать на дубликатах."""
        if self.flavour == "sqlite":
            return query.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)
        return query.replace("INSERT INTO", "INSERT IGNORE INTO", 1)

    def execute(self, query: str, args: tuple = ()):
        cur = self.conn.cursor()
        cur.execute(self.sql(query), args)
        return cur

    def executemany(self, query: str, rows: list[tuple]):
        if not rows:
            return
        cur = self.conn.cursor()
        cur.executemany(self.sql(query), rows)
        return cur

    def commit(self) -> None:
        self.conn.commit()

    def init_schema(self) -> None:
        if self.flavour == "sqlite":
            fmt = dict(
                pk="INTEGER PRIMARY KEY AUTOINCREMENT", bool_t="INTEGER",
                text_t="TEXT", ine="IF NOT EXISTS",
                uniq_pages="", uniq_noms="", uniq_comments="",
            )
        else:
            fmt = dict(
                pk="BIGINT AUTO_INCREMENT PRIMARY KEY", bool_t="TINYINT",
                text_t="MEDIUMTEXT", ine="IF NOT EXISTS",
                uniq_pages="u_page", uniq_noms="u_nom", uniq_comments="u_comment",
            )
        for stmt in SCHEMA:
            try:
                self.execute(stmt.format(**fmt))
            except Exception as exc:  # индекс уже есть — MariaDB до 10.6 не знает IF NOT EXISTS
                if "duplicate" not in str(exc).lower() and "exists" not in str(exc).lower():
                    raise
        self.commit()


def connect(dsn: str | None = None) -> DB:
    """dsn: путь к файлу SQLite либо `toolsdb:<имя базы>`.

    На Toolforge креды приезжают в окружении сами — TOOL_TOOLSDB_USER
    и TOOL_TOOLSDB_PASSWORD подставляет платформа, руками их класть не надо.
    """
    dsn = dsn or os.environ.get("TS_DB", "talk-snapshots.sqlite")
    if dsn.startswith("toolsdb:"):
        import pymysql

        user = os.environ["TOOL_TOOLSDB_USER"]
        conn = pymysql.connect(
            host=os.environ.get("TS_TOOLSDB_HOST", "tools.db.svc.wikimedia.cloud"),
            user=user,
            password=os.environ["TOOL_TOOLSDB_PASSWORD"],
            database=dsn.split(":", 1)[1] or f"{user}__talk_snapshots",
            charset="utf8mb4",
            autocommit=False,
        )
        return DB(conn, "mysql")
    conn = sqlite3.connect(dsn)
    conn.execute("PRAGMA journal_mode=WAL")
    return DB(conn, "sqlite")


@contextmanager
def open_db(dsn: str | None = None):
    db = connect(dsn)
    try:
        yield db
    finally:
        db.conn.close()
