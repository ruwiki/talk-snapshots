"""Реестр разделов: один модуль на вики, в каждом — объект WIKI (WikiSpec).

Добавить раздел = положить сюда файл со спеком и фикстуру в tests/fixtures/<dbname>/.
Ядро по имени раздела ничего не решает: спек — единственный источник различий.
"""

from __future__ import annotations

import importlib
import pkgutil

from ..core.spec import WikiSpec

REGISTRY: dict[str, WikiSpec] = {}

for _mod in pkgutil.iter_modules(__path__):
    module = importlib.import_module(f"{__name__}.{_mod.name}")
    spec = getattr(module, "WIKI", None)
    if isinstance(spec, WikiSpec):
        REGISTRY[spec.dbname] = spec


def get(dbname: str) -> WikiSpec:
    try:
        return REGISTRY[dbname]
    except KeyError:
        raise SystemExit(f"неизвестный раздел: {dbname}; есть {', '.join(sorted(REGISTRY))}") from None
