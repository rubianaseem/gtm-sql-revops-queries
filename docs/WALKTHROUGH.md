# Walk through it line by line

Open `sql/` and `gtm_sql/` next to this page. The order below is the order the runner works in. Each section shows the code, then the judgment behind it, because the syntax is the easy part. Knowing which number is wrong is the job.

## 1. Load raw, clean in SQL (`gtm_sql/loader.py`)

```python
types = ["TEXT"] * len(header)
if typed:
    types = [_infer_type([r[i] for r in rows]) for i in range(len(header))]
```

- Every CRM export column loads as TEXT, exactly as exported. Nothing is cleaned in Python.
- Only the lookup tables you own (`stage_map`, `fx_rates`, `quotas`) get real types. If `stage_order` were TEXT, `'10' < '2'` would be true and the funnel would sort wrong.
- Why keep raw as text: when a number looks wrong, you can compare `raw_deals.amount` with `stg_deals.amount` and see exactly what cleaning did. If you clean on the way in, that evidence is gone.

## 2. Staging views (`sql/00_staging.sql`)

```sql
lower(trim(email)) AS email_key,   -- the dedupe key
```

- `trim` removes the stray space, `lower` makes `Priya.Shah@NORTHWIND.COM` equal `priya.shah@northwind.com`. The original `email` column stays for display.
- Every later query joins on `email_key`, never `email`. Write the rule once; if it changes, it changes everywhere.

```sql
SELECT * FROM (
    SELECT c.*,
           ROW_NUMBER() OVER (PARTITION BY email_key ORDER BY created_date, contact_id) AS rn,
           COUNT(*)     OVER (PARTITION BY email_key)                                  AS records_for_person
    FROM stg_contacts c
) WHERE rn = 1;
```

- This is the standard dedupe pattern. `PARTITION BY email_key` splits contacts into one group per person. `ORDER BY created_date` puts the oldest record first. `ROW_NUMBER()` numbers each group 1, 2, 3. Keep `rn = 1`.
- `contact_id` in the ORDER BY is a tie-breaker. Without it, two records created the same day could swap between runs and your counts would drift.
- `COUNT(*) OVER (...)` is the same window without numbering. It puts the group size on every row, which the audit uses to find duplicates. A `GROUP BY` would collapse the rows; a window keeps them.
- You cannot filter on a window function in the same SELECT (`WHERE rn = 1` fails there), hence the subquery.

```sql
LEFT JOIN stage_map sm ON sm.raw_value = lower(trim(d.raw_stage))
LEFT JOIN fx_rates  fx ON fx.currency  = COALESCE(d.currency_raw, 'USD');
```

- HubSpot exports internal values (`closedwon`, `contractsent`); a hand import added `closed won`. A mapping table beats a long `CASE`: ops can add a row without touching SQL, and the audit lists anything unmapped.
- `LEFT JOIN`, not `JOIN`. An inner join would silently drop the deal in `Verbal Commit` and the CHF deal. With a left join they stay, with NULLs the audit can find. Rule of thumb: inner joins hide problems, left joins expose them.
- `COALESCE(currency_raw, 'USD')` is an assumption. It is written down here and the audit flags every row it touched (`currency_assumed`), so nobody mistakes it for a fact.

## 3. Funnel conversion (`01_funnel_conversion.sql`)

```sql
WITH furthest AS (
    SELECT deal_id, MAX(stage_order) AS furthest_order
    FROM stg_stage_history
    WHERE stage_order IS NOT NULL
    GROUP BY deal_id
),
```

- A CTE (`WITH name AS (...)`) is a named step. Read the query top to bottom like a recipe: furthest stage per deal, then the list of stages, then counts.
- The furthest stage comes from history, not the current stage. D9003 went Discovery, Qualified, Proposal, then back to Demo. A current-stage report counts it only in Demo. The funnel needs it counted in Proposal too, or Proposal's conversion looks better than it is.
- Closed Lost has `stage_order` 0, so `MAX` never picks it. A lost deal counts for the furthest open stage it reached, which is what you want.

```sql
LEFT JOIN furthest f ON f.furthest_order >= s.stage_order
```

- A join on `>=` instead of `=`. Each deal matches every stage up to its furthest one, so a deal that reached Proposal is counted in Discovery, Qualified, Demo and Proposal.

```sql
LEAD(r.deals_reached) OVER (ORDER BY r.stage_order) AS deals_reached_next
```

- `LEAD` reads the next row's value. Here it gives the next stage's count on the current row, so conversion is one division. No self-join needed.

## 4. Time in stage (`02_stage_velocity.sql`)

```sql
LEAD(h.changed_at)  OVER w AS next_changed_at,
LAG(h.stage_order)  OVER w AS prev_stage_order,
...
WINDOW w AS (PARTITION BY h.deal_id ORDER BY h.changed_at)
```

