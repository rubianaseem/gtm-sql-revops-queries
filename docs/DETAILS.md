# Details

## Cost note

With no API key the runner costs nothing. SQLite is a file on your laptop. With a key, the brief is one Claude call per run carrying only the aggregated findings (a couple of thousand tokens), and each `--ask` is one call carrying the schema and your question. Check current pricing on Anthropic's site. If you move the SQL to a warehouse, the cost there is compute per query: these queries scan every deal and touch, which is cheap at CRM scale but worth partitioning by date once touches run into the millions.

## Stack-swap table

| Piece | In this repo | Swap for |
|---|---|---|
| Database | SQLite file in `out/` | DuckDB (reads CSV and Parquet directly), Postgres, BigQuery, Snowflake |
| Load | CSV export into `raw_*` tables | Fivetran, Airbyte, HubSpot Data Share to Snowflake, Salesforce Data Cloud |
| Cleaning | `sql/00_staging.sql` views | dbt staging models with tests |
| Deals | HubSpot deal export | Salesforce Opportunity report or `Opportunity` table |
| Stage history | HubSpot Deal Stage property history | Salesforce `OpportunityHistory`, a daily snapshot table |
| Touches | Contact touch export | Salesforce `CampaignMember`, GA4 events, a reverse-ETL table |
| Brief | Rules, or Claude | Any model that follows a JSON-only prompt |
| Delivery | CSV and Markdown in `out/` | A BI tool reading the views, a Slack post, a Notion page |

SQLite to warehouse syntax swaps you will need:

| SQLite | BigQuery | Snowflake / Postgres |
|---|---|---|
| `julianday(a) - julianday(b)` | `DATE_DIFF(a, b, DAY)` | `DATEDIFF('day', b, a)` / `a::date - b::date` |
| `strftime('%Y-%m', d)` | `FORMAT_DATE('%Y-%m', d)` | `TO_CHAR(d, 'YYYY-MM')` |
| `SUM(x = 'a')` | `COUNTIF(x = 'a')` | `SUM(CASE WHEN x = 'a' THEN 1 ELSE 0 END)` |
| `MAX(a, b)` (two arguments) | `GREATEST(a, b)` | `GREATEST(a, b)` |
| `WINDOW w AS (...)` | supported | supported |
| `:as_of` parameter | `@as_of` | `:as_of` / `%(as_of)s` from Python |

## Customise for your stack

- `stage_map.csv`: every raw stage value you see (labels, internal names, every pipeline), its order, closed and won flags, and how many days a deal may sit there before it counts as stalled.
- `sample_fx_rates.csv`: one rate per currency. In production, use the rate at close date, not today's.
- `sample_quotas.csv`: quota per owner per quarter. Coverage only reports quarters that appear here.
- The 3x coverage line and the stage weighting (`stage_order / 6`) are in `04_pipeline_coverage.sql`. Replace the weighting with your stage probabilities.
- The 21-day no-activity rule is in `07_stalled_deals.sql`.
- The blank-currency-means-USD assumption is in `stg_deals`. Change it to your portal's default.
- To add a data-quality check, add one `SELECT ... UNION ALL` block to `06_data_quality_audit.sql` with the same six columns. It flows into the review queue and the brief automatically.
- To add a query, add a numbered file to `sql/` and its name to `QUERY_FILES` in `gtm_sql/queries.py`.

## How this runs today (and what production would add)

Today it is a script you run by hand on CSV exports. It rebuilds a local SQLite file every run, runs the SQL, and writes files. It never connects to or writes to your CRM. You read the brief and work the review queue yourself.

Honest limits:

- Attribution uses the deal's primary contact (and that person's duplicates). Buying committees touch more than one person; a production model would credit every contact role.
- Stage history from an export is only as good as the export. HubSpot keeps a limited number of revisions per property, so very old, busy deals may be missing early stages.
- FX is a single rate per currency.
- Velocity is an average; one 260-day deal moves it. Look at `max_days` and the stalled list before you quote it.

Production would add:

- Data landing in a warehouse on a schedule, with the staging views as dbt models and tests (unique, not null, accepted values on stage).
- A daily deal snapshot table, so coverage and stage history do not depend on export limits.
- Metric definitions agreed with sales and marketing and written down next to the SQL, so the brief and the board deck use the same numbers.
- The brief posted weekly to the RevOps channel, and the review queue turned into owner tasks.
- `--ask` restricted to a read-only warehouse role, with every generated query logged.
