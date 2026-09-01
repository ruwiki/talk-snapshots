"""Вебсервис: витрина и JSON из той же базы, что наполняет крон.

Агрегаты считаются по запросу и кэшируются в памяти на TS_CACHE_SECONDS
(по умолчанию час): база обновляется раз в сутки, ходить в неё на каждый
хит незачем. Ни NFS, ни файлов между джобой и вебом — только Toolsdb.
"""

from __future__ import annotations

import json
import os
import threading
import time

from flask import Flask, Response

from . import page, report, wikis
from .db import open_db

app = Flask(__name__)
CACHE_SECONDS = int(os.environ.get("TS_CACHE_SECONDS", "3600"))
_lock = threading.Lock()
_cache: dict[str, object] = {"at": 0.0, "report": None, "html": None}


def _order() -> list[str]:
    raw = os.environ.get("TS_WIKIS", ",".join(wikis.REGISTRY))
    return [w.strip() for w in raw.split(",") if w.strip() in wikis.REGISTRY]


def _fresh() -> dict:
    with _lock:
        if _cache["report"] is None or time.time() - float(_cache["at"]) > CACHE_SECONDS:
            with open_db() as db:
                rep = report.build(db, [wikis.get(w) for w in _order()])
            _cache.update(at=time.time(), report=rep, html=page.render(rep, _order()))
        return _cache  # type: ignore[return-value]


@app.get("/")
def index() -> Response:
    return Response(_fresh()["html"], mimetype="text/html; charset=utf-8")


@app.get("/api/report.json")
def report_json() -> Response:
    body = json.dumps(_fresh()["report"], ensure_ascii=False)
    return Response(body, mimetype="application/json; charset=utf-8",
                    headers={"Access-Control-Allow-Origin": "*"})


@app.get("/healthz")
def healthz() -> Response:
    with open_db() as db:
        n = db.execute("SELECT COUNT(*) FROM nominations").fetchone()[0]
    return Response(f"ok nominations={n}\n", mimetype="text/plain")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