- `LEAD` gives the time the deal left this stage (the next change). `LAG` gives the previous stage, which tells you whether this entry was a step backward.
- `PARTITION BY deal_id` matters: without it, `LEAD` would read the next deal's row.
- The named `WINDOW w` avoids repeating the same `OVER (...)` twice.
- The last stage of an open deal has no next change, so it runs to `:as_of`. Closed deals stop at their close row. Using today's date for closed deals would make every won deal look slow.

## 5. Lead-to-deal cohort (`03_lead_to_deal_cohort.sql`)

- The cohort is people (`stg_people`), not contact records. Count records and every duplicate is an extra person who never converted, which drags the rate down.
- A deal counts for a person if it names any of their records (`person_records`). The deal is often attached to the duplicate, not the original.
- `SUM(days_to_deal IS NOT NULL)` counts rows where the condition is true. In SQLite a comparison returns 1 or 0, so `SUM` of a condition is a count. In BigQuery use `COUNTIF`.
- `window_incomplete` marks cohorts younger than 90 days. Last month's cohort always looks worst because it has not had time to convert. Do not compare it with the others.

## 6. Pipeline coverage (`04_pipeline_coverage.sql`)

```sql
COALESCE(d.owner_id, '(no owner)') AS owner_id,
```

- Unowned deals become a visible row instead of disappearing. Coverage reports that only show reps with quota quietly lose this money. Here it is $85,800 in Q4.

```sql
ROUND(r.open_pipeline_usd / NULLIF(MAX(q.quota_usd - r.won_usd, 0), 0), 2) AS coverage_ratio
```

- Coverage is open pipeline over what is left to close, not over the full quota. A rep who has already won most of the number needs far less pipeline.
- `NULLIF(x, 0)` turns 0 into NULL so a rep who has hit quota gets NULL instead of a divide-by-zero. `MAX(a, 0)` with two arguments is SQLite's `GREATEST`.
- The join to quotas is a `LEFT JOIN` on owner and quarter. A deactivated rep has no quota, so their pipeline shows with a status saying so.

## 7. Attribution (`05_campaign_attribution.sql`)

```sql
WHERE date(t.touched_at) <= dp.create_date
```

- Only touches on or before the deal was created count. A webinar attended after the deal opened did not create it. Forget this filter and late-stage nurture campaigns take credit for pipeline.

```sql
ROW_NUMBER() OVER (PARTITION BY deal_id ORDER BY touched_at ASC)  AS first_rank,
ROW_NUMBER() OVER (PARTITION BY deal_id ORDER BY touched_at DESC) AS last_rank
```

- The same pattern as dedupe: rank within each deal, keep rank 1. Ascending gives the first touch, descending the last.
- The join-fanout trap: a deal with five touches becomes five rows after the join. Summing `amount_usd` straight after the join would count the deal five times. Ranking first and keeping one row per deal per model is what makes the sums safe. Always ask "what is one row here?" before you SUM.
- Channel is normalised in staging (`paid social` and `Paid Social` are one channel), so the duplicate C08 campaign lands with C02 instead of splitting the row.

## 8. Data-quality audit (`06_data_quality_audit.sql`)

- Each check is one small SELECT with the same six columns, joined with `UNION ALL`. `UNION ALL` keeps every row; plain `UNION` would also deduplicate, which is slower and can hide two identical issues.
- The orphan check is the classic anti-join: `LEFT JOIN companies ... WHERE c.company_id IS NULL` finds deals whose company is not in the export.
- Severity is about who notices. High changes a number leadership sees. Fix those before you present anything.
- The final `ORDER BY` sits outside the `issues` CTE because SQLite will not sort a compound SELECT by an expression.

## 9. Stalled deals (`07_stalled_deals.sql`)

- Days in stage comes from the last history row, not the create date. A deal created in April that reached Negotiation last week is not stalled.
- Last activity is the latest touch from anyone at the company, not only the primary contact.
- Two levels: over the stage limit, and stalled with no activity (more than twice the limit and nothing in 21 days). The second list is the one to send to managers.

## 10. The read-only guard (`gtm_sql/guard.py`)

```python
conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
conn.execute("PRAGMA query_only = ON")
conn.set_authorizer(_authorizer)
```

- SQL from Claude or from a paste is untrusted. The text check refuses anything that is not one SELECT or WITH. That alone is not enough, because text checks can be fooled.
- `mode=ro` opens the file read-only at the operating-system level. `query_only` tells SQLite to refuse writes. The authorizer is called by SQLite for every action in the query and denies anything that is not a read. Any one layer would stop a `DELETE`.
- The same idea in a warehouse is a read-only role for the agent. Never give a model a connection that can write.

## 11. The brief (`gtm_sql/brief.py`)

- `findings()` reduces seven result sets to a small dictionary of facts. Both the rules and Claude write from that dictionary only, so Claude cannot quote a number the SQL did not produce.
- If the Claude call fails for any reason, the run still finishes with the rules version and says so in the brief.
