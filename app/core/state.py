"""Судьба страницы — из журналов, одинаково для любого раздела.

Это не исход обсуждения (он в core/outcome.py, и пишут его люди по-разному),
а факт из базы: страница есть / перенаправление / удалена (когда, кем, с каким
основанием) / переименована / пересоздана. Схема таблиц page и logging одна
на всех вики, поэтому здесь нет ни одной ветки по разделу — только регулярка
классификации основания из спека.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from ..api import Api
from . import revisions as revs

DELETE_SQL = """
SELECT l.log_title, l.log_action, l.log_timestamp, a.actor_name, c.comment_text, l.log_params
  FROM logging l
  JOIN actor a ON a.actor_id = l.log_actor
  JOIN comment c ON c.comment_id = l.log_comment_id
 WHERE l.log_namespace = %s AND l.log_type IN ('delete', 'move')
   AND l.log_timestamp >= %s AND l.log_title IN ({ph})
 ORDER BY l.log_timestamp
"""

PAGE_SQL = "SELECT page_title, page_is_redirect FROM page WHERE page_namespace = %s AND page_title IN ({ph})"


@dataclass
class PageState:
    ns: int
    title: str
    #: exists | redirect | deleted | moved | recreated | missing
    state: str
    deleted_at: dt.datetime | None = None
    deleted_by: str | None = None
    reason_class: str | None = None
    reason_code: str | None = None
    reason_raw: str | None = None
    moved_to: str | None = None


def _db_title(title: str) -> str:
    return title.replace(" ", "_")


def _chunks(seq, n=300):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def page_states(spec, refs: list[tuple[int, str]], since: dt.date, api: Api | None = None) -> list[PageState]:
    """refs: (ns, title). since: с какой даты смотреть журнал (день номинации минус запас)."""
    if revs.replicas_available():
        return _from_replica(spec, refs, since)
    return _from_api(spec, refs, since, api or Api(spec.host))


def _fold(spec, ns: int, title: str, exists: dict, logs: dict) -> PageState:
    key = _db_title(title)
    events = logs.get(key, [])
    dels = [e for e in events if e[0] == "delete"]
    moves = [e for e in events if e[0] in ("move", "move_redir")]
    st = PageState(ns=ns, title=title, state="missing")
    if key in exists:
        st.state = "recreated" if dels else ("redirect" if exists[key] else "exists")
    elif dels:
        st.state = "deleted"
    elif moves:
        st.state = "moved"
    if dels:
        _, ts, actor, comment, _ = dels[-1]
        st.deleted_at, st.deleted_by, st.reason_raw = ts, actor, comment[:500]
        st.reason_class, st.reason_code = spec.reason.classify(comment)
    if moves and st.state == "moved":
        st.moved_to = moves[-1][4] or None
    return st


def _from_replica(spec, refs, since):
    conn = revs.replica_connect(spec)
    out: list[PageState] = []
    since_ts = since.strftime("%Y%m%d") + "000000"
    try:
        with conn.cursor() as cur:
            by_ns: dict[int, list[str]] = {}
            for ns, title in refs:
                by_ns.setdefault(ns, []).append(title)
            for ns, titles in by_ns.items():
                exists: dict[str, bool] = {}
                logs: dict[str, list] = {}
                for chunk in _chunks(sorted({_db_title(t) for t in titles})):
                    ph = ",".join(["%s"] * len(chunk))
                    cur.execute(PAGE_SQL.format(ph=ph), (ns, *chunk))
                    for t, r in cur.fetchall():
                        exists[revs.dec(t)] = bool(r)
                    cur.execute(DELETE_SQL.format(ph=ph), (ns, since_ts, *chunk))
                    for t, action, ts, actor, comment, params in cur.fetchall():
                        logs.setdefault(revs.dec(t), []).append(
                            (revs.dec(action), revs._ts_from_mw(ts), revs.dec(actor),
                             revs.dec(comment), _move_target(revs.dec(params)))
                        )
                for title in titles:
                    out.append(_fold(spec, ns, title, exists, logs))
    finally:
        conn.close()
    return out


def _move_target(params: str) -> str | None:
    # сериализованный PHP-массив: "4::target";s:NN:"Название"
    import re

    m = re.search(r'"4::target";s:\d+:"([^"]+)"', params or "")
    return m.group(1) if m else None


def _from_api(spec, refs, since, api: Api):
    """Снаружи Toolforge: существование пачками, журнал — по одной странице из отсутствующих."""
    out: list[PageState] = []
    by_ns: dict[int, list[str]] = {}
    for ns, title in refs:
        by_ns.setdefault(ns, []).append(title)
    for ns, titles in by_ns.items():
        full = {t: _full_title(spec, ns, t) for t in titles}
        exists: dict[str, bool] = {}
        for chunk in _chunks(list(full.values()), 50):
            data = api.get(action="query", prop="info", titles="|".join(chunk))
            for p in data.get("query", {}).get("pages", []):
                if "missing" not in p:
                    exists[_db_title(_strip_ns(p["title"]))] = "redirect" in p
        logs: dict[str, list] = {}
        for t in titles:
            if _db_title(t) in exists:
                continue
            data = api.get(action="query", list="logevents", letitle=full[t],
                           leprop="type|timestamp|user|comment|details", lelimit=20,
                           leend=since.isoformat() + "T00:00:00Z")
            for e in data.get("query", {}).get("logevents", []):
                if e.get("type") not in ("delete", "move"):
                    continue
                logs.setdefault(_db_title(t), []).append(
                    (e.get("action"), dt.datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")),
                     e.get("user", ""), e.get("comment", ""),
                     (e.get("params") or {}).get("target_title"))
                )
        for t in titles:
            out.append(_fold(spec, ns, t, exists, logs))
    return out


def _full_title(spec, ns: int, title: str) -> str:
    if ns == 0:
        return title
    for prefix, n in {**revs.CANONICAL_NS, **spec.locale.namespaces}.items():
        if n == ns:
            return f"{prefix}:{title}"
    return title


def _strip_ns(title: str) -> str:
    return title.split(":", 1)[1] if ":" in title else title
