"""Поток правок: снимок темы в момент номинации, а не раз в сутки.

Суточная джоба видит номинацию, только если статья дожила до 04:17 UTC. В рувики
часть номинаций закрывают быстрее (замер 24.10.2026: 179 из 1 424 удалённых — меньше
чем за сутки), а после удаления категорий и истории правок уже не взять. Поток
EventStreams (recentchange) сообщает о правке дневной страницы через секунды; по ней
номинации страницы перечитываются, и для новых страниц сразу снимаются категории,
элемент Викиданных с P31/P106 и авторы.

Снимок пишется по странице (page_topics, page_authors), как и в суточной джобе, —
номинацию заводить не нужно, отчёт найдёт тему по страницам номинации.

Ядро не знает имён вики: какие страницы слушать, говорит listing каждого спека.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
from collections.abc import Callable, Iterable, Iterator

import requests

from ..api import UA, Api
from . import pipeline
from .threads import fetch_page_threads

log = logging.getLogger(__name__)

URL = "https://stream.wikimedia.org/v2/stream/recentchange"
STATE_KEY = "recentchange"
#: сервер рвёт соединение каждые 15 минут — переподключение штатное, не сбой
READ_TIMEOUT = 90
#: насколько назад брать при старте: история потока 7–31 день, но старше суток
#: догоняет суточная джоба, а догон недели занял бы часы
MAX_REPLAY = dt.timedelta(hours=24)
#: сколько дней снимок свежий: раньше страницу повторно не снимают ни по базе, ни по памяти пода
FRESH_DAYS = 3

Key = tuple[str, str]  # (dbname, заголовок дневной страницы)


def lines(resp) -> Iterator[str]:
    """Строки ответа как str. Резать байты, а не текст: iter_lines(decode_unicode=True)
    режет по str.splitlines, и U+2028 из описания правки рвёт строку data посередине."""
    for raw in resp.iter_lines():
        yield raw.decode("utf-8", "replace")


def iter_sse(source: Iterable[str]) -> Iterator[tuple[str | None, dict]]:
    """Строки text/event-stream → (id, data как dict). id по правилам SSE держится до
    следующего поля id. Битый JSON пропускается."""
    data: list[str] = []
    event_id: str | None = None
    for line in source:
        if line == "":
            if data:
                try:
                    yield event_id, json.loads("\n".join(data))
                except ValueError:
                    log.warning("stream: битое событие пропущено")
                data = []
            continue
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
        elif line.startswith("id:"):
            event_id = line[3:].strip()
    if data:
        try:
            yield event_id, json.loads("\n".join(data))
        except ValueError:
            pass


def event_time(event: dict) -> dt.datetime | None:
    value = (event.get("meta") or {}).get("dt")
    try:
        return dt.datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


class Watch:
    """Какие правки нас касаются: дневные страницы обсуждений за последние дни.

    Новые номинации появляются на сегодняшней странице, иногда на вчерашней (сдвиг
    часового пояса раздела против UTC); правки старых страниц — реплики и итоги,
    их суточная джоба перечитает сама. «Сегодня» — день события, а не часы пода:
    при догоне после рестарта вчерашние правки сверяются со вчерашними страницами.
    """

    def __init__(self, specs, window_days: int = 2):
        self.specs = {s.dbname: s for s in specs}
        self.window_days = window_days
        self._cache: dict[dt.date, dict[Key, object]] = {}

    def titles(self, today: dt.date) -> dict[Key, object]:
        if today not in self._cache:
            titles: dict[Key, object] = {}
            for spec in self.specs.values():
                # k = −1 — завтра по UTC: it, ja, zh живут впереди UTC (25.10 itwiki правит
                # страницу «25 ottobre» в 22:10 UTC 24-го)
                for k in range(-1, self.window_days):
                    day = today - dt.timedelta(days=k)
                    for title in spec.listing.page_titles(spec, day):
                        titles[(spec.dbname, title)] = spec
            self._cache = {d: v for d, v in self._cache.items() if abs((d - today).days) <= 1}
            self._cache[today] = titles
        return self._cache[today]

    def match(self, event: dict, today: dt.date):
        """→ (spec, заголовок страницы) или None."""
        if event.get("type") not in ("edit", "new"):
            return None
        key = (event.get("wiki"), event.get("title"))
        spec = self.titles(today).get(key)
        return (spec, key[1]) if spec else None


class Pending:
    """Отложенная обработка: первая правка ставит страницу в очередь на `delay` секунд,
    следующие правки той же страницы срок не сдвигают — поток реплик не откладывает
    снимок бесконечно, а пачка правок одной номинации даёт один проход.

    Страница уходит из очереди только после удачного прохода (done): упал проход или
    база — она остаётся и пробуется снова через `delay`. Для сохранения позиции очередь
    помнит первое событие по каждой странице (номер по порядку и SSE id): позиция не
    уходит дальше него.
    """

    def __init__(self, delay: float = 60.0):
        self.delay = delay
        self._items: dict[Key, list] = {}   # key → [срок, (номер, id первого события), наибольшая ревизия]

    def add(self, key: Key, now: float, mark: tuple[int, str | None] | None = None, rev: int = 0) -> None:
        item = self._items.get(key)
        if item is None:
            self._items[key] = [now + self.delay, mark, rev]
        else:
            item[2] = max(item[2], rev)

    def ready(self, now: float) -> list[Key]:
        return [k for k, item in self._items.items() if item[0] <= now]

    def done(self, key: Key) -> int:
        """Проход удался → наибольшая ревизия, которую он покрыл."""
        return self._items.pop(key)[2]

    def retry(self, key: Key, now: float) -> None:
        self._items[key][0] = now + self.delay

    def oldest(self) -> str | None:
        """SSE id самого раннего события среди ждущих страниц."""
        marks = [item[1] for item in self._items.values() if item[1] is not None and item[1][1]]
        return min(marks)[1] if marks else None

    def __len__(self) -> int:
        return len(self._items)


class Seen:
    """Страницы, которые этот под уже снимал: правки дневной страницы не гоняют базу и API
    по тем же номинациям. Запись живёт FRESH_DAYS, как свежесть снимка в базе, — повторную
    номинацию через месяц снимут заново, а память пода не растёт неделями."""

    def __init__(self, ttl: float = FRESH_DAYS * 86400):
        self.ttl = ttl
        self._at: dict[tuple[str, int, str], float] = {}

    def has(self, key: tuple[str, int, str], now: float) -> bool:
        t = self._at.get(key)
        return t is not None and now - t < self.ttl

    def add(self, keys: Iterable[tuple[str, int, str]], now: float) -> None:
        self._at = {k: t for k, t in self._at.items() if now - t < self.ttl}
        for k in keys:
            self._at.setdefault(k, now)  # срок — от первого снимка, повторные проходы его не продлевают

    def __len__(self) -> int:
        return len(self._at)


def headings_of(api: Api, title: str) -> tuple:
    """Заголовки страницы без HTML веток: новая номинация = новый заголовок (у дневного
    лога — из транклюдированной подстраницы, parse их раскрывает)."""
    data = api.get(action="parse", page=title, prop="sections")
    return tuple((s.get("level"), s.get("line")) for s in data.get("parse", {}).get("sections", []))


def snapshot_page(db, spec, api: Api, title: str, seen: Seen, now: float | None = None,
                  headings: dict[Key, tuple] | None = None) -> dict:
    """Перечитать номинации страницы и снять темы и авторов для страниц, которых ещё не снимали.

    headings — память заголовков между проходами: правка реплики заголовков не меняет,
    и тогда полный discussiontoolspageinfo с HTML всех веток не нужен.
    """
    now = time.monotonic() if now is None else now
    key = (spec.dbname, title)
    heads = None
    if headings is not None:
        heads = headings_of(api, title)
        if headings.get(key) == heads:
            return dict(nominations=0, pages=0, topics=0, claims=0, authors=0, unchanged=True)
    noms = fetch_page_threads(api, spec, page=title)
    refs = pipeline.topic_refs(spec, noms)
    pages = {(p.ns, p.title) for nom in noms for p in nom.pages}
    fresh = [r for r in refs if not seen.has((spec.dbname, *r), now)]
    fresh = pipeline.without_recent_snapshot(db, spec, fresh, days=FRESH_DAYS) if fresh else []
    try:
        n_topics, n_claims = pipeline.store_topics(db, spec, fresh, api) if fresh else (0, 0)
        author_refs = [r for r in fresh if r in pages]
        n_authors = pipeline.store_authors_refs(db, spec, author_refs, api) if author_refs else 0
        db.commit()
    except Exception:
        # без отката темы без авторов закоммитит следующая страница или save_position,
        # и without_recent_snapshot потом трое суток считает страницу снятой
        db.rollback()
        raise
    seen.add(((spec.dbname, *r) for r in refs), now)
    if headings is not None:
        headings[key] = heads
    return dict(nominations=len(noms), pages=len(fresh), topics=n_topics, claims=n_claims, authors=n_authors)


def load_position(db) -> str | None:
    return load_position_row(db)[0]


def load_position_row(db) -> tuple[str | None, str | None]:
    """→ (SSE id, когда сохранён)."""
    row = db.execute("SELECT value, updated_at FROM tool_state WHERE name = ?", (STATE_KEY,)).fetchone()
    return (row[0], row[1]) if row else (None, None)


def save_position(db, value: str) -> None:
    db.execute(
        db.upsert("INSERT INTO tool_state (name, value, updated_at) VALUES (?, ?, ?)",
                  ("name",), ("name", "value", "updated_at")),
        (STATE_KEY, value, pipeline._now()),
    )
    db.commit()


def resume(saved: str | None, now: dt.datetime, saved_at: str | None = None) -> tuple[dict, dict]:
    """→ (params, headers) запроса к потоку.

    Позиция — SSE id: JSON-массив {topic, partition, timestamp | offset} по каждому топику.
    Он уходит обратно в Last-Event-ID, и сервер продолжает каждый топик со своего места.
    Одно время на всех (meta.dt, since) так не умеет: в recentchange два топика, eqiad и
    codfw, и почти пустой отдаёт свои события раньше, чем активный начинает повтор
    (25.10.2026: codfw — 5 событий до 08:37, eqiad — повтор с 08:10). Позиция «по самому
    новому времени» перепрыгивала бы через ещё не повторённую историю.

    Вместо timestamp сервер пишет и offset (25.10: у eqiad сразу после возобновления) —
    такой id годен как есть, возраст по нему не узнать; тогда возраст — по saved_at.
    Первый запуск — since на 10 минут назад; позиция старше суток — since на сутки назад.
    """
    floor = now - MAX_REPLAY
    if saved is None:
        return {"since": _since(now - dt.timedelta(minutes=10))}, {}
    if saved_at and dt.datetime.fromisoformat(saved_at) < floor:
        return {"since": _since(floor)}, {}
    try:
        parts = json.loads(saved)
        stamps = [int(p["timestamp"]) for p in parts if "timestamp" in p]
        if not parts or any("timestamp" not in p and "offset" not in p for p in parts):
            raise ValueError(saved)
    except (ValueError, TypeError, AttributeError):
        return {"since": _since(floor)}, {}
    if stamps and min(stamps) / 1000 < floor.timestamp():
        return {"since": _since(floor)}, {}
    return {}, {"Last-Event-ID": saved}


def _since(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


class EmptyStream(Exception):
    """Сервер закрыл ответ, не прислав ни одного события: переподключаться с паузой."""


def run(specs, open_db: Callable, window_days: int = 2, delay: float = 60.0,
        heartbeat: float = 600.0, max_events: int | None = None) -> int:
    """Слушать поток до остановки пода. open_db — контекстный менеджер соединения с базой:
    соединение открывается на каждую пачку, долгоживущее Toolsdb рвёт по таймауту."""
    watch = Watch(specs, window_days)
    pending = Pending(delay)
    apis: dict[str, Api] = {}
    seen = Seen()
    headings: dict[Key, tuple] = {}
    covered: dict[Key, int] = {}   # наибольшая ревизия страницы, уже покрытая проходом
    stats = dict(events=0, matched=0, snapshots=0, errors=0)
    with open_db() as db:
        db.init_schema()
        position, saved_at = load_position_row(db)
    seq = 0
    last_dt: dt.datetime | None = None
    last_save = last_beat = time.monotonic()
    backoff = 1.0
    while True:
        params, extra = resume(position, dt.datetime.now(dt.UTC), saved_at)
        saved_at = None   # дальше позиция — из этого процесса, свежая
        received = 0
        try:
            with requests.get(URL, params=params, stream=True, timeout=(15, READ_TIMEOUT),
                              headers={"User-Agent": UA, "Accept": "text/event-stream", **extra}) as resp:
                resp.raise_for_status()
                log.info("stream: подключено, %s", params or "Last-Event-ID")
                for event_id, event in iter_sse(lines(resp)):
                    received += 1
                    seq += 1
                    stats["events"] += 1
                    if event_id:
                        position = event_id
                    when = event_time(event)
                    if when:
                        last_dt = when
                    hit = watch.match(event, (when or dt.datetime.now(dt.UTC)).date())
                    now = time.monotonic()
                    if hit:
                        key = (hit[0].dbname, hit[1])
                        rev = int((event.get("revision") or {}).get("new") or 0)
                        # правку, которую проход уже покрыл, приносит повтор после переподключения
                        if not rev or rev > covered.get(key, 0):
                            stats["matched"] += 1
                            pending.add(key, now, (seq, event_id), rev)
                    ready = pending.ready(now)
                    if ready or now - last_save > 60:
                        with open_db() as db:
                            for key in ready:
                                dbname, title = key
                                spec = watch.specs[dbname]
                                if dbname not in apis:
                                    apis[dbname] = Api(spec.host)
                                try:
                                    r = snapshot_page(db, spec, apis[dbname], title, seen, now, headings)
                                except Exception as exc:  # noqa: BLE001 — одна страница не повод ронять поток
                                    stats["errors"] += 1
                                    pending.retry(key, now)
                                    log.warning("stream: %s %s: %s", dbname, title, exc)
                                    continue
                                covered[key] = max(covered.get(key, 0), pending.done(key))
                                stats["snapshots"] += 1
                                if r["pages"]:
                                    log.info("stream: %s %s — номинаций %d, новых страниц %d, тем %d, "
                                             "P31/P106 %d, авторов %d", dbname, title, r["nominations"],
                                             r["pages"], r["topics"], r["claims"], r["authors"])
                            # позиция не уходит дальше первого события страницы, которая ещё ждёт:
                            # после рестарта пода повтор поставит её в очередь снова
                            safe = pending.oldest() or position
                            if safe:
                                save_position(db, safe)
                        last_save = now
                        # сброс только после удачной пачки: подключиться к потоку удаётся и при лежащей Toolsdb
                        backoff = 1.0
                    if now - last_beat > heartbeat:
                        lag = (dt.datetime.now(dt.UTC) - last_dt).total_seconds() if last_dt else -1
                        log.info("stream: событий %d, наших %d, проходов %d, ошибок %d, в очереди %d, отставание %.0f с",
                                 stats["events"], stats["matched"], stats["snapshots"], stats["errors"],
                                 len(pending), lag)
                        last_beat = now
                    if max_events is not None and stats["events"] >= max_events:
                        return 0
            if not received:
                raise EmptyStream("ответ без событий")
        except Exception as exc:  # noqa: BLE001 — сеть, Toolsdb, формат: переподключиться, а не уронить под
            log.warning("stream: %s: %s, переподключение через %.0f с", type(exc).__name__, exc, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
