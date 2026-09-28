"""Критерии быстрого удаления по разделам: «недостаток → как удаляют в этой Википедии».

Данные — снимок app/data/speedy.json (собирается в вольте из разведки 51 вики, журналы за месяц снимка).
Три страницы: /speedy — недостатки по семействам; /speedy/<family>/<id> — один недостаток во всех вики;
/speedy/wiki/<db> — все недостатки одной вики.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from urllib.parse import quote

from .page import _shell, esc

DATA = Path(__file__).parent / "data" / "speedy.json"
STATUS_ORDER = {"speedy": 0, "slow": 1, "discussion": 2, "removed": 3, "absent": 4}
STATUS_TEXT = {
    "speedy": "speedy deletion",
    "slow": "tag and wait",
    "discussion": "only through a discussion",
    "removed": "removed from the rules",
    "absent": "no such criterion",
}
CSS = (".st-speedy{color:#1a7f37}.st-slow{color:#9a6700}.st-discussion{color:#0969da}"
       ".st-removed,.st-absent{color:#8c959f}code{white-space:pre-wrap;word-break:break-word}"
       ".muted a{margin-right:.6em}")


@cache
def data() -> dict:
    d = json.loads(DATA.read_text(encoding="utf-8"))
    d["by_key"] = {s["key"]: s for s in d["subclasses"]}
    return d


def _url_key(key: str) -> str:
    fam, sid = key.split(":", 1)
    return f"/speedy/{fam}/{quote(sid)}"


def _rules_link(wiki: str) -> str:
    p = data()["policy"].get(wiki) or {}
    if not p.get("host") or not p.get("page"):
        return ""
    href = f"https://{p['host']}/wiki/{quote(p['page'].replace(' ', '_'), safe=':/()')}"
    return f"<a href='{esc(href)}'>rules</a>"


def _mark(c: dict) -> str:
    if c.get("how"):
        return esc(c["how"])
    t = c.get("template")
    if not t:
        return ""
    if "{{" in t:
        code = t
    elif c.get("param") and "|" not in t:
        code = f"{{{{{t}|{c['param']}}}}}"
    else:
        code = f"{{{{{t}}}}}"
    return f"<code>{esc(code)}</code>"


def _status(c: dict) -> str:
    s = c["status"]
    extra = " (de facto)" if c.get("defacto") else ""
    wait = f", {esc(c['wait'])} days" if s == "slow" and c.get("wait") and str(c["wait"]).isdigit() else ""
    return f"<span class='st-{s}'>{esc(STATUS_TEXT[s])}{wait}{extra}</span>"


def _cells(key: str | None = None, wiki: str | None = None) -> list[dict]:
    return [c for c in data()["cells"]
            if (key is None or c["key"] == key) and (wiki is None or c["wiki"] == wiki)]


def _wikis() -> list[str]:
    return sorted({c["wiki"] for c in data()["cells"]})


def _coverage(key: str) -> dict:
    best: dict[str, str] = {}
    for c in _cells(key=key):
        cur = best.get(c["wiki"], "absent")
        if STATUS_ORDER[c["status"]] < STATUS_ORDER[cur]:
            best[c["wiki"]] = c["status"]
    out = {s: 0 for s in STATUS_ORDER}
    for w in _wikis():
        out[best.get(w, "absent")] += 1
    return out


def _wiki_nav() -> str:
    return "<p class='muted'>" + "".join(f"<a href='/speedy/wiki/{esc(w)}'>{esc(w)}</a>" for w in _wikis()) + "</p>"


def render_index() -> str:
    d = data()
    parts = ["<nav><a href='/'>← overview</a></nav><h1>Speedy deletion across Wikipedias</h1>",
             f"<p>What is wrong with the page → how each of {len(_wikis())} Wikipedias deletes it: the local criterion, "
             "the tag to place, what reason people actually write, and whether the criterion is alive. "
             f"Survey of the rules, the admins' reason menu and the full deletion log for {esc(d['snapshot'])}; "
             "counts exclude mass runs by one bot or admin. Prototype: mappings were made by reading each wiki's rules "
             "and may contain errors — corrections welcome.</p>",
             "<h2>By Wikipedia</h2>", _wiki_nav()]
    for fam, fname in d["families"].items():
        rows = []
        for s in d["subclasses"]:
            if s["family"] != int(fam):
                continue
            cov = _coverage(s["key"])
            rows.append(f"<tr><td><a href='{_url_key(s['key'])}'>{esc(s['name'])}</a></td>"
                        f"<td>{esc(s.get('en_label') or '')}</td><td>{cov['speedy']}</td><td>{cov['slow'] or ''}</td>"
                        f"<td>{cov['discussion'] or ''}</td><td>{cov['absent'] + cov['removed']}</td></tr>")
        parts.append(f"<h2>{esc(fam)}. {esc(fname)}</h2><table class='ov-table'><thead><tr><th>defect</th>"
                     "<th>enwiki</th><th>speedy</th><th>tag and wait</th><th>discussion only</th><th>none</th></tr></thead>"
                     f"<tbody>{''.join(rows)}</tbody></table>")
    return _shell("en", "Speedy deletion across Wikipedias", f"<style>{CSS}</style>" + "".join(parts))


def render_defect(key: str) -> str | None:
    s = data()["by_key"].get(key)
    if s is None:
        return None
    cells = _cells(key=key)
    have = {c["wiki"] for c in cells}
    cells += [{"wiki": w, "status": "absent"} for w in _wikis() if w not in have]
    cells.sort(key=lambda c: (STATUS_ORDER[c["status"]], -(c.get("clean") or 0), c["wiki"]))
    rows = []
    for c in cells:
        live = "" if c["status"] == "absent" else ("—" if c.get("clean") is None else str(c["clean"]))
        rows.append(f"<tr id='{esc(c['wiki'])}'><td><a href='/speedy/wiki/{esc(c['wiki'])}'>{esc(c['wiki'])}</a></td>"
                    f"<td>{_status(c)}</td><td>{esc(c.get('code') or '')}</td><td>{esc(c.get('name') or '')}</td>"
                    f"<td>{_mark(c)}</td><td>{esc(c.get('reason') or '')}</td><td>{live}</td>"
                    f"<td>{_rules_link(c['wiki']) if c['status'] != 'absent' else ''}</td></tr>")
    label = f" ({esc(s['en_label'])} on enwiki)" if s.get("en_label") else ""
    body = (f"<nav><a href='/speedy'>← all defects</a></nav><h1>{esc(s['name'])}{label}</h1>"
            "<p class='muted'>«what people write» is the most frequent reason in the deletion log; "
            "«deletions» are per month without mass runs.</p>"
            "<figure class='wide'><table class='ov-table'><thead><tr><th>wiki</th><th>status</th><th>code</th>"
            "<th>local name</th><th>how to request</th><th>what people write</th><th>deletions</th><th></th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></figure>")
    return _shell("en", s["name"], f"<style>{CSS}</style>" + body)


def render_wiki(wiki: str) -> str | None:
    if wiki not in _wikis():
        return None
    d = data()
    parts = [f"<nav><a href='/speedy'>← all defects</a></nav><h1>Speedy deletion on {esc(wiki)}</h1>",
             f"<p>{_rules_link(wiki)}</p>"]
    for fam, fname in d["families"].items():
        rows = []
        for s in d["subclasses"]:
            if s["family"] != int(fam):
                continue
            cells = _cells(key=s["key"], wiki=wiki) or [{"status": "absent"}]
            for c in sorted(cells, key=lambda c: STATUS_ORDER[c["status"]]):
                live = "" if c["status"] == "absent" else ("—" if c.get("clean") is None else str(c["clean"]))
                rows.append(f"<tr><td><a href='{_url_key(s['key'])}#{esc(wiki)}'>{esc(s['name'])}</a></td>"
                            f"<td>{_status(c)}</td><td>{esc(c.get('code') or '')}</td><td>{esc(c.get('name') or '')}</td>"
                            f"<td>{_mark(c)}</td><td>{esc(c.get('reason') or '')}</td><td>{live}</td></tr>")
        parts.append(f"<h2>{esc(fam)}. {esc(fname)}</h2><figure class='wide'><table class='ov-table'><thead><tr>"
                     "<th>defect</th><th>status</th><th>code</th><th>local name</th><th>how to request</th>"
                     f"<th>what people write</th><th>deletions</th></tr></thead><tbody>{''.join(rows)}</tbody></table></figure>")
    return _shell("en", f"Speedy deletion on {wiki}", f"<style>{CSS}</style>" + "".join(parts))
