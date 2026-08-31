"""История правок — второй источник, которого нет ни в тексте, ни в тредах.

Подпись оставляет след только когда человек пишет свою реплику. История
показывает и остальное: кто правил чужие слова, кто удалял, кто подводил итог,
кто переносил номинацию. Плюс теги движка: `discussiontools-added-comment`
стоит ровно на тех правках, которыми добавлена реплика, — это разметка от
MediaWiki, а не наша догадка.

Два бэкенда с одинаковым выходом: реплики баз на Toolforge (быстро, массово)
и API, когда код запущен вне Cloud VPS.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime

from ..api import Api
from ..models import Revision

SECTION = re.compile(r"^/\*\s*(.*?)\s*\*/\s*")

REPLICA_SQL = """
SELECT r.rev_id, a.actor_name, r.rev_timestamp, c.comment_text, r.rev_len,
       COALESCE(pr.rev_len, 0) AS parent_len
  FROM revision r
  JOIN page p    ON p.page_id = r.rev_page
  JOIN actor a   ON a.actor_id = r.rev_actor
  JOIN comment c ON c.comment_id = r.rev_comment_id
  LEFT JOIN revision pr ON pr.rev_id = r.rev_parent_id
 WHERE p.page_namespace = %s AND p.page_title = %s
 ORDER BY r.rev_timestamp
"""

TAGS_SQL = """
SELECT ct.ct_rev_id, ctd.ctd_name
  FROM change_tag ct
  JOIN change_tag_def ctd ON ctd.ctd_id = ct.ct_tag_id
 WHERE ct.ct_rev_id IN ({placeholders})
"""

#: канонические префиксы, понятные любой вики
CANONICAL_NS = {"Wikipedia": 4, "Project": 4, "Talk": 1, "User": 2, "User talk": 3,
                "Category": 14, "Template": 10, "File": 6}


def replicas_available() -> bool:
    """Есть ли доступ к репликам.

    Проверять надо креды, а не файл `~/replica.my.cnf`: образы build service
    запускаются без смонтированного NFS-дома, и файла там нет — зато
    TOOL_REPLICA_USER и TOOL_REPLICA_PASSWORD платформа подставляет сама.
    """
    return bool(os.environ.get("TOOL_REPLICA_USER") and os.environ.get("TOOL_REPLICA_PASSWORD"))


def on_toolforge() -> bool:
    return replicas_available() or bool(os.environ.get("TOOL_TOOLSDB_USER"))


def split_title(spec, title: str) -> tuple[int, str]:
    """`Википедия:К удалению/1 июля 2026` → (4, `К_удалению/1_июля_2026`)."""
    if ":" in title:
        prefix, rest = title.split(":", 1)
        ns = spec.locale.namespaces.get(prefix, CANONICAL_NS.get(prefix))
        if ns is not None:
            return ns, rest.replace(" ", "_")
    return 0, title.replace(" ", "_")


def replica_connect(spec):
    import pymysql

    return pymysql.connect(
        host=f"{spec.dbname}.analytics.db.svc.wikimedia.cloud",
        user=os.environ["TOOL_REPLICA_USER"],
        password=os.environ["TOOL_REPLICA_PASSWORD"],
        database=f"{spec.dbname}_p",
        charset="utf8mb4",
    )


def dec(value) -> str:
    return value.decode(errors="replace") if isinstance(value, bytes) else (value or "")


def _ts_from_mw(value: str | bytes) -> datetime:
    return datetime.strptime(dec(value), "%Y%m%d%H%M%S").replace(tzinfo=UTC)


def _section_of(summary: str) -> str | None:
    m = SECTION.match(summary or "")
    return m.group(1) if m else None


def from_replica(spec, title: str) -> list[Revision]:
    ns, db_title = split_title(spec, title)
    conn = replica_connect(spec)
    try:
        with conn.cursor() as cur:
            cur.execute(REPLICA_SQL, (ns, db_title))
            rows = cur.fetchall()
            tags: dict[int, list[str]] = {}
            if rows:
                ids = [r[0] for r in rows]
                for chunk in (ids[i:i + 500] for i in range(0, len(ids), 500)):
                    q = TAGS_SQL.format(placeholders=",".join(["%s"] * len(chunk)))
                    cur.execute(q, chunk)
                    for rev_id, tag in cur.fetchall():
                        tags.setdefault(rev_id, []).append(dec(tag))
    finally:
        conn.close()

    out = []
    for rev_id, actor, ts, summary, size, parent_size in rows:
        summary = dec(summary)
        out.append(
            Revision(
                rev_id=rev_id, page_title=title, wiki=spec.dbname, actor=dec(actor),
                ts=_ts_from_mw(ts), section=_section_of(summary), summary=summary,
                tags=tuple(tags.get(rev_id, ())),
                size_delta=int(size or 0) - int(parent_size or 0),
            )
        )
    return out


def from_api(api: Api, spec, title: str, limit: int = 500) -> list[Revision]:
    out: list[Revision] = []
    params = dict(
        action="query", prop="revisions", titles=title, rvlimit=limit,
        rvprop="ids|timestamp|user|comment|tags|size", rvdir="newer", rvslots="main",
    )
    for page in api.paged(**params):
        for p in page.get("query", {}).get("pages", []):
            prev_size = 0
            for rev in p.get("revisions", []):
                summary = rev.get("comment", "") or ""
                size = rev.get("size", 0) or 0
                out.append(
                    Revision(
                        rev_id=rev["revid"], page_title=title, wiki=spec.dbname,
                        actor=rev.get("user", ""),
                        ts=datetime.fromisoformat(rev["timestamp"].replace("Z", "+00:00")),
                        section=_section_of(summary), summary=summary,
                        tags=tuple(rev.get("tags", ())), size_delta=size - prev_size,
                    )
                )
                prev_size = size
    return out


def fetch(spec, title: str, api: Api | None = None) -> list[Revision]:
    """Реплика на Toolforge, API снаружи — выход одинаковый."""
    if replicas_available():
        return from_replica(spec, title)
    return from_api(api or Api(spec.host), spec, title)


def latest_revid(spec, title: str, api: Api | None = None) -> int | None:
    """Последняя ревизия страницы — дешёвый признак «страница менялась»."""
    if replicas_available():
        ns, db_title = split_title(spec, title)
        conn = replica_connect(spec)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT page_latest FROM page WHERE page_namespace=%s AND page_title=%s",
                    (ns, db_title),
                )
                row = cur.fetchone()
                return int(row[0]) if row else None
        finally:
            conn.close()
    data = (api or Api(spec.host)).get(action="query", prop="info", titles=title)
    for p in data.get("query", {}).get("pages", []):
        if "lastrevid" in p:
            return int(p["lastrevid"])
    return None
