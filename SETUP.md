# Setup

## 1. Install

You need Python 3.10 or newer (`python3 --version`). SQLite comes with Python, so there is no database to install.

```bash
git clone https://github.com/rubianaseem/gtm-sql-revops-queries.git
cd gtm-sql-revops-queries
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Run on the sample data

```bash
python run_queries.py
pytest -q
```

No keys needed. The sample data is frozen at 31 Oct 2026, so the run uses that date unless you pass `--as-of`. Results land in `out/`:

| File | What it is |
|---|---|
| `gtm.db` | The SQLite database. Open it in DB Browser for SQLite, DBeaver, or `sqlite3 out/gtm.db` |
| `q01_funnel_conversion.csv` | Deals that reached each stage and conversion to the next |
| `q02_stage_velocity.csv` | Average and longest days in each stage, backward entries |
| `q03_lead_to_deal_cohort.csv` | People created each month, how many became a deal and how fast |
| `q04_pipeline_coverage.csv` | Open, weighted and won pipeline against quota, by owner and quarter |
| `q05_campaign_attribution.csv` | First and last touch pipeline and won revenue by channel |
| `q06_data_quality_audit.csv` | One row per issue per record, with severity and a suggested fix |
| `q07_stalled_deals.csv` | Open deals over their stage limit, with days since last activity |
| `review_queue.csv` | Audit issues and stalled deals in one list, by priority, with owner |
| `revops_brief.md` | The weekly brief |

To rebuild the sample CSVs (fixed seed, same output every time): `python scripts/make_sample_data.py`.

## 3. Run your own SQL

```bash
python run_queries.py --sql "SELECT owner_id, ROUND(SUM(amount_usd)) FROM stg_deals WHERE is_closed = 0 GROUP BY owner_id"
```

Query the `stg_*` views, not the `raw_*` tables; the views hold the cleaning. Use `:as_of` for today's date. The guard refuses anything that is not a single SELECT or WITH, opens the database read-only, and caps results at 200 rows. The result is saved to `out/ad_hoc_result.csv`.

## 4. Optional: Claude

```bash
cp .env.example .env      # paste your key into .env
export $(grep -v '^#' .env | xargs)
python run_queries.py                                  # Claude writes the brief
python run_queries.py --ask "Which owner has the most open pipeline in Negotiation?"
```

For the brief, Claude only sees the aggregated findings (counts, ratios, the top stalled deals), never the full export. For `--ask`, it sees the schema (view and column names) and your question, drafts one query, and the guard runs it. Read the SQL it prints before you trust the answer. If a call fails, the brief falls back to the rules and says so. `--no-claude` forces rules even with a key set.

## 5. Real data sources

The runner expects the same file names as `data/`. Put your exports in a folder, rename them, keep the column names (or edit `sql/00_staging.sql`), and run:

```bash
python run_queries.py --data my_export/ --as-of today
```

Copy `data/stage_map.csv`, `data/sample_fx_rates.csv` and `data/sample_quotas.csv` into that folder too and edit them. They are yours to own.

**HubSpot.**
- Contacts, companies, deals: CRM > the object > Export, all properties you need, CSV. Deal Stage and Owner may export as internal values (numbers or `closedwon`). That is what `stage_map.csv` is for; add every internal value you see.
- Deal stage history: three routes, best first. (1) The CRM v3 deals API with `propertiesWithHistory=dealstage`, which returns every change with a timestamp. (2) The property's Export property history option in Settings > Properties, where your portal offers it. (3) The "Date entered (stage)" deal properties, one column per stage, unpivoted to one row per stage. Map the result to `history_id, deal_id, deal_stage, changed_at`.
- Touches: export marketing events, form submissions or campaign membership with a contact id and timestamp. If you only have Original Source on the contact, make one touch per contact from it.
- Owners: Settings > Users and Teams > Export, then add `status` (active or deactivated).

**Salesforce.**
- Opportunities report with Id, AccountId, OwnerId, StageName, Amount, CurrencyIsoCode, CreatedDate, CloseDate, and the primary Contact Role.
- Stage history: the Opportunity History report (OpportunityHistory object) gives StageName and CreatedDate per change.
- Touches: Campaign Members with CampaignId, ContactId (or LeadId) and CreatedDate.
- Rename the columns to match the sample headers, or change the staging views.

**A warehouse.** If HubSpot or Salesforce already lands in BigQuery, Snowflake or Postgres (Fivetran, Airbyte, HubSpot Data Share), skip the CSVs. Recreate the `stg_*` views on top of your synced tables and run the numbered SQL files there. The SQL is standard apart from a few SQLite date functions; [docs/DETAILS.md](docs/DETAILS.md) lists the swaps.

## 6. Extend it with an AI coding tool

Open the folder in Cursor, Claude Code, Codex CLI or Grok and ask for one change at a time, for example:

- "Add 08_win_rate_by_segment.sql: win rate and average deal size by company industry and employee band. Add it to QUERY_FILES and a test."
- "Change pipeline coverage to use stage probabilities from a new column in stage_map.csv instead of stage_order / 6."
- "Add a time-decay attribution model to 05 next to first and last touch."
- "Port 00_staging.sql to BigQuery syntax in a new folder sql_bigquery/."

Ask it to run `pytest -q` and `python run_queries.py` after each change and to show you the diff in the SQL.

## 7. CI

`ci/tests.yml` runs the tests on every push. To switch it on, move it to `.github/workflows/tests.yml` and push.

## Troubleshooting

| Problem | Fix |
|---|---|
| `FileNotFoundError: .../sample_deals.csv` | `--data` folder is missing a file or the name differs. Use the sample file names |
| A deal is missing from funnel and coverage | Its stage is not in `stage_map.csv`. Check `unmapped_stage` in the audit |
| Pipeline total looks low | Deals with no FX rate or a zero amount drop out. Check `missing_fx_rate` and `negative_or_zero_amount` |
| Every deal is "over stage limit" | Your `--as-of` is far after the export date. Use the date you exported |
| `no such column` | Your export headers differ from the sample. Rename them or edit `sql/00_staging.sql` |
| `Refused: keyword not allowed` | The guard only runs reads. Write changes in your CRM, not here |
| `ModuleNotFoundError: anthropic` | `pip install -r requirements.txt`, or unset `ANTHROPIC_API_KEY` |
