"""HTML-витрина из агрегатов report.build(): без внешних скриптов и CDN.

Два вида страниц. Обзор (`render_overview`) — по-английски, разделы по убыванию
объёма, одна сравнимая форма: 100 % полоса судьбы статей на раздел. Страница
раздела (`render_wiki`) — целиком на языке раздела (app/i18n.py).

Формы — по смыслу данных: динамика недель со стеком судьбы, 100 % полосы для
части-от-целого (не бублик: разделы на полосах сравнимы), горизонтальные
столбики для категорий с длинными подписями, тепловая карта — только для
«когда пишут», таблица — для людей. Подсказки — нативные <title>.
"""

from __future__ import annotations

import html

from .i18n import t, weekdays

C = {"blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a", "yellow": "#eda100",
     "magenta": "#e87ba4", "violet": "#4a3aa7", "gray": "#9a9892", "light": "#c9c7bf"}
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#1c5cab", "#104281"]
LIFE_KEYS = [("discussing", C["light"]), ("hanging", C["gray"]), ("kept", C["blue"]),
             ("deleted", C["orange"]), ("redirect", C["aqua"]), ("moved", C["yellow"]),
             ("recreated", C["magenta"]), ("missing", "#6b6a66")]
TOPIC_KEYS = [("open", C["light"]), ("kept", C["blue"]), ("deleted", C["orange"]),
              ("redirect", C["aqua"]), ("moved", C["yellow"]), ("recreated", C["magenta"])]
DELAY_ORDER = ["<1d", "1-7d", "8-14d", "15-30d", ">30d"]
CPN_ORDER = ["0", "1-2", "3-5", "6-10", "11-20", ">20"]


def esc(s) -> str:
    return html.escape(str(s))


def _life(lang):
    return [(k, t(lang, f"life_{k}"), c) for k, c in LIFE_KEYS]


def stacked_columns(series: dict[str, dict[str, int]], keys, lang: str, width=560, height=180) -> str:
    xs = list(series)
    if not xs:
        return f"<p class='muted'>{t(lang, 'no_data')}</p>"
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
            tip = t(lang, "week_of", date=x) + f" · {label}: " + t(lang, "of_total", n=n, total=total)
            out.append(f"<rect x='{pad_l + i*cw + 1.5:.1f}' y='{y0:.1f}' width='{bw:.1f}' "
                       f"height='{max(h-1,0):.1f}' fill='{color}'><title>{esc(tip)}</title></rect>")
        if i % step == 0:
            out.append(f"<text x='{pad_l + i*cw + bw/2:.1f}' y='{height-6}' class='ax' text-anchor='middle'>{esc(x[5:])}</text>")
    out.append("</svg>")
    return "".join(out)


def hbar(items, lang: str, color=C["blue"], width=560, row=22, total=None, labels=None) -> str:
    if not items:
        return f"<p class='muted'>{t(lang, 'no_data')}</p>"
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


def stacked_hbar(rows, keys, lang: str, width=560, row=24, links=None) -> str:
    if not rows:
        return f"<p class='muted'>{t(lang, 'no_data')}</p>"
    lab_w = 236
    height = row * len(rows) + 4
    out = [f"<svg viewBox='0 0 {width} {height}' class='chart' role='img'>"]
    for i, (label, parts) in enumerate(rows):
        y = i * row + 2
        total = sum(parts.values()) or 1
        x = lab_w
        text = f"<text x='{lab_w-8}' y='{y+row/2+4}' class='lab' text-anchor='end'>{esc(label)}</text>"
        if links and label in links:
            text = f"<a href='{esc(links[label])}'>{text}</a>"
        out.append(text)
        for key, klabel, color in keys:
            n = parts.get(key, 0)
            if not n:
                continue
            w = (width - lab_w - 50) * n / total
            tip = f"{label} · {klabel}: " + t(lang, "of_total", n=n, total=total) + f" ({100*n/total:.0f}%)"
            out.append(f"<rect x='{x:.1f}' y='{y+3}' width='{max(w-2,0):.1f}' height='{row-8}' fill='{color}'>"
                       f"<title>{esc(tip)}</title></rect>")
            x += w
        out.append(f"<text x='{width-40}' y='{y+row/2+4}' class='val'>{total}</text>")
    out.append("</svg>")
    return "".join(out)


