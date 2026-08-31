"""Снимок темы в момент номинации.

После удаления категорию статьи узнать негде: строки categorylinks стираются,
текст в реплики не попадает, сайтлинки Викиданных снимают боты. Единственный
момент, когда тема доступна, — пока статья жива, то есть в дни обсуждения.
Джоба ходит каждый день, значит снимок бесплатен.

Источники: категории самой страницы, её элемент Викиданных (page_props) и
категории страницы обсуждения (в англовики там DELSORT — «AfD debates (X)»).
"""

from __future__ import annotations

from ..api import Api
from . import revisions as revs

CATS_SQL = """
SELECT p.page_title, lt.lt_title
  FROM categorylinks cl
  JOIN page p ON p.page_id = cl.cl_from
  JOIN linktarget lt ON lt.lt_id = cl.cl_target_id
 WHERE lt.lt_namespace = 14 AND p.page_namespace = %s AND p.page_title IN ({ph})
"""
PROPS_SQL = """
SELECT p.page_title, pp.pp_value
  FROM page_props pp JOIN page p ON p.page_id = pp.pp_page
 WHERE pp.pp_propname = 'wikibase_item' AND p.page_namespace = %s AND p.page_title IN ({ph})
"""


def snapshot(spec, refs: list[tuple[int, str]], api: Api | None = None) -> list[tuple[int, str, str, str]]:
    """→ [(ns, title, source, value)], source ∈ {category, wikibase_item}."""
    if not refs:
        return []
    if revs.replicas_available():
        return _from_replica(spec, refs)
    return _from_api(spec, refs, api or Api(spec.host))


def _from_replica(spec, refs):
    out = []
    conn = revs.replica_connect(spec)
    try:
        with conn.cursor() as cur:
            by_ns: dict[int, list[str]] = {}
            for ns, t in refs:
                by_ns.setdefault(ns, []).append(t.replace(" ", "_"))
            for ns, titles in by_ns.items():
                for i in range(0, len(titles), 300):
                    chunk = titles[i:i + 300]
                    ph = ",".join(["%s"] * len(chunk))
                    cur.execute(CATS_SQL.format(ph=ph), (ns, *chunk))
                    for t, cat in cur.fetchall():
                        out.append((ns, revs.dec(t).replace("_", " "), "category", revs.dec(cat).replace("_", " ")))
                    cur.execute(PROPS_SQL.format(ph=ph), (ns, *chunk))
                    for t, q in cur.fetchall():
                        out.append((ns, revs.dec(t).replace("_", " "), "wikibase_item", revs.dec(q)))
    finally:
        conn.close()
    return out


def _from_api(spec, refs, api: Api):
    from .state import _full_title, _strip_ns

    out = []
    for ns in {r[0] for r in refs}:
        titles = [_full_title(spec, ns, t) for n, t in refs if n == ns]
        for i in range(0, len(titles), 50):
            chunk = titles[i:i + 50]
            params = dict(action="query", prop="categories|pageprops", ppprop="wikibase_item",
                          cllimit="max", titles="|".join(chunk))
            for data in api.paged(**params):
                for p in data.get("query", {}).get("pages", []):
                    t = _strip_ns(p["title"]) if ns else p["title"]
                    for c in p.get("categories", []):
                        out.append((ns, t, "category", _strip_ns(c["title"])))
                    q = (p.get("pageprops") or {}).get("wikibase_item")
                    if q:
                        out.append((ns, t, "wikibase_item", q))
    return out
