"""Готовность на Toolforge: без envvars не уходить молча в пустую SQLite и не зеленеть на /readyz.

22–25.10.2026 под веб-сервиса пересоздали без переменных окружения: connect() без TS_DB открыл
локальную SQLite, витрина 2,5 суток отдавала 503, а /readyz — 200.
"""

import pytest

from app.db import connect

TOOLFORGE_VARS = ("TOOL_TOOLSDB_USER", "KUBERNETES_SERVICE_HOST")


@pytest.fixture
def local_env(monkeypatch, tmp_path):
    for var in TOOLFORGE_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("TS_DB", str(tmp_path / "ts.sqlite"))
    return monkeypatch


@pytest.fixture
def web(local_env):
    from app import web  # прогрев при импорте падает на пустой базе — витрина не собрана

    local_env.setattr(web.CACHE, "pages", {})
    return web


def test_connect_without_ts_db_falls_back_to_sqlite_only_locally(local_env, tmp_path):
    local_env.chdir(tmp_path)
    local_env.delenv("TS_DB")
    db = connect()
    assert db.flavour == "sqlite"
    db.conn.close()
    # TOOL_TOOLSDB_USER приходит из envvars и может пропасть вместе с TS_*; KUBERNETES_SERVICE_HOST — нет
    for var in TOOLFORGE_VARS:
        with local_env.context() as m:
            m.setenv(var, "x")
            with pytest.raises(RuntimeError, match="TS_DB"):
                connect()
            assert connect(":memory:").flavour == "sqlite"   # явный dsn (тесты, --db) — как попросили


def test_readyz_503_until_showcase_is_built(web, local_env):
    client = web.app.test_client()
    r = client.get("/readyz")
    assert r.status_code == 503 and b"cache" in r.data
    local_env.setattr(web.CACHE, "pages", {"": "<html>"})
    assert client.get("/readyz").status_code == 200


def test_readyz_503_on_toolforge_without_toolsdb(web, local_env):
    local_env.setattr(web.CACHE, "pages", {"": "<html>"})
    local_env.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
    client = web.app.test_client()
    r = client.get("/readyz")                       # TS_DB указывает на SQLite
    assert r.status_code == 503 and b"Toolsdb" in r.data
    local_env.delenv("TS_DB")                       # как в инциденте: envvars не доехали
    r = client.get("/readyz")
    assert r.status_code == 503 and b"database unavailable" in r.data
