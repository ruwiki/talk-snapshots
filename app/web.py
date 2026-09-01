"""Вебсервис: обзор, страницы разделов и JSON из той же базы, что наполняет крон.

Кэш — по принципу stale-while-revalidate: агрегаты и все страницы строятся при
старте воркера (прогрев), по истечении TTL первый запрос отдаёт старую версию
и запускает пересборку в фоне; одновременных пересборок внутри процесса не
бывает. У gunicorn sync-воркеры — отдельные процессы, кэш у каждого свой.

/healthz — только живость процесса, без базы. /readyz — SELECT 1.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time

from flask import Flask, Response

from . import page, report, wikis
from .db import open_db

app = Flask(__name__)
log = logging.getLogger("talk-snapshots.web")
CACHE_SECONDS = int(os.environ.get("TS_CACHE_SECONDS", "3600"))

SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; "
                                "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


def _order() -> list[str]:
    raw = os.environ.get("TS_WIKIS", ",".join(wikis.REGISTRY))
    return [w.strip() for w in raw.split(",") if w.strip() in wikis.REGISTRY]


class _Cache:
    """Снимок витрины + одиночная фоновая пересборка по истечении TTL."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._building = False
        self.at = 0.0
        self.report_json = b"{}"
        self.pages: dict[str, str] = {}

    def _build(self) -> None:
        started = time.monotonic()
        with open_db() as db:
            rep = report.build(db, [wikis.get(w) for w in _order()])
        pages = {"": page.render_overview(rep)}
        for w in page.order_by_scale(rep):
            pages[w] = page.render_wiki(w, rep["wikis"][w], rep, wikis.get(w).lang)
        with self._lock:
            self.report_json = json.dumps(rep, ensure_ascii=False).encode()
            self.pages = pages
            self.at = time.time()
        log.info("витрина собрана за %.1f с", time.monotonic() - started)

    def warm(self) -> None:
        try:
            self._build()
        except Exception:  # без базы воркер всё равно должен подняться и отвечать 503
            log.exception("прогрев кэша не удался")

    def _refresh_in_background(self) -> None:
        with self._lock:
            if self._building:
                return
            self._building = True

        def run() -> None:
            try:
                self._build()
            except Exception:
                log.exception("фоновая пересборка не удалась; отдаём прежний снимок")
            finally:
                with self._lock:
                    self._building = False

        threading.Thread(target=run, name="ts-refresh", daemon=True).start()

    def get(self, key: str) -> str | None:
        if self.at and time.time() - self.at > CACHE_SECONDS:
            self._refresh_in_background()
        if not self.at:
            # прогрев не удался при старте — пробуем синхронно один раз
            self.warm()
        return self.pages.get(key)


CACHE = _Cache()
CACHE.warm()  # прогрев при старте воркера: первый посетитель не платит за рендер


@app.after_request
def _headers(resp: Response) -> Response:
    for k, v in SECURITY_HEADERS.items():
        resp.headers.setdefault(k, v)
    return resp


@app.get("/")
def index() -> Response:
    html = CACHE.get("")
    if html is None:
        return Response("service warming up\n", status=503, mimetype="text/plain")
    return Response(html, mimetype="text/html; charset=utf-8")


@app.get("/wiki/<dbname>")
def wiki_page(dbname: str) -> Response:
    html = CACHE.get(dbname)
    if html is None:
        if dbname not in wikis.REGISTRY:
            return Response("no such wiki\n", status=404, mimetype="text/plain")
        return Response("service warming up\n", status=503, mimetype="text/plain")
    return Response(html, mimetype="text/html; charset=utf-8")


@app.get("/api/report.json")
def report_json() -> Response:
    CACHE.get("")
    # wildcard намеренный: публичный read-only JSON для гаджетов и юзерскриптов на вики
    return Response(CACHE.report_json, mimetype="application/json; charset=utf-8",
                    headers={"Access-Control-Allow-Origin": "*"})


@app.get("/healthz")
def healthz() -> Response:
    return Response("ok\n", mimetype="text/plain")


@app.get("/readyz")
def readyz() -> Response:
    try:
        with open_db() as db:
            db.execute("SELECT 1").fetchone()
    except Exception:
        return Response("not ready\n", status=503, mimetype="text/plain")
    return Response("ok\n", mimetype="text/plain")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
