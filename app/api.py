"""Вежливый клиент MediaWiki API.

Один сеанс на раздел, User-Agent по правилам Викимедиа, повтор при 429/5xx.
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests

UA = os.environ.get(
    "TS_USER_AGENT",
    "talk-snapshots/0.1 (https://talk-snapshots.toolforge.org; tools.talk-snapshots@toolforge.org)",
)


class Api:
    def __init__(self, host: str, timeout: int = 60, maxlag: int | None = 5):
        """maxlag=None — не просить сервер отказывать при лаге (чтение с Викиданных: лаг там почти всегда > 5 с)."""
        self.host = host
        self.url = f"https://{host}/w/api.php"
        self.timeout = timeout
        self.maxlag = maxlag
        self.session = requests.Session()
        self.session.headers["User-Agent"] = UA

    def get(self, **params: Any) -> dict:
        params.setdefault("format", "json")
        params.setdefault("formatversion", 2)
        if self.maxlag is not None:
            params.setdefault("maxlag", self.maxlag)
        delay = 1.0
        for _attempt in range(5):
            resp = self.session.get(self.url, params=params, timeout=self.timeout)
            if resp.status_code in (429, 502, 503, 504):
                time.sleep(delay)
                delay *= 2
                continue
            resp.raise_for_status()
            data = resp.json()
            if "error" in data and data["error"].get("code") == "maxlag":
                time.sleep(delay)
                delay *= 2
                continue
            return data
        raise RuntimeError(f"{self.host}: не удалось получить ответ за 5 попыток: {params}")

    def paged(self, **params: Any):
        """Обход continuation-ов."""
        while True:
            data = self.get(**params)
            yield data
            if "continue" not in data:
                return
            params.update(data["continue"])
