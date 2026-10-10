"""Снимок темы в момент номинации.

После удаления категорию статьи узнать негде: строки categorylinks стираются,
текст в реплики не попадает, сайтлинки Викиданных снимают боты. Единственный
момент, когда тема доступна, — пока статья жива, то есть в дни обсуждения.
Джоба ходит каждый день, значит снимок бесплатен.

Источники: категории самой страницы, её элемент Викиданных (page_props) и
категории страницы обсуждения (в англовики там DELSORT — «AfD debates (X)»).

Для элемента Викиданных тут же снимаются P31 («это экземпляр») и P106 (род
занятий, если это человек): после удаления статьи элемент без других
сайтлинков тоже удаляют, а классы (Q5, Q4830453 «бизнес»…) остаются навсегда,
поэтому хранится QID класса. Замер 09.10.2026: в раскрытом платном участии
организации — 28 % против ≈ 0 % в случайной выборке, то есть тема — главный
признак коммерческой правки (toolforge/30, раздел 8).
"""

from __future__ import annotations

import logging
from itertools import batched

from ..api import Api
from . import revisions as revs

log = logging.getLogger(__name__)

WIKIDATA_HOST = "www.wikidata.org"
CLAIMS = ("P31", "P106")
_wikidata: Api | None = None


def wikidata_api() -> Api:
    """Один клиент Викиданных на процесс: сессия и TLS переиспользуются между страницами и днями."""
    global _wikidata
    if _wikidata is None:
        _wikidata = Api(WIKIDATA_HOST, maxlag=None)
    return _wikidata

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


def snapshot(
    spec, refs: list[tuple[int, str]], api: Api | None = None, wikidata: Api | None = None
) -> list[tuple[int, str, str, str]]:
    """→ [(ns, title, source, value)], source ∈ {category, wikibase_item, P31, P106}."""
    if not refs:
        return []
    if revs.replicas_available():
        rows = _from_replica(spec, refs)
    else:
        rows = _from_api(spec, refs, api or Api(spec.host))
    return rows + claims(rows, wikidata)


def claims(rows: list[tuple[int, str, str, str]], wikidata: Api | None = None) -> list[tuple[int, str, str, str]]:
    """По строкам wikibase_item — строки (ns, title, P31|P106, QID значения).

    Любой сбой Викиданных — предупреждение в лог и пустой список: снимок категорий
    и элемента уже снят, терять из-за него весь день ingest нельзя.
    """
    items = [(ns, t, q) for ns, t, source, q in rows if source == "wikibase_item"]
    if not items:
        return []
    found: dict[str, dict[str, list[str]]] = {}
    try:
        wd = wikidata or wikidata_api()
        for chunk in batched(sorted({q for _, _, q in items}), 50, strict=False):
            data = wd.get(action="wbgetentities", ids="|".join(chunk), props="claims")
            if "error" in data:
                log.warning("wikidata %s: %s (%d id)", data["error"].get("code"), data["error"].get("info"), len(chunk))
                continue
            for qid, ent in data.get("entities", {}).items():
                found[qid] = {prop: _best_rank((ent.get("claims") or {}).get(prop, [])) for prop in CLAIMS}
    except Exception as exc:  # noqa: BLE001 — сеть, JSON, формат ответа: всё одинаково не повод ронять день
        log.warning("wikidata claims skipped: %s", exc)
        return []
    out = []
    for ns, t, q in items:
        for prop in CLAIMS:
            for value in found.get(q, {}).get(prop, []):
                out.append((ns, t, prop, value))
    return out


def _best_rank(statements: list[dict]) -> list[str]:
    """Значения-сущности с лучшим рангом (как «truthy» в Викиданных): preferred, если есть, иначе normal."""
    by_rank: dict[str, list[str]] = {"preferred": [], "normal": []}
    for s in statements:
        value = ((s.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        rank = s.get("rank", "normal")
        if isinstance(value, dict) and "id" in value and rank in by_rank:
            by_rank[rank].append(value["id"])
    return list(dict.fromkeys(by_rank["preferred"] or by_rank["normal"]))


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
