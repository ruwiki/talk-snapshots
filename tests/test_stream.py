"""Поток правок: какие события ловим, когда снимаем, что пишем и что сохраняем как позицию."""

import datetime as dt
import json
import pathlib
from contextlib import contextmanager

import pytest

from app import wikis
from app.core import authors, stream, topics
from app.db import connect
from app.models import Nomination, PageRef

TODAY = dt.date(2026, 10, 24)
REAL_TITLES = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "stream" / "recentchange_titles.json").read_text(encoding="utf-8")
)


def _nom(title, *pages, source_page=None):
    nom = Nomination(title=title, heading_raw=title, struck=False)
    nom.pages = [PageRef(ns=0, title=p, resolved_by="test") for p in pages]
    nom.source_page = source_page
    return nom


def _db():
    db = connect(":memory:")
    db.init_schema()
    return db


# --- разбор потока -------------------------------------------------------------------------


class _Raw:
    """Ответ requests с байтовыми строками — как iter_lines() без decode_unicode."""

    def __init__(self, payload: str):
        self.payload = payload

    def iter_lines(self):
        return iter(self.payload.encode("utf-8").splitlines())


def test_lines_keep_u2028_inside_event():
    """U+2028 в описании правки: str.splitlines рвёт по нему строку data, bytes.splitlines — нет."""
    event = {"type": "edit", "comment": "строка вторая\u0085третья", "title": "X"}
    payload = f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    assert len(payload.splitlines()) > 2                         # так резал decode_unicode=True
    assert list(stream.iter_sse(stream.lines(_Raw(payload)))) == [(None, event)]


def test_iter_sse_events_ids_multiline_and_broken():
    lines = [
        ":ok", "", "event: message", 'id: [{"topic":"x"}]', 'data: {"a": 1}', "",
        'data: {"b":', "data: 2}", "",                       # id без нового поля держится
        "data: {broken", "",
        "id: 7", 'data: {"c": 3}',
    ]
    assert list(stream.iter_sse(lines)) == [('[{"topic":"x"}]', {"a": 1}), ('[{"topic":"x"}]', {"b": 2}), ("7", {"c": 3})]


# --- какие страницы слушаем ----------------------------------------------------------------


@pytest.mark.parametrize("dbname", sorted(wikis.REGISTRY))
def test_watch_matches_real_recentchange_titles(dbname):
    """Заголовки и время — из recentchanges самих вики (фикстура от 25.10.2026), не из page_titles.

    Хоть одна правка дневной страницы должна совпасть в окне своего дня; служебные подстраницы
    («Предварительные итоги», «AutoQS…», «今週/topic list») — никогда.
    """
    watch = stream.Watch([wikis.get(dbname)])
    rows = REAL_TITLES[dbname]
    hits = []
    for r in rows:
        when = dt.datetime.fromisoformat(r["dt"])
        hit = watch.match({"type": r["type"], "wiki": dbname, "title": r["title"]}, when.date())
        if not any(ch.isdigit() for ch in r["title"].rsplit("/", 1)[-1]):
            assert hit is None, r["title"]
        if hit:
            hits.append(r["title"])
    assert hits, f"{dbname}: ни одна реальная правка дневной страницы не совпала — формат заголовка разошёлся"


def test_watch_window_follows_event_day():
    """Окно — по дню события: правка страницы трёхдневной давности при догоне — своя."""
    spec = wikis.get("ruwiki")
    watch = stream.Watch([spec])
    old = spec.listing.page_titles(spec, TODAY - dt.timedelta(days=3))[0]
    event = {"type": "edit", "wiki": "ruwiki", "title": old}
    assert watch.match(event, TODAY) is None
    assert watch.match(event, TODAY - dt.timedelta(days=3)) is not None
    assert watch.match({"type": "log", "wiki": "ruwiki", "title": old}, TODAY - dt.timedelta(days=3)) is None
    assert watch.match({"type": "edit", "wiki": "xxwiki", "title": old}, TODAY - dt.timedelta(days=3)) is None


# --- очередь и память пода -----------------------------------------------------------------


