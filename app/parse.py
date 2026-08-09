"""ЗАПАСНОЙ путь: разбор вики-текста, когда API вызвать нельзя.

Основной источник структуры — threads.py (DiscussionTools): движок сегментирует
обсуждение точнее, чем регулярки по подписям, и отдаёт автора, время и
вложенность полями. Этот модуль нужен там, где API недоступен по стоимости:
офлайн-обработка дампов за годы и по сотням разделов.

Единица разбора — подпись: реплика заканчивается меткой времени, а начинается
там, где закончилась предыдущая. Формат голосования не используется, поэтому
разбор одинаково работает на дневной странице рувики и на странице номинации
англовики. Насколько он проигрывает движку — меряется в tests/test_vs_engine.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from .models import Comment, Nomination
from .wikis import Wiki

#: маркеры отступа в начале строки
INDENT = re.compile(r"^([*:#]+)", re.M)
#: [[ссылка|подпись]] → подпись, [[ссылка]] → ссылка
LINK = re.compile(r"\[\[([^|\]]+)(?:\|([^\]]*))?\]\]")
NOWIKI_ENTITY = re.compile(r"&#(\d+);")
#: хвост предыдущей реплики, затекающий в начало следующей: закрытия шаблонов и тегов.
#: без \A и ^ — якорем служит сама позиция, с которой вызван match()
LEFTOVER = re.compile(r"(?:\s*(?:\}\}|</\w+>|</?div[^>]*>|\)|\||<br\s*/?>))+", re.I)


def _unescape(s: str) -> str:
    return NOWIKI_ENTITY.sub(lambda m: chr(int(m.group(1))), s)


def _norm_user(name: str) -> str:
    name = _unescape(name).replace("_", " ").strip()
    name = name.split("/")[0].strip()  # Special:Contributions/1.2.3.4 и подстраницы
    return name[:1].upper() + name[1:] if name else name


def heading_title(raw: str) -> str:
    """Извлечь название статьи из заголовка номинации."""
    cleaned = re.sub(r"</?s>|</?strike>|'''|<small>|</small>", "", raw, flags=re.IGNORECASE)
    links = LINK.findall(cleaned)
    if links:
        target = links[0][0].lstrip(":").strip()
        return target
    return cleaned.strip()


@dataclass(frozen=True)
class Section:
    heading: str
    body: str
    #: смещение заголовка в исходном тексте — нужно, чтобы отрезать итог по позиции
    start: int


def split_sections(text: str, level: int) -> list[Section]:
    """Разбить страницу на секции заданного уровня."""
    eq = "=" * level
    pattern = re.compile(rf"^{eq}([^=].*?){eq}\s*$", re.M)
    marks = list(pattern.finditer(text))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append(Section(m.group(1).strip(), text[m.end():end], m.start()))
    return out


def _depth_at(text: str, pos: int) -> int:
    """Глубина отступа строки, в которой начинается реплика."""
    line_start = text.rfind("\n", 0, pos) + 1
    m = INDENT.match(text, line_start)
    return len(m.group(1)) if m and m.start() == line_start else 0


def _first_content_pos(text: str, start: int, end: int) -> int:
    """Начало собственно реплики.

    Пропускаем пробелы и переводы строк после прошлой подписи, затем — хвост
    предыдущей реплики: закрывающие скобки шаблонов и тегов, оставшиеся от
    подписи внутри {{smalldiv|…}} или <small>…</small>.
    """
    pos = start
    while True:
        while pos < end and text[pos] in "\n\r \t":
            pos += 1
        m = LEFTOVER.match(text, pos, end)
        if not m or m.end() == pos:
            return pos
        pos = m.end()


def clean_text(chunk: str, wiki: Wiki, has_author: bool) -> str:
    """Убрать из реплики служебную обвязку и собственную подпись.

    Подпись отрезается по началу последней ссылки на участника — но только
    если после неё почти ничего нет. Иначе это не подпись, а упоминание
    коллеги внутри текста, и резать по нему нельзя.
    """
    text = chunk
    for pat in wiki.boilerplate_patterns:
        text = re.sub(pat, "", text, flags=re.I | re.S | re.M)
    if has_author:
        last = None
        for m in wiki.user_link_re().finditer(text):
            last = m
        if last is not None and len(text) - last.end() <= 80:
            head = text[: last.start()]
            # подпись часто состоит из нескольких ссылок подряд — срезаем весь блок,
            # но только ссылки на участников: [[ВП:КОПИВИО]] — это уже текст реплики
            tail_re = re.compile(
                rf"(?:[-–—|,;:()\[\]{{}}\s]|<[^>]+>|{wiki.user_link_full_re().pattern})+$",
                re.I,
            )
            text = tail_re.sub("", head)
    text = re.sub(r"^[\s*:#]+", "", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _author_before(chunk: str, wiki: Wiki) -> str | None:
    """Автор — последняя ссылка на участника перед меткой времени.

    Последняя, а не первая: подпись почти всегда выглядит как
    «[[У:Имя|Имя]] ([[ОУ:Имя|обс.]]) время», и обе ссылки ведут к одному
    человеку, но у оформленных подписей первой может оказаться чужая ссылка
    из текста реплики.
    """
    links = wiki.user_link_re().findall(chunk)
    return _norm_user(links[-1]) if links else None


def parse_timestamp(m: re.Match[str], wiki: Wiki) -> datetime:
    hh, mm, day, month, year = m.groups()
    return datetime(
        int(year), wiki.months[month], int(day), int(hh), int(mm), tzinfo=timezone.utc
    )


def parse_comments(
    body: str, wiki: Wiki, is_outcome: bool = False, stats: dict[str, int] | None = None
) -> list[Comment]:
    ts_re = wiki.timestamp_re()
    vote_re = wiki.vote_re()
    noise_re = wiki.noise_re()

    comments: list[Comment] = []
    prev_end = 0
    for m in ts_re.finditer(body):
        start = _first_content_pos(body, prev_end, m.start())
        chunk = body[start:m.start()]
        raw = body[start:m.end()]
        prev_end = m.end()
        if not chunk.strip():
            if stats is not None:
                stats["empty"] = stats.get("empty", 0) + 1
            continue
        if noise_re and noise_re.search(raw):
            if stats is not None:
                stats["noise"] = stats.get("noise", 0) + 1
            continue
        author = _author_before(chunk, wiki)
        comment = Comment(
            idx=len(comments),
            author=author,
            ts=parse_timestamp(m, wiki),
            depth=_depth_at(body, start),
            parent=None,
            text=clean_text(chunk, wiki, has_author=author is not None),
            is_outcome=is_outcome,
            is_bot=bool(author and author in wiki.known_bots),
        )
        if vote_re:
            vm = vote_re.match(chunk)
            if vm:
                comment.vote = vm.group(1).capitalize()
        comments.append(comment)

    _link_parents(comments)
    return comments


def _link_parents(comments: list[Comment]) -> None:
    """Родитель — ближайшая предыдущая реплика строго меньшей глубины."""
    stack: list[Comment] = []
    for c in comments:
        while stack and stack[-1].depth >= c.depth:
            stack.pop()
        c.parent = stack[-1].idx if stack else None
        stack.append(c)


def parse_page(
    text: str, wiki: Wiki, page_title: str = "", stats: dict[str, int] | None = None
) -> list[Nomination]:
    """Разобрать страницу обсуждений в список номинаций."""
    # временные аккаунты подписываются как [[Служебная:Вклад/&#126;2026-…]] —
    # без раскрытия сущностей имя не вычленить
    text = _unescape(text)
    sections = split_sections(text, wiki.nomination_level)
    if not sections:
        # страница-номинация без собственного заголовка нужного уровня
        sections = [Section(page_title, text, 0)]

    nominations: list[Nomination] = []
    for sec in sections:
        body, outcomes = _split_outcome(sec.body, wiki)
        comments = parse_comments(body, wiki, stats=stats)
        for ob in outcomes:
            offset = len(comments)
            for c in parse_comments(ob, wiki, is_outcome=True, stats=stats):
                c.idx += offset
                c.parent = None if c.parent is None else c.parent + offset
                comments.append(c)

        nominations.append(
            Nomination(
                title=heading_title(sec.heading),
                heading_raw=sec.heading,
                struck=bool(re.search(r"</?s>|</?strike>", sec.heading, re.IGNORECASE)),
                comments=comments,
            )
        )
    return nominations


def _split_outcome(body: str, wiki: Wiki) -> tuple[str, list[str]]:
    """Отделить итоги от самой дискуссии — по позиции заголовка, а не по тексту."""
    if not wiki.outcome_headings:
        return body, []
    subs = split_sections(body, wiki.nomination_level + 1)
    outcome_subs = [s for s in subs if s.heading.strip() in wiki.outcome_headings]
    if not outcome_subs:
        return body, []
    return body[: outcome_subs[0].start], [s.body for s in outcome_subs]
