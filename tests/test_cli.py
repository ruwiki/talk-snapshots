"""Суточная джоба: сбой одного раздела не глушит остальные, журналы догоняют дыру сами,
длинный код причины не роняет вставку судьбы."""

import argparse
import datetime as dt

from app import cli
from app.core import logs, pipeline
from app.core import state as pstate
from app.db import connect


def _db(path):
    db = connect(str(path))
    db.init_schema()
    return db


def test_one_failing_wiki_does_not_stop_the_rest(monkeypatch, tmp_path, capsys):
    """14.09–25.10.2026: dewiki ронял state, и ни uk/zh/it/ja, ни журналы, ни метрики не считались."""
    path = tmp_path / "ts.sqlite"
    _db(path).conn.close()
    done = []

    def refresh(db, spec, api=None, since=None):
        if spec.dbname == "dewiki":
            raise ValueError("Data too long for column 'reason_code'")
        done.append(spec.dbname)
        return 1

    monkeypatch.setattr(pipeline, "refresh_states", refresh)
    args = argparse.Namespace(db=str(path), wiki="ruwiki,dewiki,ukwiki")
    assert cli.cmd_state(args) == 1
    assert done == ["ruwiki", "ukwiki"]
    assert "dewiki  state: СБОЙ" in capsys.readouterr().err


def test_logs_start_after_last_stored_day(monkeypatch, tmp_path):
    today = dt.datetime.now(dt.UTC).date()
    path = tmp_path / "ts.sqlite"
    db = _db(path)
    last = {"ruwiki": today - dt.timedelta(days=29), "enwiki": today - dt.timedelta(days=1),
            "dewiki": today - dt.timedelta(days=100)}
    for w, d in last.items():
        db.execute("INSERT INTO log_counts VALUES (?, ?, 'delete', 'article', 'speedy', 1)", (w, d.isoformat()))
    db.commit()
    db.conn.close()
    asked = {}
    monkeypatch.setattr(logs, "store", lambda db, spec, start, end: asked.setdefault(spec.dbname, (start, end)) and 0)
    args = argparse.Namespace(db=str(path), wiki="ruwiki,enwiki,dewiki,ukwiki", start=None, end=None)
    assert cli.cmd_logs(args) == 0
    assert asked["ruwiki"][0] == today - dt.timedelta(days=28)      # дыра в 28 дней закрывается сама
    assert asked["enwiki"][0] == today - dt.timedelta(days=2)       # свежие — последние 3 дня, как раньше
    assert asked["dewiki"][0] == today - dt.timedelta(days=60)      # не дальше 60 дней назад
    assert asked["ukwiki"][0] == today - dt.timedelta(days=2)       # пусто — последние 3 дня
    assert {e for _, e in asked.values()} == {today}


def test_long_reason_code_is_cut_to_column_width(monkeypatch, tmp_path):
    from app import wikis

    db = _db(tmp_path / "ts.sqlite")
    db.execute("INSERT INTO pages (id, wiki, title, day, fetched_at) VALUES (1, 'dewiki', 'p', '2026-10-01', 'x')")
    db.execute("INSERT INTO nominations (id, page_id, wiki, day, title, struck, n_comments, kind) "
               "VALUES (1, 1, 'dewiki', '2026-10-01', 'X', 0, 1, 'single')")
    db.execute("INSERT INTO nomination_pages VALUES (1, 'dewiki', 0, 'X', 't')")
    gone = pstate.PageState(0, "X", "deleted", dt.datetime(2026, 10, 2, tzinfo=dt.UTC), "Admin",
                            "speedy", "Schnelllöschantrag", "SLA: Schnelllöschantrag")
    monkeypatch.setattr(pstate, "page_states", lambda spec, refs, since, api=None: [gone])
    assert pipeline.refresh_states(db, wikis.get("dewiki")) == 1
    assert db.execute("SELECT reason_code FROM page_state").fetchone()[0] == "Schnelllöschantr"
