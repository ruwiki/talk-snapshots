"""Контроль качества данных — часть джобы, а не отдельный интерфейс.

Каждый запуск считает по разделу несколько метрик и сравнивает с порогами.
Выход за порог не блокирует загрузку (данные уже лежат), но помечает запуск
и роняет код возврата — чтобы сбой был виден в логах джобы, а не через месяц
в графике. Поправил обсуждение на вики → следующий запуск перечитает день.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from ..db import DB

#: метрика → (порог, «больше — плохо»)
THRESHOLDS: dict[str, tuple[float, bool]] = {
    "share_unknown_kind": (0.05, True),       # номинации без единой найденной страницы
    "share_missing_ts": (0.02, True),         # реплики без метки времени
    "unknown_bot_candidates": (0, True),      # авторы вида *bot, не помеченные ботами
    "share_outcome_old_open": (0.60, True),   # старше 30 дней, но ни итога, ни судьбы
}


@dataclass
class Metric:
    name: str
    value: float
    threshold: float | None
    ok: bool


def compute(db: DB, wiki: str, since: dt.date) -> list[Metric]:
    s = since.isoformat()
    n_noms = db.execute("SELECT COUNT(*) FROM nominations WHERE wiki=? AND day>=?", (wiki, s)).fetchone()[0]
    n_unknown = db.execute(
        "SELECT COUNT(*) FROM nominations WHERE wiki=? AND day>=? AND kind='unknown'", (wiki, s)
    ).fetchone()[0]
    n_comments, n_missing = db.execute(
        """SELECT COUNT(*), SUM(CASE WHEN c.ts IS NULL THEN 1 ELSE 0 END)
             FROM comments c JOIN nominations n ON n.id = c.nomination_id
            WHERE c.wiki=? AND n.day>=?""", (wiki, s)
    ).fetchone()
    bots = db.execute(
        """SELECT COUNT(DISTINCT author) FROM comments
            WHERE wiki=? AND is_bot=0 AND author IS NOT NULL AND LOWER(author) LIKE ?""",
        (wiki, "%bot"),
    ).fetchone()[0]
    old = (dt.datetime.now(dt.UTC).date() - dt.timedelta(days=30)).isoformat()
    n_old, n_old_open = db.execute(
        """SELECT COUNT(*), SUM(CASE WHEN o.nomination_id IS NULL AND ps.state IS NULL THEN 1 ELSE 0 END)
             FROM nominations n
             LEFT JOIN discussion_outcome o ON o.nomination_id = n.id
             LEFT JOIN nomination_pages np ON np.nomination_id = n.id
             LEFT JOIN page_state ps ON ps.wiki = n.wiki AND ps.ns = np.ns AND ps.title = np.title
                                    AND ps.state IN ('deleted','redirect','moved','recreated')
            WHERE n.wiki=? AND n.day>=? AND n.day<=?""", (wiki, s, old)
    ).fetchone()
    values = {
        "nominations": n_noms,
        "comments": n_comments or 0,
        "share_unknown_kind": (n_unknown / n_noms) if n_noms else 0.0,
        "share_missing_ts": ((n_missing or 0) / n_comments) if n_comments else 0.0,
        "unknown_bot_candidates": bots,
        "share_outcome_old_open": ((n_old_open or 0) / n_old) if n_old else 0.0,
    }
    out = []
    for name, value in values.items():
        thr = THRESHOLDS.get(name)
        ok = True if thr is None else (value <= thr[0] if thr[1] else value >= thr[0])
        out.append(Metric(name, float(value), thr[0] if thr else None, ok))
    return out


def store(db: DB, wiki: str, metrics: list[Metric]) -> None:
    now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    db.executemany(
        "INSERT INTO quality_runs (run_at, wiki, metric, value, threshold, ok) VALUES (?, ?, ?, ?, ?, ?)",
        [(now, wiki, m.name, m.value, m.threshold, int(m.ok)) for m in metrics],
    )
    db.commit()


def report(wiki: str, metrics: list[Metric]) -> bool:
    ok_all = True
    for m in metrics:
        flag = "ok " if m.ok else "СБОЙ"
        thr = "" if m.threshold is None else f"  (порог {m.threshold:g})"
        val = f"{m.value:.1%}" if m.name.startswith("share_") else f"{m.value:g}"
        print(f"[{flag}] {wiki:8s} {m.name:26s} {val}{thr}")
        ok_all &= m.ok
    return ok_all
