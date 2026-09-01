"""Агрегаты для витрины — из таблиц базы, без обращения к вики.

Витрина показывает три разных вещи и не смешивает их:
* судьба страницы (page_state) — что реально случилось по журналам;
* исход обсуждения (discussion_outcome) — что решили люди;
* «ещё обсуждается» — страница есть, итога нет, номинация свежая.

Всё считается в Python по нескольким широким выборкам: так запросы одинаковы
для SQLite и MariaDB, а объём (десятки тысяч строк на раздел) держится в секундах.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter, defaultdict

from .db import DB

OPEN_DAYS = 14          # моложе — «обсуждается»; старше без итога и судьбы — «висит»
DELAY_BUCKETS = ((1, "<1d"), (7, "1-7d"), (14, "8-14d"), (30, "15-30d"), (10**6, ">30d"))
CPN_BUCKETS = ((0, "0"), (2, "1-2"), (5, "3-5"), (10, "6-10"), (20, "11-20"), (10**6, ">20"))
LIFECYCLE = ("discussing", "hanging", "kept", "deleted", "redirect", "moved", "recreated", "missing")


def _bucket(value: float, buckets) -> str:
    for limit, name in buckets:
        if value <= limit:
            return name
    return buckets[-1][1]


def _iso(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_wiki(db: DB, spec, today: dt.date | None = None) -> dict:
    today = today or dt.datetime.now(dt.UTC).date()
    w = spec.dbname
    noms = db.execute("SELECT id, day, kind, n_comments FROM nominations WHERE wiki = ?", (w,)).fetchall()
    if not noms:
        return {"empty": True, "label": spec.label or w}
    pages = db.execute("SELECT nomination_id, ns, title FROM nomination_pages WHERE wiki = ?", (w,)).fetchall()
    states = {
        (ns, title): (state, _iso(deleted_at), reason_class, reason_code)
        for ns, title, state, deleted_at, reason_class, reason_code in db.execute(
            "SELECT ns, title, state, deleted_at, reason_class, reason_code FROM page_state WHERE wiki = ?", (w,)
        ).fetchall()
    }
    outcomes = db.execute(
        "SELECT nomination_id, page, kind, closer FROM discussion_outcome WHERE wiki = ?", (w,)
    ).fetchall()
    comments = db.execute(
        "SELECT nomination_id, author, ts, vote, is_bot, is_outcome FROM comments WHERE wiki = ?", (w,)
    ).fetchall()

    nom_day = {nid: dt.date.fromisoformat(day) for nid, day, _, _ in noms if day}
    nom_kind = {nid: kind for nid, _, kind, _ in noms}
    out_by_nom: dict[int, dict[str | None, str]] = defaultdict(dict)
    closers: Counter = Counter()
    for nid, page, kind, closer in outcomes:
        out_by_nom[nid][page or None] = kind
        if closer:
            closers[closer] += 1

    # --- жизненный цикл по страницам-статьям -------------------------------------------
    life_week: dict[str, Counter] = defaultdict(Counter)
    life_total: Counter = Counter()
    delay: Counter = Counter()
    reasons: Counter = Counter()
    articles = 0
    for nid, ns, title in pages:
        if ns != 0 or nid not in nom_day:
            continue
        articles += 1
        day = nom_day[nid]
        state, deleted_at, rclass, rcode = states.get((ns, title), ("missing", None, None, None))
        outs = out_by_nom.get(nid, {})
        okind = outs.get(title) or outs.get(None)
        if state in ("deleted", "redirect", "moved", "recreated"):
            lc = state
            if state == "deleted" and deleted_at:
                delay[_bucket((deleted_at.date() - day).days, DELAY_BUCKETS)] += 1
                reasons[f"{rclass or 'other'}" + (f" {rcode}" if rcode else "")] += 1
        elif state == "missing":
            lc = "missing"
        elif okind:
            lc = "kept"
        elif (today - day).days <= OPEN_DAYS:
            lc = "discussing"
        else:
            lc = "hanging"
        week = (day - dt.timedelta(days=day.weekday())).isoformat()
        life_week[week][lc] += 1
        life_total[lc] += 1

    # --- обсуждение ---------------------------------------------------------------------
    people: dict[str, dict] = defaultdict(lambda: {"comments": 0, "noms": set()})
    votes: Counter = Counter()
    heat = [[0] * 24 for _ in range(7)]
    n_comments = 0
    for nid, author, ts, vote, is_bot, _is_outcome in comments:
        n_comments += 1
        if vote:
            votes[vote] += 1
        t = _iso(ts)
        if t:
            heat[t.weekday()][t.hour] += 1
        if author and not is_bot and not author.startswith("~"):
            people[author]["comments"] += 1
            people[author]["noms"].add(nid)
    top = sorted(people.items(), key=lambda kv: -kv[1]["comments"])[:15]
    cpn: Counter = Counter(_bucket(n, CPN_BUCKETS) for _, _, _, n in noms)
    kinds: Counter = Counter(nom_kind.values())
    okinds: Counter = Counter(kind for _, _, kind, _ in outcomes)

    # --- темы (только если у раздела задан паттерн) ---------------------------------------
    topic_state: dict[str, Counter] = {}
    if spec.topic_pattern:
        rx = re.compile(spec.topic_pattern)
        rows = db.execute(
            "SELECT nomination_id, value FROM topics WHERE wiki = ? AND source = 'category'", (w,)
        ).fetchall()
        page_of: dict[int, list[tuple[int, str]]] = defaultdict(list)
        for nid, ns, title in pages:
            page_of[nid].append((ns, title))
        seen: set[tuple[int, str]] = set()
        for nid, value in rows:
            m = rx.match(value)
            if not m or (nid, m.group(1)) in seen:
                continue
            seen.add((nid, m.group(1)))
            for ns, title in page_of.get(nid, ()):
                if ns != 0:
                    continue
                state = states.get((ns, title), ("missing",))[0]
                outs = out_by_nom.get(nid, {})
                lc = state if state in ("deleted", "redirect", "moved", "recreated") else (
                    "kept" if (outs.get(title) or outs.get(None)) else "open")
                topic_state.setdefault(m.group(1), Counter())[lc] += 1
        topic_state = dict(sorted(topic_state.items(), key=lambda kv: -sum(kv[1].values()))[:12])

    return {
        "label": spec.label or w,
        "days": [min(nom_day.values()).isoformat(), max(nom_day.values()).isoformat()],
        "kpi": {
            "nominations": len(noms), "articles": articles, "comments": n_comments,
            "participants": len(people),
            "share_deleted": life_total["deleted"] / articles if articles else 0,
            "share_kept": life_total["kept"] / articles if articles else 0,
            "share_open": (life_total["discussing"] + life_total["hanging"]) / articles if articles else 0,
        },
        "kinds": dict(kinds),
        "lifecycle_total": dict(life_total),
        "lifecycle_by_week": {k: dict(v) for k, v in sorted(life_week.items())},
        "deletion_delay": dict(delay),
        "deletion_reasons": dict(reasons.most_common(12)),
        "outcome_kinds": dict(okinds.most_common()),
        "comments_per_nomination": dict(cpn),
        "votes": dict(votes.most_common(10)),
        "heatmap": heat,
        "top_participants": [
            {"user": a, "comments": v["comments"], "nominations": len(v["noms"]), "closes": closers.get(a, 0)}
            for a, v in top
        ],
        "topic_state": {k: dict(v) for k, v in topic_state.items()},
    }


def build(db: DB, specs: list) -> dict:
    return {
        "generated": dt.datetime.now(dt.UTC).isoformat(timespec="minutes"),
        "wikis": {spec.dbname: build_wiki(db, spec) for spec in specs},
    }
