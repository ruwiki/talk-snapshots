# talk-snapshots

**Live:** https://talk-snapshots.toolforge.org/ (HTML) · https://talk-snapshots.toolforge.org/api/report.json (JSON)

Who argues with whom, about which pages, in deletion discussions — and what
happens to those pages afterwards — across Wikipedias with one codebase.

Seven wikis are wired in: `ruwiki`, `enwiki`, `dewiki`, `ukwiki`, `zhwiki`,
`itwiki`, `jawiki`. Adding one more is a single declarative file, see below.

## Two things that are universal, and everything that is not

**Universal.** The participation layer (who spoke, when, replying to whom)
comes from the DiscussionTools API and works on any wiki. The fate of a page
(exists / redirect / deleted, when, by whom, on which grounds / moved /
recreated) comes from the `page` and `logging` tables of the database
replicas — the same schema on every wiki, one query for all of them.

**Per wiki.** Where the discussions live, how nominations are separated on a
page, which pages a nomination is about, where the closing decision is written
and how a comment expresses a stance. None of this is hard-coded: each axis is
a small strategy in `app/core/`, and a wiki is a composition of strategies in
`app/wikis/<dbname>.py`.

| Axis | Strategies | Used by |
|---|---|---|
| listing | `DayPage`, `DailyLog` | ru/de/uk/zh · en/it/ja |
| pages (1:N) | `Subsections`, `HeadingLinks`, `TitleFromHeading`, `TitleAfterPrefix` | group nominations, headings, per-nomination pages |
| outcome | `OutcomeSection`, `HeadingSuffix`, `ClosingTemplate`, `CommentPattern`, `NoOutcome` | ru/uk · de · en/zh · ja · it |
| stance | `VoteWords`, `SectionStance`, `NoStance` | en/de/uk/zh/ja · it · — |
| reason | `ReasonClass` regexes over the deletion-log comment | all |

Discussion outcome and page state are stored separately
(`discussion_outcome` vs `page_state`): a page can be kept by the discussion
and speedily deleted a month later, or deleted and recreated — those are
different facts.

A nomination may concern several pages (`nomination_pages`): Russian
Wikipedia groups articles under one heading with sub-headings per article,
and a fifth of nominations there are such groups or non-article pages.

## Three sources, not one

| Source | What it provides | Module |
|---|---|---|
| **DiscussionTools API** | thread structure as MediaWiki itself sees it: author, timestamp, nesting, sub-headings, `transcludedfrom` | `core/threads.py` |
| **Database replicas** (Toolforge; API elsewhere) | revision history of the discussion page, page state and deletion log, categories and Wikidata item snapshot | `core/revisions.py`, `core/state.py`, `core/topics.py` |
| **Wikitext parsing** | fallback for dump processing, where an API call per page is not affordable; also the closing templates | `core/parse.py` |

Topics are snapshotted **at nomination time**: after deletion the categories
are gone from every source (replicas, Wikidata sitelinks, even the enwiki
DELSORT categories vanish when the AfD is closed).

## Usage

```bash
pip install -r requirements.txt
export TS_DB=ts.sqlite            # or toolsdb:<db> on Toolforge (set by envvars)
export TS_WIKIS=ruwiki,enwiki,dewiki

python -m app.cli ingest --from 2026-07-01 --to 2026-07-03   # all TS_WIKIS
python -m app.cli --wiki dewiki ingest --recent 3 --refresh-changed
python -m app.cli state                                      # page fate from logs, whole volume
python -m app.cli quality                                    # metrics vs thresholds, non-zero exit on breach
python -m app.cli daily                                      # what the cron runs: the three above
python -m app.stats --report top                             # participation reports
```

`--refresh-changed` re-reads a day page only if its latest revision on the
wiki differs from the stored one: fixing a discussion on-wiki is the trigger,
there is no management UI. Page state is recomputed over the whole volume on
every run — it has no window.

## Adding a wiki

1. Create `app/wikis/<dbname>.py` with a `WIKI = WikiSpec(...)`: locale
   (months, user-namespace aliases, namespace prefixes, bots, signature
   format), and one strategy per axis. `dewiki.py` is the shortest example.
2. Save one day of DiscussionTools output as
   `tests/fixtures/<dbname>/dt_<day>.json` and pin counts in
   `expected_<day>.json`. The registry test refuses wikis without a fixture.
3. Add the dbname to `TS_WIKIS`. Nothing in `app/core/` changes — a test
   asserts the core never mentions a wiki name.

## Deployment

`Procfile` declares `web` (gunicorn serving the dashboard straight from Toolsdb with an
hourly in-memory cache — no files shared between the cron and the web pod), `migrate`,
`daily` and `smoke`; `toolforge.yaml` schedules `daily`. Web: `toolforge webservice
buildservice start --mount none`. The post-deploy check runs as a one-off job on Toolforge, not in
GitHub Actions: replicas and Toolsdb are unreachable outside Cloud VPS, so CI
runs only the offline tests (`python -m pytest`) and `ruff`.

Licensed under Apache-2.0.