def heatmap(grid, lang: str, width=560) -> str:
    wd = weekdays(lang)
    m = max(max(r) for r in grid) or 1
    cell = (width - 30) / 24
    height = int(cell * 7 + 20)
    out = [f"<svg viewBox='0 0 {width} {height}' class='chart' role='img'>"]
    for d in range(7):
        out.append(f"<text x='24' y='{d*cell + cell/2 + 4:.1f}' class='ax' text-anchor='end'>{esc(wd[d])}</text>")
        for h in range(24):
            v = grid[d][h]
            col = SEQ[min(int(v / m * (len(SEQ) - 1) + 0.999), len(SEQ) - 1)] if v else "#f0efe9"
            tip = f"{wd[d]} {h:02d}:00 UTC — " + t(lang, "comments_short", n=v)
            out.append(f"<rect x='{30 + h*cell + 1:.1f}' y='{d*cell + 1:.1f}' width='{cell-2:.1f}' "
                       f"height='{cell-2:.1f}' rx='2' fill='{col}'><title>{esc(tip)}</title></rect>")
    for h in range(0, 24, 3):
        out.append(f"<text x='{30 + h*cell + cell/2:.1f}' y='{height-4}' class='ax' text-anchor='middle'>{h:02d}</text>")
    out.append("</svg>")
    return "".join(out)


def legend(keys) -> str:
    return "<div class='legend'>" + "".join(
        f"<span><i style='background:{c}'></i>{esc(lab)}</span>" for _, lab, c in keys) + "</div>"