def test_pending_delay_does_not_slide_and_keys_leave_only_when_done():
    p = stream.Pending(delay=60)
    p.add(("ruwiki", "A"), now=0, mark=(1, "id1"), rev=10)
    p.add(("ruwiki", "A"), now=50, mark=(9, "id9"), rev=12)                 # срок и метку не двигает, ревизию — да
    p.add(("ruwiki", "B"), now=30, mark=(5, "id5"), rev=11)
    assert p.ready(59) == []
    assert p.ready(60) == [("ruwiki", "A")]
    p.retry(("ruwiki", "A"), now=60)                                          # проход упал — ещё раз позже
    assert p.ready(90) == [("ruwiki", "B")] and p.oldest() == "id1"
    assert p.done(("ruwiki", "B")) == 11
    assert p.ready(120) == [("ruwiki", "A")] and p.done(("ruwiki", "A")) == 12
    assert len(p) == 0 and p.oldest() is None


def test_seen_forgets_after_ttl():
    s = stream.Seen(ttl=100)
    s.add([("ruwiki", 0, "A")], now=0)
    s.add([("ruwiki", 0, "A"), ("ruwiki", 0, "B")], now=50)   # повторный проход срок A не продлевает
    assert s.has(("ruwiki", 0, "A"), 99) and not s.has(("ruwiki", 0, "A"), 100)
    s.add([], now=120)                                          # A забыта и из памяти
    assert len(s) == 1 and s.has(("ruwiki", 0, "B"), 120)


def _sse_id(*stamps):
    """SSE id EventStreams: по смещению-времени на каждый топик (мс)."""
    topics_ = ("eqiad.mediawiki.recentchange", "codfw.mediawiki.recentchange")
    return json.dumps([{"topic": t, "partition": 0, "timestamp": int(s.timestamp() * 1000)}
                       for t, s in zip(topics_, stamps, strict=True)])


def test_resume():
    now = dt.datetime(2026, 10, 24, 12, 0, tzinfo=dt.UTC)
    assert stream.resume(None, now) == ({"since": "2026-10-24T11:50:00Z"}, {})
    fresh = _sse_id(now - dt.timedelta(minutes=5), now - dt.timedelta(hours=2))
    assert stream.resume(fresh, now) == ({}, {"Last-Event-ID": fresh})        # каждый топик со своего места
    stale = _sse_id(now - dt.timedelta(minutes=5), now - dt.timedelta(days=3))
    assert stream.resume(stale, now) == ({"since": "2026-10-23T12:00:00Z"}, {})
    assert stream.resume("2026-10-24T11:00:30Z", now) == ({"since": "2026-10-23T12:00:00Z"}, {})
    # сервер пишет и offset вместо timestamp — такой id годен как есть
    with_offset = json.dumps([{"offset": 6638225332, "partition": 0, "topic": "eqiad.mediawiki.recentchange"},
                              {"topic": "codfw.mediawiki.recentchange", "partition": 0,
                               "timestamp": int((now - dt.timedelta(minutes=3)).timestamp() * 1000)}])
    assert stream.resume(with_offset, now) == ({}, {"Last-Event-ID": with_offset})
    # возраст по одним offset не узнать — по времени сохранения
    assert stream.resume(with_offset, now, saved_at="2026-10-22T00:00:00+00:00") == ({"since": "2026-10-23T12:00:00Z"}, {})
    assert stream.resume(with_offset, now, saved_at="2026-10-24T11:59:00+00:00") == ({}, {"Last-Event-ID": with_offset})


# --- проход по странице --------------------------------------------------------------------


def _fake_snapshots(monkeypatch, calls):
    def snap(spec, refs, api=None, wikidata=None):
        calls.append(("topics", list(refs)))
        return [(ns, t, "category", f"Кат {t}") for ns, t in refs] + [(0, refs[0][1], "P31", "Q5")]

    def auth(spec, refs, api=None):
        calls.append(("authors", list(refs)))
        ts = dt.datetime(2026, 10, 1, tzinfo=dt.UTC)
        return [authors.Author(ns, t, "Автор", 3, 1000, ts, ts, False) for ns, t in refs]

    monkeypatch.setattr(topics, "snapshot", snap)
    monkeypatch.setattr(authors, "snapshot", auth)


