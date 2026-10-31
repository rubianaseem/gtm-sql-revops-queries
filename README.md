# SQL on GTM Data: Seven RevOps Queries

A messy CRM export loaded into SQLite, seven SQL queries that answer the questions RevOps gets every week, and a Python runner that flags the bad data and writes a review queue and a plain-English brief.

Built by Rubia Naseem, GTM Engineer (12+ yrs CRM/RevOps, HubSpot & Salesforce).

## The pain point

CRM report builders handle one object at a time. Leadership's questions cross objects and time: pipeline against quota by rep, how deals move between stages, which campaign sourced the pipeline. So the numbers end up in a spreadsheet, and RevOps roles now test for SQL.

> "I still find I need a spreadsheet for reporting. I also absolutely despise their lack of cross-object reporting."
> [r/hubspot: "What are your top Hubspot Reporting limitations?"](https://www.reddit.com/r/hubspot/comments/17zmu1v/what_are_your_top_hubspot_reporting_limitations/)

> "However in a final 4th round interview, I was actually tested on practical use cases for SQL, and I could tell the two panelists went cold on me after that."
> [r/revops: "For RevOps professionals, is learning how to write SQL use-full?"](https://www.reddit.com/r/revops/comments/1cdhvfr/for_revops_professionals_is_learning_how_to_write/)

## What it does

- Loads seven CRM-shaped CSVs (owners, companies, contacts, deals, stage history, campaigns, touches) into SQLite as exported, then cleans them once in `sql/00_staging.sql`: dedupe keys, stage mapping, USD conversion.
- Runs seven queries: funnel conversion, time in stage, lead-to-deal time by cohort, pipeline coverage by owner and quarter, first and last touch attribution, a data-quality audit and stalled deals.
- Ships realistic mess on purpose: duplicate contacts that differ only by case, unowned and orphan deals, backward stage moves, a currency with no FX rate, an unmapped custom stage, touches on a deleted campaign.
- Writes every result to CSV, plus `review_queue.csv` (who to ask about what) and `revops_brief.md`.
- Runs your own SQL with `--sql` through a read-only guard. With an Anthropic key, `--ask` has Claude draft the SQL and the same guard runs it.

## Where each step runs

1. **GitHub** is where the code and sample data live. You copy it to your laptop with `git clone`.
2. **Terminal** (Mac Terminal or the terminal inside Cursor) is where you run `python run_queries.py`. It builds `out/gtm.db`, runs the SQL files in order and writes everything to `out/`.
3. **Claude is optional.** With no key, built-in rules write the brief and everything still runs in the terminal. With a key in `.env`, Claude writes the brief from the aggregated findings and can draft SQL for `--ask`.
4. **Your CRM** is where you act on it. Export your own data ([SETUP.md](SETUP.md) shows how), rerun with `--data`, then work through `review_queue.csv`: merge the duplicates, assign the unowned deals, chase the stalled ones. The runner never writes to your CRM itself.

## Quick start

```bash
git clone https://github.com/rubianaseem/gtm-sql-revops-queries.git
cd gtm-sql-revops-queries
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run_queries.py
pytest -q
```

Your own query: `python run_queries.py --sql "SELECT stage, COUNT(*) FROM stg_deals GROUP BY stage"`

## Example output

```
Loaded 246 contacts, 38 companies, 105 deals, 350 stage changes, 474 touches into out/gtm.db
As of 2026-10-31. Mode: rules only (no API key)

Funnel (from stage history):
  stage        reached  now_here  to_next_%
  Discovery    101      16        68.3
  Qualified    69       11        63.8
  Demo         44       5         75
  Proposal     33       4         63.6
  Negotiation  21       6         52.4
  Closed Won   11       12

Coverage 2026-Q4:
  owner        quota_usd  won_usd  open_usd  coverage  status
  (no owner)              0        56,100              no quota (no owner or inactive)
  Chris Wong              0        29,700              no quota (no owner or inactive)
  Elena Rossi  90,000     0        104,760   1.16      under 3x coverage
  Jordan Lee   120,000    0        115,150   0.96      under 3x coverage
  Maya Patel   150,000    31,750   336,460   2.85      under 3x coverage
  Sam Okafor   110,000    48,600   167,240   2.72      under 3x coverage

Data quality: 67 issues (18 high). Top issues:
  currency_assumed          21
  backward_stage_move       13
  close_date_in_past        6
  deal_no_owner             4
  deal_owner_inactive       4
  duplicate_contact         4

Stalled with no activity: 10 deals. Review queue: 92 rows. Brief written by: rules.
Outputs written to out/
```

Two things to notice. `now_here` is what a current-stage report shows; `reached` counts the furthest stage each deal ever hit, so a deal that slid back from Proposal to Demo still counts for Proposal. And Closed Won shows 11 reached but 12 there now: one deal was marked won with no stage history at all, which the audit flags. Every rep is under 3x coverage, and $85,800 of Q4 pipeline belongs to nobody who forecasts it.

## More

- [SETUP.md](SETUP.md): install, sample run, API key, exporting from HubSpot or Salesforce, pointing it at a warehouse, extending with Cursor, Claude Code, Codex CLI or Grok, and troubleshooting.
- [docs/DETAILS.md](docs/DETAILS.md): cost note, stack-swap table, customising it for your stack, and how this runs today versus what production would add.
- [docs/WALKTHROUGH.md](docs/WALKTHROUGH.md): walk through the SQL and Python line by line, with the judgment calls behind CTEs, window functions, join pitfalls and dedupe.
