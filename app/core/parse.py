"""ЗАПАСНОЙ путь: разбор вики-текста, когда API вызвать нельзя.

Основной источник структуры — core/threads.py (DiscussionTools): движок
сегментирует обсуждение точнее, чем регулярки по подписям, и отдаёт автора,
время и вложенность полями. Этот модуль нужен там, где API недоступен по
стоимости: офлайн-обработка дампов за годы и по сотням разделов.

Единица разбора — подпись: реплика заканчивается меткой времени, а начинается
там, где закончилась предыдущая. Формат голосования не используется, поэтому
разбор одинаково работает на дневной странице и на странице номинации.
Насколько он проигрывает движку — меряется в tests/test_vs_engine.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from ..models import Comment, Nomination

#: маркеры отступа в начале строки
INDENT = re.compile(r"^([*:#]+)", re.MULTILINE)
#: [[ссылка|подпись]] → подпись, [[ссылка]] → ссылка
LINK = re.compile(r"\[\[([^|\]]+)(?:\|([^\]]*))?\]\]")
NOWIKI_ENTITY = re.compile(r"&#(\d+);")
#: хвост предыдущей реплики, затекающий в начало следующей: закрытия шаблонов и тегов.
#: без \A и ^ — якорем служит сама позиция, с которой вызван match()
LEFTOVER = re.compile(r"(?:\s*(?:\}\}|</\w+>|</?div[^>]*>|\)|\||<br\s*/?>))+", re.IGNORECASE)


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
        return links[0][0].lstrip(":").strip()
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
    pattern = re.compile(rf"^{eq}([^=].*?){eq}\s*$", re.MULTILINE)
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


def clean_text(chunk: str, spec, has_author: bool) -> str:
    """Убрать из реплики служебную обвязку и собственную подпись.

    Подпись отрезается по началу последней ссылки на участника — но только
    если после неё почти ничего нет. Иначе это не подпись, а упоминание
    коллеги внутри текста, и резать по нему нельзя.
    """
    loc = spec.locale
    text = chunk
    for pat in loc.boilerplate_patterns:
        text = re.sub(pat, "", text, flags=re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if has_author:
        last = None
        for m in loc.user_link_re().finditer(text):
            last = m
        if last is not None and len(text) - last.end() <= 80:
            head = text[: last.start()]
            # подпись часто состоит из нескольких ссылок подряд — срезаем весь блок,
            # но только ссылки на участников: [[ВП:КОПИВИО]] — это уже текст реплики
            tail_re = re.compile(
                rf"(?:[-–—|,;:()\[\]{{}}\s]|<[^>]+>|{loc.user_link_full_re().pattern})+$",
                re.IGNORECASE,
            )
            text = tail_re.sub("", head)
    text = re.sub(r"^[\s*:#]+", "", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _author_before(chunk: str, spec) -> str | None:
    """Автор — последняя ссылка на участника перед меткой времени.

    Последняя, а не первая: подпись почти всегда выглядит как
    «[[У:Имя|Имя]] ([[ОУ:Имя|обс.]]) время», и обе ссылки ведут к одному
    человеку, но у оформленных подписей первой может оказаться чужая ссылка
    из текста реплики.
    """
    links = spec.locale.user_link_re().findall(chunk)
    return _norm_user(links[-1]) if links else None


def parse_timestamp(m: re.Match[str], spec) -> datetime:
    g = m.groupdict()
    loc = spec.locale
    month = g["month"]
    month_n = loc.months.get(month) or loc.months.get(month.rstrip(".")) or int(month)
    tz = UTC if loc.tz == "UTC" else ZoneInfo(loc.tz)
    local = datetime(int(g["year"]), month_n, int(g["day"]), int(g["hh"]), int(g["mm"]), tzinfo=tz)
    return local.astimezone(UTC)


def parse_comments(
    body: str, spec, is_outcome: bool = False, stats: dict[str, int] | None = None,
    section: str | None = None,
) -> list[Comment]:
    loc = spec.locale
    ts_re = loc.timestamp_re()
    vote_re = spec.stance.wikitext_re()
    noise_re = loc.noise_re()

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
        author = _author_before(chunk, spec)
        comment = Comment(
            idx=len(comments),
            author=author,
            ts=parse_timestamp(m, spec),
            depth=_depth_at(body, start),
            parent=None,
            text=clean_text(chunk, spec, has_author=author is not None),
            is_outcome=is_outcome,
            is_bot=bool(author and author in loc.known_bots),
            section=section,
        )
        if vote_re:
            vm = vote_re.match(chunk)
            if vm:
                comment.vote = vm.group(1).capitalize()
        elif section is not None:
            comment.vote = spec.stance.of_comment(comment, section)
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
    text: str, spec, page_title: str = "", stats: dict[str, int] | None = None
) -> list[Nomination]:
    """Разобрать страницу обсуждений в список номинаций."""
    # временные аккаунты подписываются как [[Служебная:Вклад/&#126;2026-…]] —
    # без раскрытия сущностей имя не вычленить
    text = _unescape(text)
    sections = split_sections(text, spec.nomination_level)
    if not sections:
        # страница-номинация без собственного заголовка нужного уровня
        sections = [Section(page_title, text, 0)]

    nominations: list[Nomination] = []
    for sec in sections:
        body, outcomes = _split_outcome(sec.body, spec)
        comments = parse_comments(body, spec, stats=stats)
        for ob in outcomes:
            offset = len(comments)
            for c in parse_comments(ob, spec, is_outcome=True, stats=stats):
                c.idx += offset
                c.parent = None if c.parent is None else c.parent + offset
                comments.append(c)

        nom = Nomination(
            title=heading_title(sec.heading),
            heading_raw=sec.heading,
            struck=bool(re.search(r"</?s>|</?strike>", sec.heading, re.IGNORECASE)),
            comments=comments,
            source_page=page_title if page_title and not sections[0].start else None,
        )
        for sub in split_sections(sec.body, spec.nomination_level + 1):
            nom.subheadings.append((spec.nomination_level + 1, heading_title(sub.heading), sub.heading))
        nom.pages = spec.resolve_pages(nom)
        spec.outcome.apply(nom, spec, sec.body)
        nominations.append(nom)
    return nominations


def _split_outcome(body: str, spec) -> tuple[str, list[str]]:
    """Отделить итоги от самой дискуссии — по позиции заголовков, а не по тексту.

    Итог может стоять подсекцией номинации (=== Итог ===) или подсекцией
    отдельной статьи в группе (==== Итог ====). Диапазон итога тянется до
    следующего заголовка того же или более высокого уровня; всё, что вне
    диапазонов, — дискуссия, включая статьи группы после чужого итога.
    """
    names = spec.outcome.section_names
    if not names:
        return body, []
    level = spec.nomination_level + 1
    heads = [
        (m.start(), m.end(), len(m.group(1)), m.group(2).strip())
        for m in re.finditer(rf"^(={{{level},6}})([^=\n][^\n]*?)\1\s*$", body, re.MULTILINE)
    ]
    ranges: list[tuple[int, int]] = []
    for i, (start, _end, lvl, text) in enumerate(heads):
        if text not in names:
            continue
        stop = len(body)
        for s2, _, l2, _ in heads[i + 1:]:
            if l2 <= lvl:
                stop = s2
                break
        if ranges and start < ranges[-1][1]:
            continue  # вложен в уже взятый диапазон
        ranges.append((start, stop))
    if not ranges:
        return body, []
    parts, pos = [], 0
    for a, b in ranges:
        parts.append(body[pos:a])
        pos = b
    parts.append(body[pos:])
    return "\n".join(parts), [body[a:b] for a, b in ranges]