def test_snapshot_page_stores_by_page_once(monkeypatch):
    spec = wikis.get("ruwiki")
    db = _db()
    calls = []
    _fake_snapshots(monkeypatch, calls)
    noms = [_nom("Ромашка", "Ромашка"), _nom("Лютик", "Лютик")]
    monkeypatch.setattr(stream, "fetch_page_threads", lambda api, spec, page: noms)

    seen = stream.Seen()
    r = stream.snapshot_page(db, spec, api=None, title="Википедия:К удалению/24 октября 2026", seen=seen)
    assert r == dict(nominations=2, pages=2, topics=2, claims=1, authors=2)
    rows = db.execute("SELECT wiki, title, source, value FROM page_topics ORDER BY title, source").fetchall()
    assert [tuple(x) for x in rows] == [
        ("ruwiki", "Лютик", "category", "Кат Лютик"),
        ("ruwiki", "Ромашка", "P31", "Q5"), ("ruwiki", "Ромашка", "category", "Кат Ромашка"),
    ]
    assert db.execute("SELECT COUNT(*) FROM page_authors").fetchone()[0] == 2

    # та же страница ещё раз: в этом процессе уже видели
    assert stream.snapshot_page(db, spec, None, "x", seen)["pages"] == 0
    # новый процесс (seen пуст), но свежий снимок в базе есть — снова не снимаем
    assert stream.snapshot_page(db, spec, None, "x", stream.Seen())["pages"] == 0
    # появилась третья номинация — снимается только она
    noms.append(_nom("Василёк", "Василёк"))
    assert stream.snapshot_page(db, spec, None, "x", seen)["pages"] == 1
    assert calls[-2:] == [("topics", [(0, "Василёк")]), ("authors", [(0, "Василёк")])]


def test_same_title_in_two_wikis_keeps_both_snapshots(monkeypatch):
    """Ключ снимка с вики: одноимённая статья во второй вики не теряется на INSERT IGNORE."""
    db = _db()
    _fake_snapshots(monkeypatch, [])
    monkeypatch.setattr(stream, "fetch_page_threads", lambda api, spec, page: [_nom("Kyiv", "Kyiv")])
    for dbname in ("ruwiki", "ukwiki"):
        assert stream.snapshot_page(db, wikis.get(dbname), None, "x", stream.Seen())["pages"] == 1
    rows = db.execute("SELECT wiki FROM page_topics WHERE source = 'category' ORDER BY wiki").fetchall()
    assert [r[0] for r in rows] == ["ruwiki", "ukwiki"]


def test_renomination_weeks_later_is_snapshotted_again(monkeypatch):
    """Ромашку оставили, через 38 дней номинируют снова, под всё тот же — снимок нужен заново."""
    spec = wikis.get("ruwiki")
    db = _db()
    calls = []
    _fake_snapshots(monkeypatch, calls)
    monkeypatch.setattr(stream, "fetch_page_threads", lambda api, spec, page: [_nom("Ромашка", "Ромашка")])
    seen = stream.Seen()
    assert stream.snapshot_page(db, spec, None, "x", seen, now=0)["pages"] == 1
    db.execute("UPDATE page_topics SET last_seen = '2000-01-01T00:00:00+00:00'")   # в базе снимок давно не свежий
    assert stream.snapshot_page(db, spec, None, "x", seen, now=3600)["pages"] == 0      # через час: память пода
    del calls[:]
    assert stream.snapshot_page(db, spec, None, "x", seen, now=38 * 86400)["pages"] == 1
    assert calls == [("topics", [(0, "Ромашка")]), ("authors", [(0, "Ромашка")])]


def test_failed_snapshot_rolls_back_and_is_retried(monkeypatch):
    """Авторы упали после записи тем: темы откатываются, следующий проход снимает страницу целиком."""
    spec = wikis.get("ruwiki")
    db = _db()
    _fake_snapshots(monkeypatch, [])
    good_authors = authors.snapshot

    def boom(spec, refs, api=None):
        raise RuntimeError("API авторов недоступен")

    monkeypatch.setattr(authors, "snapshot", boom)
    monkeypatch.setattr(stream, "fetch_page_threads", lambda api, spec, page: [_nom("Ромашка", "Ромашка")])
    seen = stream.Seen()
    with pytest.raises(RuntimeError):
        stream.snapshot_page(db, spec, None, "x", seen, now=0)
    stream.save_position(db, "2026-10-24T12:00:00Z")      # в run следом коммитит save_position
    assert db.execute("SELECT COUNT(*) FROM page_topics").fetchone()[0] == 0
    monkeypatch.setattr(authors, "snapshot", good_authors)
    r = stream.snapshot_page(db, spec, None, "x", seen, now=60)
    assert (r["pages"], r["topics"], r["authors"]) == (1, 1, 1)


