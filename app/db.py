"""Хранилище: SQLite при локальной разработке, Toolsdb на Toolforge.

Различие спрятано в одном месте — плейсхолдеры и типы. Схема одна, чтобы
локальный прогон и продовый работали с одинаковыми запросами.

У каждой таблицы есть колонка wiki: разделы живут в одной базе, и любой
запрос витрины — это GROUP BY wiki, а не отдельная база на раздел.
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
        kind        VARCHAR(16),
        source_page VARCHAR(255),
        UNIQUE {uniq_noms} (wiki, page_id, title)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nomination_pages (
        nomination_id BIGINT       NOT NULL,
        wiki          VARCHAR(32)  NOT NULL,
        ns            INT          NOT NULL,
        title         VARCHAR(255) NOT NULL,
        resolved_by   VARCHAR(32),
        PRIMARY KEY (nomination_id, ns, title)
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
        page          VARCHAR(255),
        section       VARCHAR(255),
        UNIQUE {uniq_comments} (nomination_id, idx)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS discussion_outcome (
        nomination_id BIGINT       NOT NULL,
        wiki          VARCHAR(32)  NOT NULL,
        page          VARCHAR(255) NOT NULL,
        kind          VARCHAR(16)  NOT NULL,
        closer        VARCHAR(255),
        closed_at     VARCHAR(32),
        source        VARCHAR(16),
        raw           VARCHAR(255),
        PRIMARY KEY (nomination_id, page)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS page_state (
        wiki          VARCHAR(32)  NOT NULL,
        ns            INT          NOT NULL,
        title         VARCHAR(255) NOT NULL,
        state         VARCHAR(16)  NOT NULL,
        deleted_at    VARCHAR(32),
        deleted_by    VARCHAR(255),
        reason_class  VARCHAR(16),
        reason_code   VARCHAR(16),
        reason_raw    VARCHAR(500),
        moved_to      VARCHAR(255),
        checked_at    VARCHAR(32)  NOT NULL,
        PRIMARY KEY (wiki, ns, title)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS topics (
        nomination_id BIGINT       NOT NULL,
        wiki          VARCHAR(32)  NOT NULL,
        ns            INT          NOT NULL,
        title         VARCHAR(255) NOT NULL,
        source        VARCHAR(24)  NOT NULL,
        value         VARCHAR(255) NOT NULL,
        taken_at      VARCHAR(32)  NOT NULL,
        PRIMARY KEY (nomination_id, ns, title, source, value)
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
    """
    CREATE TABLE IF NOT EXISTS quality_runs (
        id        {pk},
        run_at    VARCHAR(32)  NOT NULL,
        wiki      VARCHAR(32)  NOT NULL,
        metric    VARCHAR(40)  NOT NULL,
        value     DOUBLE,
        threshold DOUBLE,
        ok        {bool_t}     NOT NULL
    )
    """,
    "CREATE INDEX {ine} idx_revisions_actor ON revisions (actor)",
    "CREATE INDEX {ine} idx_revisions_section ON revisions (wiki, page_title, section)",
    "CREATE INDEX {ine} idx_comments_author ON comments (author)",
    "CREATE INDEX {ine} idx_comments_ts ON comments (ts)",
    "CREATE INDEX {ine} idx_noms_day ON nominations (wiki, day)",
    "CREATE INDEX {ine} idx_pages_state ON page_state (wiki, state)",
]

#: колонки, добавленные после первого деплоя: применяются к уже существующим таблицам
MIGRATIONS = [
    "ALTER TABLE nominations ADD COLUMN kind VARCHAR(16)",
    "ALTER TABLE nominations ADD COLUMN source_page VARCHAR(255)",
    "ALTER TABLE comments ADD COLUMN page VARCHAR(255)",
    "ALTER TABLE comments ADD COLUMN section VARCHAR(255)",
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

    def upsert(self, query: str, keys: tuple[str, ...], cols: tuple[str, ...]) -> str:
        """INSERT … ON CONFLICT/DUPLICATE — обновить всё, кроме ключей."""
        upd = ", ".join(f"{c} = {'excluded.' if self.flavour == 'sqlite' else 'VALUES('}{c}{'' if self.flavour == 'sqlite' else ')'}" for c in cols if c not in keys)
        if self.flavour == "sqlite":
            return f"{query} ON CONFLICT ({', '.join(keys)}) DO UPDATE SET {upd}"
        return f"{query} ON DUPLICATE KEY UPDATE {upd}"

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
        for stmt in MIGRATIONS:
            try:
                self.execute(stmt)
            except Exception as exc:
                if "duplicate" not in str(exc).lower():
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
