"""HTML-витрина из агрегатов report.build(): один файл, без внешних скриптов и CDN.

Формы — по смыслу данных: динамика недель со стеком судьбы, 100 % полосы для
части-от-целого (не бублик: два раздела на двух полосах сравнимы, на бубликах — нет),
горизонтальные столбики для категорий с длинными подписями, тепловая карта —
только для «когда пишут», таблица — для людей. Подсказки — нативные <title>.
"""

from __future__ import annotations

import html

C = {"blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a", "yellow": "#eda100",
     "magenta": "#e87ba4", "violet": "#4a3aa7", "gray": "#9a9892", "light": "#c9c7bf"}
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#1c5cab", "#104281"]
LIFE = [("discussing", "обсуждается", C["light"]), ("hanging", "висит без итога", C["gray"]),
        ("kept", "оставлена", C["blue"]), ("deleted", "удалена", C["orange"]),
        ("redirect", "перенаправление", C["aqua"]), ("moved", "переименована", C["yellow"]),
        ("recreated", "удалена и пересоздана", C["magenta"]), ("missing", "не найдена", "#6b6a66")]
TOPIC_LIFE = [("open", "открыта", C["light"]), ("kept", "оставлена", C["blue"]), ("deleted", "удалена", C["orange"]),
              ("redirect", "перенаправление", C["aqua"]), ("moved", "переименована", C["yellow"]),
              ("recreated", "пересоздана", C["magenta"])]
OUTCOME = {"delete": "удалить", "keep": "оставить", "redirect": "перенаправить", "merge": "объединить",
           "rename": "переименовать", "moved": "перенести", "withdrawn": "снята", "other": "иное"}
DELAY_ORDER = ["<1d", "1-7d", "8-14d", "15-30d", ">30d"]
CPN_ORDER = ["0", "1-2", "3-5", "6-10", "11-20", ">20"]
WD = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def esc(s) -> str:
    return html.escape(str(s))