def test_afd_subpage_gets_topics_but_not_authors(monkeypatch):
    spec = wikis.get("enwiki")
    db = _db()
    calls = []
    _fake_snapshots(monkeypatch, calls)
    noms = [_nom("Foo", "Foo", source_page="Wikipedia:Articles for deletion/Foo")]
    monkeypatch.setattr(stream, "fetch_page_threads", lambda api, spec, page: noms)
    stream.snapshot_page(db, spec, None, "Wikipedia:Articles for deletion/Log/2026 October 24", stream.Seen())
    assert calls == [("topics", [(0, "Foo"), (4, "Articles for deletion/Foo")]), ("authors", [(0, "Foo")])]


class _Api:
    def __init__(self, sections):
        self.sections, self.calls = sections, 0

    def get(self, **params):
        self.calls += 1
        return {"parse": {"sections": [{"level": "2", "line": s} for s in self.sections]}}


def test_unchanged_headings_skip_the_full_threads_request(monkeypatch):
    """Правка реплики заголовков не меняет — discussiontoolspageinfo с HTML всех веток не нужен."""
    spec = wikis.get("ruwiki")
    db = _db()
    _fake_snapshots(monkeypatch, [])
    fetched = []
    monkeypatch.setattr(stream, "fetch_page_threads", lambda api, spec, page: fetched.append(page) or [_nom("A", "A")])
    api, heads, seen = _Api(["A"]), {}, stream.Seen()
    assert stream.snapshot_page(db, spec, api, "x", seen, 0, heads)["pages"] == 1
    assert stream.snapshot_page(db, spec, api, "x", seen, 60, heads).get("unchanged")
    api.sections.append("B")                                            # новая номинация — новый заголовок
    assert not stream.snapshot_page(db, spec, api, "x", seen, 120, heads).get("unchanged")
    assert fetched == ["x", "x"]


# --- цикл run ------------------------------------------------------------------------------


class _Resp:
    """Ответ потока: у события без явного id он строится из meta.dt (eqiad) и codfw на минуту раньше."""

    def __init__(self, events):
        out = []
        for e in events:
            eid = e.pop("_id", None)
            if eid is None and (e.get("meta") or {}).get("dt"):
                t = dt.datetime.fromisoformat(e["meta"]["dt"])
                eid = _sse_id(t, t - dt.timedelta(minutes=1))
            out.append((f"id: {eid}\n" if eid else "") + f"data: {json.dumps(e, ensure_ascii=False)}\n\n")
        self.payload = "".join(out)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_lines(self):
        return iter(self.payload.encode("utf-8").splitlines())


class _Stop(BaseException):
    """Выход из бесконечного run: Exception он ловит сам."""


def _open_db_at(path, fail_on=()):
    opened = []

    @contextmanager
    def open_db():
        opened.append(1)
        if len(opened) in fail_on:
            raise RuntimeError("toolsdb down")
        db = connect(path)
        try:
            yield db
        finally:
            db.conn.close()

    return open_db


def _ok(*a, **kw):
    return dict(nominations=1, pages=0, topics=0, claims=0, authors=0)


