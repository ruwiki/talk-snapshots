# talk-snapshots

Who argues with whom, about which topics, in deletion discussions — across
Russian and English Wikipedia with one codebase.

The participation layer (who spoke, when, replying to whom) is
format-independent and works on any wiki. Stances are a per-wiki plugin,
because the formats genuinely differ: English Wikipedia bolds `Keep`/`Delete`,
Russian Wikipedia has no formal voting in deletion discussions at all.
Measured on 1,940 loaded comments: **35% of comments carry a formal stance on
enwiki against 1.4% on ruwiki**.

## Three sources, not one

| Source | What it provides | Module |
|---|---|---|
| **DiscussionTools API** | thread structure as MediaWiki itself sees it: author, timestamp, nesting, `transcludedfrom` | `app/threads.py` |
| **Revision history** (wiki replicas on Toolforge, API elsewhere) | what the text cannot show: who edited someone else's comment, who closed the discussion, who moved a nomination; plus engine tags such as `discussiontools-added-comment` | `app/revisions.py` |
| **Wikitext parsing** | fallback for dump processing, where an API call per page is not affordable | `app/parse.py` |

That order is deliberate. Signature parsing is the fallback, not the
foundation: on the ruwiki deletion log for 1 July 2026 the engine finds 121
comments where the hand-rolled parser finds 102 (**84%**), with 95% agreement
on participants. The gap is pinned by `tests/test_vs_engine.py` so it cannot
grow unnoticed.

## Usage

```bash
pip install -r requirements.txt

# load a few days into SQLite
python -m app.ingest --wiki ruwiki --from 2026-07-01 --to 2026-07-03 --db ts.sqlite
python -m app.ingest --wiki enwiki --from 2026-07-01 --to 2026-07-03 --db ts.sqlite

# reports
python -m app.stats --db ts.sqlite --report overview   # per-wiki summary
python -m app.stats --db ts.sqlite --report top        # participation ranking
python -m app.stats --db ts.sqlite --report edges      # who replies to whom
python -m app.stats --db ts.sqlite --report pairs      # who meets whom
python -m app.stats --db ts.sqlite --report closers    # who closes discussions
python -m app.stats --db ts.sqlite --report silent     # edited a section, never spoke in it
python -m app.stats --db ts.sqlite --report tags       # how edits were made
```

On Toolforge the database comes from the environment:
`TS_DB=toolsdb:$TOOL_TOOLSDB_USER__talk_snapshots`. Replica and Toolsdb
credentials are injected by the platform and must never live in the repository.

## Deployment

`Procfile` declares three processes: `migrate` (schema), `daily` (last three
days of both wikis), `smoke` (post-deploy check). `toolforge.yaml` puts `daily`
on a schedule.

The post-deploy check deliberately does **not** live in GitHub Actions: wiki
replicas and Toolsdb are unreachable outside Cloud VPS, so CI runs only the
offline tests and `smoke` runs as a one-off job on Toolforge.

## Adding a wiki

One entry in `app/wikis.py`: month names, user-namespace aliases, where
deletion discussions live, and — optionally — the stance markers that wiki
uses. Everything else is shared.

## Status

Working and verified on live data, both locally and on Toolforge (replicas,
Toolsdb). Not built yet: a web interface, a topic layer via Wikidata, stance
extraction for ruwiki, and bulk loading from dumps.

Licensed under Apache-2.0.