def stacked_columns(series: dict[str, dict[str, int]], keys, width=560, height=180) -> str:
    xs = list(series)
    if not xs:
        return "<p class='muted'>нет данных</p>"
    m = max(sum(v.values()) for v in series.values()) or 1
    pad_l, pad_b, pad_t = 34, 22, 6
    cw = (width - pad_l) / len(xs)
    bw = max(cw - 3, 2)
    out = [f"<svg viewBox='0 0 {width} {height}' class='chart' role='img'>"]
    for g in range(5):
        y = pad_t + (height - pad_b - pad_t) * (1 - g / 4)
        out.append(f"<line x1='{pad_l}' x2='{width}' y1='{y:.1f}' y2='{y:.1f}' class='grid'/>"
                   f"<text x='{pad_l-4}' y='{y+3:.1f}' class='ax' text-anchor='end'>{round(m*g/4)}</text>")
    step = max(1, len(xs) // 6)
    for i, x in enumerate(xs):
        y0 = height - pad_b
        total = sum(series[x].values())
        for key, label, color in keys:
            n = series[x].get(key, 0)
            if not n:
                continue
            h = (height - pad_b - pad_t) * n / m
            y0 -= h
            out.append(f"<rect x='{pad_l + i*cw + 1.5:.1f}' y='{y0:.1f}' width='{bw:.1f}' height='{max(h-1,0):.1f}' "
                       f"fill='{color}'><title>неделя с {esc(x)} · {esc(label)}: {n} из {total}</title></rect>")
        if i % step == 0:
            out.append(f"<text x='{pad_l + i*cw + bw/2:.1f}' y='{height-6}' class='ax' text-anchor='middle'>{esc(x[5:])}</text>")
    out.append("</svg>")
    return "".join(out)


def hbar(items, color=C["blue"], width=560, row=22, total=None, labels=None) -> str:
    if not items:
        return "<p class='muted'>нет данных</p>"
    m = max(n for _, n in items) or 1
    lab_w = 200
    height = row * len(items) + 4
    out = [f"<svg viewBox='0 0 {width} {height}' class='chart' role='img'>"]
    for i, (label, n) in enumerate(items):
        y = i * row + 2
        w = (width - lab_w - 90) * n / m
        share = f" ({100*n/total:.0f}%)" if total else ""
        text = (labels or {}).get(label, label)
        out.append(f"<text x='{lab_w-8}' y='{y+row/2+4}' class='lab' text-anchor='end'>{esc(text)}</text>"
                   f"<rect x='{lab_w}' y='{y+3}' width='{w:.1f}' height='{row-8}' rx='3' fill='{color}'>"
                   f"<title>{esc(text)}: {n}{share}</title></rect>"
                   f"<text x='{lab_w + w + 6:.1f}' y='{y+row/2+4}' class='val'>{n}{esc(share)}</text>")
    out.append("</svg>")
    return "".join(out)


def stacked_hbar(rows, keys, width=560, row=24) -> str:
    if not rows:
        return "<p class='muted'>нет данных</p>"
    lab_w = 236
    height = row * len(rows) + 4
    out = [f"<svg viewBox='0 0 {width} {height}' class='chart' role='img'>"]
    for i, (label, parts) in enumerate(rows):
        y = i * row + 2
        total = sum(parts.values()) or 1
        x = lab_w
        out.append(f"<text x='{lab_w-8}' y='{y+row/2+4}' class='lab' text-anchor='end'>{esc(label)}</text>")
        for key, klabel, color in keys:
            n = parts.get(key, 0)
            if not n:
                continue
            w = (width - lab_w - 50) * n / total
            out.append(f"<rect x='{x:.1f}' y='{y+3}' width='{max(w-2,0):.1f}' height='{row-8}' fill='{color}'>"
                       f"<title>{esc(label)} · {esc(klabel)}: {n} из {total} ({100*n/total:.0f}%)</title></rect>")
            x += w
        out.append(f"<text x='{width-40}' y='{y+row/2+4}' class='val'>{total}</text>")
    out.append("</svg>")
    return "".join(out)


def heatmap(grid, width=560) -> str:
    m = max(max(r) for r in grid) or 1
    cell = (width - 30) / 24
    height = int(cell * 7 + 20)
    out = [f"<svg viewBox='0 0 {width} {height}' class='chart' role='img'>"]
    for d in range(7):
        out.append(f"<text x='24' y='{d*cell + cell/2 + 4:.1f}' class='ax' text-anchor='end'>{WD[d]}</text>")
        for h in range(24):
            v = grid[d][h]
            col = SEQ[min(int(v / m * (len(SEQ) - 1) + 0.999), len(SEQ) - 1)] if v else "#f0efe9"
            out.append(f"<rect x='{30 + h*cell + 1:.1f}' y='{d*cell + 1:.1f}' width='{cell-2:.1f}' height='{cell-2:.1f}' "
                       f"rx='2' fill='{col}'><title>{WD[d]} {h:02d}:00 UTC — {v} реплик</title></rect>")
    for h in range(0, 24, 3):
        out.append(f"<text x='{30 + h*cell + cell/2:.1f}' y='{height-4}' class='ax' text-anchor='middle'>{h:02d}</text>")
    out.append("</svg>")
    return "".join(out)


def legend(keys) -> str:
    return "<div class='legend'>" + "".join(
        f"<span><i style='background:{c}'></i>{esc(lab)}</span>" for _, lab, c in keys) + "</div>"


def table(rows, cols) -> str:
    head = "".join(f"<th>{esc(t)}</th>" for _, t in cols)
    body = "".join("<tr>" + "".join(f"<td>{esc(r.get(k, ''))}</td>" for k, _ in cols) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def wiki_block(dbname: str, W: dict) -> str:
    if W.get("empty"):
        return f"<section class='wiki'><h2 id='{dbname}'>{esc(W['label'])}</h2><p class='muted'>данных ещё нет</p></section>"
    k = W["kpi"]
    kpis = [("номинаций", k["nominations"]), ("статей", k["articles"]), ("реплик", k["comments"]),
            ("участников", k["participants"]), ("удалено", f"{100*k['share_deleted']:.0f}%"),
            ("оставлено", f"{100*k['share_kept']:.0f}%"), ("ещё открыто", f"{100*k['share_open']:.0f}%")]
    delay = [(b, W["deletion_delay"].get(b, 0)) for b in DELAY_ORDER]
    cpn = [(b, W["comments_per_nomination"].get(b, 0)) for b in CPN_ORDER]
    reasons = list(W["deletion_reasons"].items())
    okinds = list(W["outcome_kinds"].items())
    votes = list(W["votes"].items())
    kinds = W["kinds"]
    parts = [
        f"<section class='wiki'><h2 id='{dbname}'>{esc(W['label'])}</h2>",
        f"<p class='muted'>номинации {W['days'][0]} — {W['days'][1]}; страниц-статей {k['articles']}; "
        f"групповых номинаций {kinds.get('group', 0)}, не-статей {kinds.get('not_article', 0)}</p>",
        "<div class='kpis'>" + "".join(f"<div class='kpi'><b>{esc(v)}</b><span>{esc(t)}</span></div>" for t, v in kpis) + "</div>",
        "<div class='grid2'>",
        f"<figure><figcaption>Судьба статей по неделям номинации</figcaption>{stacked_columns(W['lifecycle_by_week'], LIFE)}{legend(LIFE)}</figure>",
        f"<figure><figcaption>Судьба статей (часть от целого)</figcaption>{stacked_hbar([('все статьи', W['lifecycle_total'])], LIFE)}"
        f"<figcaption>Через сколько дней после номинации удалили</figcaption>{hbar(delay, C['orange'], total=sum(v for _, v in delay))}</figure>",
        f"<figure><figcaption>Исход обсуждения — что решили люди</figcaption>{hbar(okinds, C['violet'], total=sum(v for _, v in okinds), labels=OUTCOME)}</figure>",
        f"<figure><figcaption>Основание удаления (по журналу)</figcaption>{hbar(reasons, C['orange'], total=sum(v for _, v in reasons))}</figure>",
        f"<figure><figcaption>Реплик на номинацию</figcaption>{hbar(cpn, C['blue'], total=k['nominations'])}</figure>",
        f"<figure><figcaption>Когда пишут (день недели × час UTC)</figcaption>{heatmap(W['heatmap'])}</figure>",
    ]
    if votes:
        parts.append(f"<figure><figcaption>Формальные позиции в репликах</figcaption>{hbar(votes, C['violet'], total=k['comments'])}</figure>")
    if W.get("topic_state"):
        rows = list(W["topic_state"].items())
        parts.append(f"<figure class='wide'><figcaption>Тема × судьба</figcaption>{stacked_hbar(rows, TOPIC_LIFE)}{legend(TOPIC_LIFE)}</figure>")
    parts.append("</div>")
    parts.append("<figure class='wide'><figcaption>Самые активные (боты и временные аккаунты исключены)</figcaption>" +
                 table(W["top_participants"], [("user", "участник"), ("comments", "реплик"),
                                              ("nominations", "номинаций"), ("closes", "итогов")]) + "</figure>")
    parts.append("</section>")
    return "".join(parts)


CSS = """
:root{color-scheme:light}
body{margin:0;background:#fcfcfb;color:#0b0b0b;font:14px/1.45 system-ui,Segoe UI,Roboto,sans-serif}
main{max-width:1240px;margin:0 auto;padding:20px 24px 60px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 2px}
.muted{color:#52514e;font-size:12.5px;margin:2px 0 12px}
nav a{margin-right:14px;font-size:13px}
.kpis{display:flex;gap:12px;flex-wrap:wrap;margin:8px 0 14px}
.kpi{background:#f3f2ec;border-radius:8px;padding:8px 14px;min-width:96px}
.kpi b{display:block;font-size:22px;font-weight:600}.kpi span{color:#52514e;font-size:12px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(520px,1fr));gap:18px 28px}
figure{margin:0;padding:10px 12px;background:#fff;border:1px solid #e1e0d9;border-radius:8px}
figure.wide{grid-column:1/-1}figure.wide .chart{max-width:640px}
figcaption{font-weight:600;font-size:13px;margin:2px 0 6px}
.chart{width:100%;height:auto;display:block}
.grid{stroke:#e1e0d9;stroke-width:1}.ax{font-size:10px;fill:#52514e}.lab{font-size:11px;fill:#0b0b0b}.val{font-size:11px;fill:#52514e}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:#52514e;margin:6px 0 2px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:4px 8px;border-bottom:1px solid #e1e0d9}
td:not(:first-child),th:not(:first-child){text-align:right}
.note{background:#fff8e6;border:1px solid #f0d78a;border-radius:8px;padding:10px 14px;font-size:13px;margin:12px 0}
footer{margin-top:40px;color:#52514e;font-size:12px}
"""


def render(report: dict, order: list[str] | None = None) -> str:
    wikis = report["wikis"]
    order = order or list(wikis)
    nav = " ".join(f"<a href='#{w}'>{esc(wikis[w]['label'])}</a>" for w in order if w in wikis)
    doc = [
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>talk-snapshots — жизненный цикл номинированных на удаление статей</title>",
        f"<style>{CSS}</style></head><body><main>",
        "<h1>talk-snapshots: что происходит со статьями после номинации на удаление</h1>",
        f"<p class='muted'>Обновлено {esc(report['generated'])} UTC · данные: обсуждения (DiscussionTools), журналы удалений и "
        "состояние страниц (реплики баз Wikimedia). <a href='/api/report.json'>JSON</a> · "
        "<a href='https://github.com/ruwiki/talk-snapshots'>код</a></p>",
        f"<nav>{nav}</nav>",
        "<div class='note'><b>Судьба страницы</b> — по журналам: существует / удалена / перенаправление / переименована. "
        "<b>Исход обсуждения</b> — что записали подводившие итог; это разные вещи: статью могут оставить итогом и удалить "
        "быстро через месяц. «Обсуждается» — итога нет и номинации меньше двух недель; «висит» — старше двух недель "
        "без итога и без записи в журнале. Не-статьи (категории, шаблоны, проектные страницы) в судьбу не входят.</div>",
    ]
    for w in order:
        if w in wikis:
            doc.append(wiki_block(w, wikis[w]))
    doc.append("<footer>talk-snapshots · Toolforge · Apache-2.0</footer></main></body></html>")
    return "".join(doc)