def test_run_wires_stream_to_snapshot_and_position(monkeypatch, tmp_path):
    spec = wikis.get("ruwiki")
    today = dt.datetime.now(dt.UTC).date()
    title = spec.listing.page_titles(spec, today)[0]
    now = dt.datetime.now(dt.UTC)
    stamp = [(now - dt.timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%S.000Z") for s in (3, 2, 1)]
    events = [
        {"type": "edit", "wiki": "enwiki", "title": "X", "meta": {"dt": stamp[0]}},
        {"type": "edit", "wiki": "ruwiki", "title": title, "meta": {"dt": stamp[1]}, "revision": {"new": 5}},
        {"type": "edit", "wiki": "ruwiki", "title": "Y", "meta": {"dt": stamp[2]}},
    ]
    done = []
    monkeypatch.setattr(stream.requests, "get", lambda url, params, **kw: _Resp(events))
    monkeypatch.setattr(stream, "snapshot_page", lambda db, spec, api, t, *a: done.append(t) or _ok())
    open_db = _open_db_at(str(tmp_path / "ts.sqlite"))
    assert stream.run([spec], open_db, delay=0, max_events=3) == 0
    assert done == [title]
    t = dt.datetime.fromisoformat(stamp[1])
    with open_db() as db:
        assert stream.load_position(db) == _sse_id(t, t - dt.timedelta(minutes=1))   # id в момент прохода


def test_run_uses_event_day_when_replaying(monkeypatch, tmp_path):
    """Догон после рестарта: правка трёхдневной страницы трое суток назад — своя, хотя по часам пода нет."""
    spec = wikis.get("ruwiki")
    then = dt.datetime.now(dt.UTC) - dt.timedelta(days=3)
    title = spec.listing.page_titles(spec, then.date())[0]
    events = [{"type": "edit", "wiki": "ruwiki", "title": title, "meta": {"dt": then.isoformat()}}]
    done = []
    monkeypatch.setattr(stream.requests, "get", lambda url, params, **kw: _Resp(events))
    monkeypatch.setattr(stream, "snapshot_page", lambda db, spec, api, t, *a: done.append(t) or _ok())
    assert stream.run([spec], _open_db_at(str(tmp_path / "ts.sqlite")), delay=0, max_events=1) == 0
    assert done == [title]


def test_run_failed_pass_keeps_page_and_position_behind_it(monkeypatch, tmp_path):
    """Проход упал: страница остаётся в очереди, позиция не уходит дальше её события."""
    spec = wikis.get("ruwiki")
    title = spec.listing.page_titles(spec, dt.datetime.now(dt.UTC).date())[0]
    now = dt.datetime.now(dt.UTC)
    t_hit, t_last = now - dt.timedelta(seconds=10), now - dt.timedelta(seconds=1)
    events = [
        {"type": "edit", "wiki": "ruwiki", "title": title, "meta": {"dt": t_hit.isoformat()}},
        {"type": "edit", "wiki": "enwiki", "title": "X", "meta": {"dt": t_last.isoformat()}},
    ]

    def boom(*a, **kw):
        raise RuntimeError("API лежит")

    monkeypatch.setattr(stream.requests, "get", lambda url, params, **kw: _Resp(events))
    monkeypatch.setattr(stream, "snapshot_page", boom)
    clock = iter([0.0, 0.0, 0.0, 61.0, 61.0, 61.0])
    monkeypatch.setattr(stream.time, "monotonic", lambda: next(clock))
    open_db = _open_db_at(str(tmp_path / "ts.sqlite"))
    assert stream.run([spec], open_db, delay=0, max_events=2) == 0
    with open_db() as db:
        assert stream.load_position(db) == _sse_id(t_hit, t_hit - dt.timedelta(minutes=1))


def test_run_skips_replayed_edits_already_covered(monkeypatch, tmp_path):
    """После переподключения повтор приносит ту же правку (та же ревизия) — второго прохода нет."""
    spec = wikis.get("ruwiki")
    title = spec.listing.page_titles(spec, dt.datetime.now(dt.UTC).date())[0]
    at = dt.datetime.now(dt.UTC).isoformat()
    ev = {"type": "edit", "wiki": "ruwiki", "title": title, "meta": {"dt": at}, "revision": {"new": 7}}
    calls, done = [], []

    def fake_get(url, params, **kw):
        calls.append(1)
        if len(calls) == 3:
            raise _Stop
        return _Resp([ev])

    monkeypatch.setattr(stream.requests, "get", fake_get)
    monkeypatch.setattr(stream.time, "sleep", lambda s: None)
    monkeypatch.setattr(stream, "snapshot_page", lambda db, spec, api, t, *a: done.append(t) or _ok())
    with pytest.raises(_Stop):
        stream.run([spec], _open_db_at(str(tmp_path / "ts.sqlite")), delay=0)
    assert done == [title]


def test_run_empty_response_backs_off(monkeypatch, tmp_path):
    """Пустой 200 / сразу EOF — пауза растёт, а не мгновенный круг переподключений."""
    slept = []

    def fake_sleep(s):
        slept.append(s)
        if len(slept) == 3:
            raise _Stop

    monkeypatch.setattr(stream.requests, "get", lambda url, params, **kw: _Resp([]))
    monkeypatch.setattr(stream.time, "sleep", fake_sleep)
    with pytest.raises(_Stop):
        stream.run([wikis.get("ruwiki")], _open_db_at(str(tmp_path / "ts.sqlite")))
    assert slept == [1.0, 2.0, 4.0]


def test_run_db_outage_backs_off_and_keeps_position(monkeypatch, tmp_path):
    """Поток жив, Toolsdb лежит: паузы растут, точка повтора на месте; после удачной пачки — снова 1 с."""
    spec = wikis.get("ruwiki")
    title = spec.listing.page_titles(spec, dt.datetime.now(dt.UTC).date())[0]
    hour_ago = dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)
    saved = _sse_id(hour_ago, hour_ago)
    path = str(tmp_path / "ts.sqlite")
    db = connect(path)
    db.init_schema()
    stream.save_position(db, saved)
    db.conn.close()

    asked, slept = [], []

    def fake_get(url, params, headers, **kw):
        asked.append((dict(params), headers.get("Last-Event-ID")))
        if len(asked) == 4:
            raise stream.requests.ConnectionError("обрыв")
        # сервер продолжает ровно с сохранённого id и повторяет его же
        return _Resp([{"type": "edit", "wiki": "ruwiki", "title": title, "_id": saved,
                       "meta": {"dt": hour_ago.isoformat()}}])

    def fake_sleep(s):
        slept.append(s)
        if len(slept) == 3:
            raise _Stop

    open_db = _open_db_at(path, fail_on=(2, 3))         # первое открытие — init_schema, потом два отказа
    monkeypatch.setattr(stream.requests, "get", fake_get)
    monkeypatch.setattr(stream.time, "sleep", fake_sleep)
    monkeypatch.setattr(stream, "snapshot_page", _ok)
    with pytest.raises(_Stop):
        stream.run([spec], open_db, delay=0)
    assert slept == [1.0, 2.0, 1.0]
    assert asked == [({}, saved)] * 4
    with open_db() as db:
        assert stream.load_position(db) == saved


def test_run_resumes_each_topic_from_its_own_place(monkeypatch, tmp_path):
    """Почти пустой codfw отдаёт событие с новым временем раньше, чем eqiad начинает повтор
    (25.10.2026: codfw до 08:37, eqiad с 08:10). Обрыв посреди повтора: переподключение по
    последнему SSE id, где eqiad стоит там, где остановился, а не по самому новому времени."""
    spec = wikis.get("ruwiki")
    now = dt.datetime.now(dt.UTC)
    t_old, t_new = now - dt.timedelta(minutes=30), now - dt.timedelta(minutes=1)
    id_codfw = _sse_id(t_old - dt.timedelta(seconds=1), t_new)          # eqiad ещё не начат, codfw уже «сейчас»
    id_eqiad = _sse_id(t_old, t_new)                                    # eqiad пошёл с t_old
    first = [
        {"type": "edit", "wiki": "dewiki", "title": "X", "_id": id_codfw, "meta": {"dt": t_new.isoformat()}},
        {"type": "edit", "wiki": "enwiki", "title": "Y", "_id": id_eqiad, "meta": {"dt": t_old.isoformat()}},
    ]
    asked = []

    def fake_get(url, params, headers, **kw):
        asked.append((dict(params), headers.get("Last-Event-ID")))
        if len(asked) == 1:
            return _Resp(first)
        raise _Stop

    monkeypatch.setattr(stream.requests, "get", fake_get)
    with pytest.raises(_Stop):
        stream.run([spec], _open_db_at(str(tmp_path / "ts.sqlite")), delay=0)
    assert asked[1] == ({}, id_eqiad)