def table(rows, cols) -> str:
    head = "".join(f"<th>{esc(title)}</th>" for _, title in cols)
    body = "".join("<tr>" + "".join(f"<td>{esc(r.get(k, ''))}</td>" for k, _ in cols) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


CSS = """
:root{color-scheme:light}
body{margin:0;background:#fcfcfb;color:#0b0b0b;font:14px/1.45 system-ui,Segoe UI,Roboto,sans-serif}
main{max-width:1240px;margin:0 auto;padding:20px 24px 60px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 2px}
.muted{color:#52514e;font-size:12.5px;margin:2px 0 12px}
nav{margin:6px 0 14px}nav a{margin-right:14px;font-size:13px}
.kpis{display:flex;gap:12px;flex-wrap:wrap;margin:8px 0 14px}
.kpi{background:#f3f2ec;border-radius:8px;padding:8px 14px;min-width:96px}
.kpi b{display:block;font-size:22px;font-weight:600}.kpi span{color:#52514e;font-size:12px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(520px,1fr));gap:18px 28px}
figure{margin:0;padding:10px 12px;background:#fff;border:1px solid #e1e0d9;border-radius:8px}
figure.wide{grid-column:1/-1}figure.wide .chart{max-width:640px}
figcaption{font-weight:600;font-size:13px;margin:2px 0 6px}
.chart{width:100%;height:auto;display:block}
.grid{stroke:#e1e0d9;stroke-width:1}.ax{font-size:10px;fill:#52514e}.lab{font-size:11px;fill:#0b0b0b}.val{font-size:11px;fill:#52514e}
svg a .lab{fill:#2a78d6}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:#52514e;margin:6px 0 2px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:4px 8px;border-bottom:1px solid #e1e0d9}
td:not(:first-child),th:not(:first-child){text-align:right}
.note{background:#fff8e6;border:1px solid #f0d78a;border-radius:8px;padding:10px 14px;font-size:13px;margin:12px 0}
.ov-table td:first-child a{text-decoration:none}
footer{margin-top:40px;color:#52514e;font-size:12px}
"""


def _shell(lang: str, title: str, body: str) -> str:
    return (f"<!doctype html><html lang='{esc(lang)}'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{esc(title)}</title><style>{CSS}</style></head><body><main>{body}"
            "<footer>talk-snapshots · Toolforge · Apache-2.0 · "
            "<a href='https://github.com/ruwiki/talk-snapshots'>GitHub</a></footer></main></body></html>")


def order_by_scale(report: dict) -> list[str]:
    def key(w):
        d = report["wikis"][w]
        return -(d.get("kpi", {}).get("nominations", 0))
    return sorted(report["wikis"], key=key)


def render_overview(report: dict) -> str:
    lang = "en"
    order = order_by_scale(report)
    wikis = report["wikis"]
    rows, links, kpi_rows = [], {}, []
    for w in order:
        d = wikis[w]
        if d.get("empty"):
            continue
        rows.append((d["label"], d["lifecycle_total"]))
        links[d["label"]] = f"/wiki/{w}"
        k = d["kpi"]
        kpi_rows.append({
            "wiki": d["label"], "_href": f"/wiki/{w}",
            "nominations": k["nominations"], "articles": k["articles"], "comments": k["comments"],
            "participants": k["participants"],
            "deleted": f"{100*k['share_deleted']:.0f}%", "kept": f"{100*k['share_kept']:.0f}%",
            "open": f"{100*k['share_open']:.0f}%",
        })
    life = _life(lang)
    cols = [("wiki", ""), ("nominations", t(lang, "kpi_nominations")), ("articles", t(lang, "kpi_articles")),
            ("comments", t(lang, "kpi_comments")), ("participants", t(lang, "kpi_participants")),
            ("deleted", t(lang, "kpi_deleted")), ("kept", t(lang, "kpi_kept")), ("open", t(lang, "kpi_open"))]
    head = "".join(f"<th>{esc(c)}</th>" for _, c in cols)
    trs = "".join(
        "<tr><td><a href='" + esc(r["_href"]) + "'>" + esc(r["wiki"]) + "</a></td>" +
        "".join(f"<td>{esc(r[k])}</td>" for k, _ in cols[1:]) + "</tr>"
        for r in kpi_rows)
    body = (
        f"<h1>{esc(t(lang, 'site_title'))}</h1>"
        f"<p class='muted'>{esc(t(lang, 'updated', date=report['generated']))} · {esc(t(lang, 'sources'))} · "
        f"<a href='/api/report.json'>JSON</a></p>"
        f"<p>{esc(t(lang, 'ov_lead'))}</p>"
        f"<figure class='wide'><figcaption>{esc(t(lang, 'ov_fate'))} — {esc(t(lang, 'ov_hint'))}</figcaption>"
        f"{stacked_hbar(rows, life, lang, width=1160, row=26, links=links)}{legend(life)}</figure>"
        f"<figure class='wide'><table class='ov-table'><thead><tr>{head}</tr></thead><tbody>{trs}</tbody></table></figure>"
        f"<div class='note'>{t(lang, 'note')}</div>"
    )
    return _shell(lang, t(lang, "site_title"), body)


def render_wiki(dbname: str, W: dict, report: dict, lang: str) -> str:
    nav = f"<nav><a href='/'>← {esc(t(lang, 'overview'))}</a></nav>"
    if W.get("empty"):
        return _shell(lang, W["label"], nav + f"<h1>{esc(W['label'])}</h1><p class='muted'>{t(lang, 'no_data')}</p>")
    k = W["kpi"]
    life = _life(lang)
    kpis = [(t(lang, "kpi_nominations"), k["nominations"]), (t(lang, "kpi_articles"), k["articles"]),
            (t(lang, "kpi_comments"), k["comments"]), (t(lang, "kpi_participants"), k["participants"]),
            (t(lang, "kpi_deleted"), f"{100*k['share_deleted']:.0f}%"),
            (t(lang, "kpi_kept"), f"{100*k['share_kept']:.0f}%"),
            (t(lang, "kpi_open"), f"{100*k['share_open']:.0f}%")]
    delay = [(b, W["deletion_delay"].get(b, 0)) for b in DELAY_ORDER]
    cpn = [(b, W["comments_per_nomination"].get(b, 0)) for b in CPN_ORDER]

    def reason_label(r: str) -> str:
        if r.startswith("speedy"):
            return (t(lang, "reason_speedy") + r.removeprefix("speedy")).strip()
        return t(lang, f"reason_{r}") if r in ("discussion", "other") else r

    reasons = [(reason_label(r), n) for r, n in W["deletion_reasons"].items()]
    out_labels = {kk: t(lang, f"out_{kk}") for kk in
                  ("delete", "keep", "redirect", "merge", "rename", "moved", "withdrawn", "other", "revdel", "relisted")}
    okinds = [(out_labels.get(kk, kk), n) for kk, n in W["outcome_kinds"].items()]
    votes = list(W["votes"].items())
    kinds = W["kinds"]
    meta = t(lang, "meta_line", a=W["days"][0], b=W["days"][1], n=k["articles"],
             g=kinds.get("group", 0), na=kinds.get("not_article", 0))
    parts = [
        nav,
        f"<h1>{esc(W['label'])}</h1>",
        f"<p class='muted'>{esc(meta)} · {esc(t(lang, 'updated', date=report['generated']))} · "
        f"<a href='/api/report.json'>JSON</a></p>",
        f"<div class='note'>{t(lang, 'note')}</div>",
        "<div class='kpis'>" + "".join(f"<div class='kpi'><b>{esc(v)}</b><span>{esc(name)}</span></div>"
                                       for name, v in kpis) + "</div>",
        "<div class='grid2'>",
        f"<figure><figcaption>{esc(t(lang, 'ch_week'))}</figcaption>"
        f"{stacked_columns(W['lifecycle_by_week'], life, lang)}{legend(life)}</figure>",
        f"<figure><figcaption>{esc(t(lang, 'ch_share'))}</figcaption>"
        f"{stacked_hbar([(t(lang, 'all_articles'), W['lifecycle_total'])], life, lang)}"
        f"<figcaption>{esc(t(lang, 'ch_delay'))}</figcaption>"
        f"{hbar(delay, lang, C['orange'], total=sum(v for _, v in delay))}</figure>",
        f"<figure><figcaption>{esc(t(lang, 'ch_outcome'))}</figcaption>"
        f"{hbar(okinds, lang, C['violet'], total=sum(n for _, n in okinds))}</figure>",
        f"<figure><figcaption>{esc(t(lang, 'ch_reasons'))}</figcaption>"
        f"{hbar(reasons, lang, C['orange'], total=sum(n for _, n in reasons))}</figure>",
        f"<figure><figcaption>{esc(t(lang, 'ch_cpn'))}</figcaption>"
        f"{hbar(cpn, lang, C['blue'], total=k['nominations'])}</figure>",
        f"<figure><figcaption>{esc(t(lang, 'ch_heat'))}</figcaption>{heatmap(W['heatmap'], lang)}</figure>",
    ]
    if votes:
        parts.append(f"<figure><figcaption>{esc(t(lang, 'ch_votes'))}</figcaption>"
                     f"{hbar(votes, lang, C['violet'], total=k['comments'])}</figure>")
    if W.get("topic_state"):
        topic = [(kk, t(lang, f"life_{kk}"), c) for kk, c in TOPIC_KEYS]
        parts.append(f"<figure class='wide'><figcaption>{esc(t(lang, 'ch_topic'))}</figcaption>"
                     f"{stacked_hbar(list(W['topic_state'].items()), topic, lang)}{legend(topic)}</figure>")
    parts.append("</div>")
    parts.append(f"<figure class='wide'><figcaption>{esc(t(lang, 'ch_top'))}</figcaption>" +
                 table(W["top_participants"], [("user", t(lang, "th_user")), ("comments", t(lang, "th_comments")),
                                               ("nominations", t(lang, "th_nominations")), ("closes", t(lang, "th_closes"))]) +
                 "</figure>")
    return _shell(lang, W["label"], "".join(parts))
