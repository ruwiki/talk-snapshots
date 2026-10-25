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

from .core import mismatch, revisions
from .db import DB

OPEN_DAYS = 14          # моложе — «обсуждается»; старше без итога и судьбы — «висит»
MONTH_DAYS = 30         # окно заглавной: номинации, открытые за последние 30 дней, считая сегодняшний
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


def month_start(today: dt.date) -> dt.date:
    return today - dt.timedelta(days=MONTH_DAYS - 1)


def _kpi(noms: int, articles: int, comments: int, participants: int, life: Counter) -> dict:
    return {
        "nominations": noms, "articles": articles, "comments": comments, "participants": participants,
        "share_deleted": life["deleted"] / articles if articles else 0,
        "share_kept": life["kept"] / articles if articles else 0,
        "share_open": (life["discussing"] + life["hanging"]) / articles if articles else 0,
    }


def build_wiki(db: DB, spec, today: dt.date | None = None) -> dict:
    today = today or dt.datetime.now(dt.UTC).date()
    since = month_start(today)
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
    life_month: Counter = Counter()
    articles_month = 0
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
        if day >= since:
            life_month[lc] += 1
            articles_month += 1

    # --- обсуждение ---------------------------------------------------------------------
    people: dict[str, dict] = defaultdict(lambda: {"comments": 0, "noms": set()})
    votes: Counter = Counter()
    heat = [[0] * 24 for _ in range(7)]
    n_comments = 0
    comments_month = 0
    people_month: set[str] = set()
    for nid, author, ts, vote, is_bot, _is_outcome in comments:
        n_comments += 1
        in_month = nid in nom_day and nom_day[nid] >= since
        comments_month += in_month
        if vote:
            votes[vote] += 1
        t = _iso(ts)
        if t:
            heat[t.weekday()][t.hour] += 1
        if author and not is_bot and not author.startswith("~"):
            people[author]["comments"] += 1
            people[author]["noms"].add(nid)
            if in_month:
                people_month.add(author)
    top = sorted(people.items(), key=lambda kv: -kv[1]["comments"])[:15]
    cpn: Counter = Counter(_bucket(n, CPN_BUCKETS) for _, _, _, n in noms)
    kinds: Counter = Counter(nom_kind.values())
    okinds: Counter = Counter(kind for _, _, kind, _ in outcomes)

    # --- темы (только если у раздела задан паттерн) ---------------------------------------
    topic_state: dict[str, Counter] = {}
    if spec.topic_pattern:
        rx = re.compile(spec.topic_pattern)
        # снимок лежит по странице: тема номинации — с её страниц и со страницы-номинации AfD (DELSORT)
        topics_of: dict[tuple[int, str], list[str]] = defaultdict(list)
        for ns, title, value in db.execute(
            "SELECT ns, title, value FROM page_topics WHERE wiki = ? AND source = 'category'", (w,)
        ).fetchall():
            m = rx.match(value)
            if m:
                topics_of[(ns, title)].append(m.group(1))
        page_of: dict[int, list[tuple[int, str]]] = defaultdict(list)
        for nid, ns, title in pages:
            page_of[nid].append((ns, title))
        source_of = {
            nid: revisions.split_title(spec, src)
            for nid, src in db.execute(
                "SELECT id, source_page FROM nominations WHERE wiki = ? AND source_page IS NOT NULL", (w,)
            ).fetchall()
        }
        for nid in page_of:
            refs = list(page_of[nid])
            if nid in source_of:
                ns, title = source_of[nid]
                refs.append((ns, title.replace("_", " ")))
            for topic in dict.fromkeys(t for ref in refs for t in topics_of.get(ref, ())):
                for ns, title in page_of[nid]:
                    if ns != 0:
                        continue
                    state = states.get((ns, title), ("missing",))[0]
                    outs = out_by_nom.get(nid, {})
                    lc = state if state in ("deleted", "redirect", "moved", "recreated") else (
                        "kept" if (outs.get(title) or outs.get(None)) else "open")
                    topic_state.setdefault(topic, Counter())[lc] += 1
        topic_state = dict(sorted(topic_state.items(), key=lambda kv: -sum(kv[1].values()))[:12])

    return {
        "label": spec.label or w,
        "days": [min(nom_day.values()).isoformat(), max(nom_day.values()).isoformat()],
        "kpi": _kpi(len(noms), articles, n_comments, len(people), life_total),
        # заглавная: номинации, открытые за последние MONTH_DAYS дней, и всё о них
        "month": {
            "since": since.isoformat(), "until": today.isoformat(),
            "kpi": _kpi(sum(d >= since for d in nom_day.values()), articles_month, comments_month,
                        len(people_month), life_month),
            "lifecycle_total": dict(life_month),
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


def build_logs(db: DB, spec, since: dt.date | None = None) -> dict | None:
    """Панель «из журналов»: удаления статей по каналам, по пространствам, restore/move/protect.

    Каналы, которых в вики нет (нет регулярки в spec.log_channels), отдаются в `absent`:
    витрина рисует их серым, а не пропускает — отсутствие процесса тоже сравнимо.
    """
    w = spec.dbname
    rows = db.execute("SELECT day, kind, ns_group, channel, n FROM log_counts WHERE wiki = ?", (w,)).fetchall()
    if since is not None:
        rows = [r for r in rows if r[0] >= since.isoformat()]
    if not rows:
        return None
    ch = spec.log_channels
    chans: Counter = Counter()
    ns: Counter = Counter()
    kinds: Counter = Counter()
    days = [min(r[0] for r in rows), max(r[0] for r in rows)]
    for _day, kind, ns_group, channel, n in rows:
        if kind == "delete":
            ns[ns_group] += n
            if ns_group == "article":
                chans[channel] += n
        kinds[kind] += n
    present = set(ch.present()) | {"other"}
    return {
        "days": days,
        "delete_channels": {c: chans.get(c, 0) for c in ch.ALL},
        "absent": [c for c in ch.ALL if c not in present],
        "delete_ns": {g: ns.get(g, 0) for g in ("article", "draft", "user", "other")},
        "has_draft": any(key == "draft" for _, key in ch.ns_groups),
        "kinds": {k: kinds.get(k, 0) for k in ("delete", "restore", "move", "protect")},
    }


def build(db: DB, specs: list, today: dt.date | None = None) -> dict:
    today = today or dt.datetime.now(dt.UTC).date()
    since = month_start(today)
    out = {
        "generated": dt.datetime.now(dt.UTC).isoformat(timespec="minutes"),
        "wikis": {spec.dbname: build_wiki(db, spec, today) for spec in specs},
    }
    for spec in specs:
        W = out["wikis"][spec.dbname]
        W["logs"] = build_logs(db, spec)
        W["logs_month"] = build_logs(db, spec, since)
        if not W.get("empty"):
            W["mismatches"] = mismatch.find(db, spec, limit=0)[1]
            W["month"]["mismatches"] = mismatch.find(db, spec, limit=0, since=since.isoformat())[1]
    return out
