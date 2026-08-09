"""История правок — второй источник, которого нет ни в тексте, ни в тредах.

Подпись оставляет след только когда человек пишет свою реплику. История
показывает и остальное: кто правил чужие слова, кто удалял, кто подводил итог,
кто переносил номинацию. Плюс теги движка: `discussiontools-added-comment`
стоит ровно на тех правках, которыми добавлена реплика, — это разметка от
MediaWiki, а не наша догадка.

Два бэкенда с одинаковым выходом: реплики баз на Toolforge (быстро, массово)
и API, когда кода запущен вне Cloud VPS.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from .api import Api
from .models import Revision
from .wikis import Wiki

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


def on_toolforge() -> bool:
    return os.path.exists(os.path.expanduser("~/replica.my.cnf"))


def _split_title(title: str) -> tuple[int, str]:
    """`Википедия:К удалению/1 июля 2026` → (4, `К_удалению/1_июля_2026`)."""
    ns_by_prefix = {
        "Википедия": 4, "Wikipedia": 4, "Обсуждение": 1, "Talk": 1,
        "Проект": 104, "Участник": 2, "User": 2,
    }
    if ":" in title:
        prefix, rest = title.split(":", 1)
        if prefix in ns_by_prefix:
            return ns_by_prefix[prefix], rest.replace(" ", "_")
    return 0, title.replace(" ", "_")


def _ts_from_mw(value: str | bytes) -> datetime:
    s = value.decode() if isinstance(value, bytes) else str(value)
    return datetime.strptime(s, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def _section_of(summary: str) -> str | None:
    m = SECTION.match(summary or "")
    return m.group(1) if m else None


def from_replica(wiki: Wiki, title: str) -> list[Revision]:
    import pymysql

    ns, db_title = _split_title(title)
    conn = pymysql.connect(
        host=f"{wiki.dbname}.analytics.db.svc.wikimedia.cloud",
        user=os.environ["TOOL_REPLICA_USER"],
        password=os.environ["TOOL_REPLICA_PASSWORD"],
        database=f"{wiki.dbname}_p",
        charset="utf8mb4",
    )
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
                        tags.setdefault(rev_id, []).append(
                            tag.decode() if isinstance(tag, bytes) else tag
                        )
    finally:
        conn.close()

    out = []
    for rev_id, actor, ts, summary, size, parent_size in rows:
        summary = summary.decode() if isinstance(summary, bytes) else (summary or "")
        actor = actor.decode() if isinstance(actor, bytes) else actor
        out.append(
            Revision(
                rev_id=rev_id,
                page_title=title,
                wiki=wiki.dbname,
                actor=actor,
                ts=_ts_from_mw(ts),
                section=_section_of(summary),
                summary=summary,
                tags=tuple(tags.get(rev_id, ())),
                size_delta=int(size or 0) - int(parent_size or 0),
            )
        )
    return out


def from_api(api: Api, wiki: Wiki, title: str, limit: int = 500) -> list[Revision]:
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
                        rev_id=rev["revid"],
                        page_title=title,
                        wiki=wiki.dbname,
                        actor=rev.get("user", ""),
                        ts=datetime.fromisoformat(rev["timestamp"].replace("Z", "+00:00")),
                        section=_section_of(summary),
                        summary=summary,
                        tags=tuple(rev.get("tags", ())),
                        size_delta=size - prev_size,
                    )
                )
                prev_size = size
    return out


def fetch(wiki: Wiki, title: str, api: Api | None = None) -> list[Revision]:
    """Реплика на Toolforge, API снаружи — выход одинаковый."""
    if on_toolforge():
        return from_replica(wiki, title)
    return from_api(api or Api(wiki.host), wiki, title)
