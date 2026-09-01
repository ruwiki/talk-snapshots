"""Словарь витрины: полнота и отсутствие мусора.

Языки страниц разделов обязаны иметь полный перевод (пустая строка = откат
в английский — это осознанный механизм только для обзорных ov_*-строк).
"""

from __future__ import annotations

from app import wikis
from app.i18n import LANGS, S, t


def test_every_key_has_english():
    for key, entry in S.items():
        assert entry.get("en"), key


def test_no_unknown_languages():
    for key, entry in S.items():
        for lang in entry:
            assert lang in LANGS, (key, lang)


def test_wiki_languages_fully_translated():
    langs = {spec.lang for spec in wikis.REGISTRY.values()}
    for lang in langs:
        missing = [k for k, e in S.items() if not e.get(lang) and not k.startswith("ov_")]
        assert not missing, (lang, missing)


def test_format_placeholders_survive_translation():
    for key, entry in S.items():
        need = {c for c in ("{n}", "{total}", "{date}", "{a}", "{b}", "{g}", "{na}") if c in entry["en"]}
        for lang, text in entry.items():
            if text:
                for ph in need:
                    assert ph in text, (key, lang, ph)


def test_weekdays_have_seven_days():
    for lang in LANGS:
        assert len(t(lang, "weekdays").split("|")) == 7, lang
