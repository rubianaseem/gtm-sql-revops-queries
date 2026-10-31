-- 04_pipeline_coverage.sql
-- Question: per owner and quarter, is there enough open pipeline to hit
-- what is left of quota?
--
-- coverage = open pipeline / (quota - closed won). Amounts are converted to
-- USD first; deals with no FX rate drop out of the sum and are flagged in 06.
-- Deals with no owner are kept as '(no owner)' so the total still ties out.

WITH deals AS (
    SELECT
        COALESCE(d.owner_id, '(no owner)')            AS owner_id,
        d.close_quarter,
        d.is_closed, d.is_won, d.stage_order,
        d.amount_usd
    FROM stg_deals d
    WHERE d.pipeline = 'New Business'
      AND d.amount_usd > 0
      AND d.close_quarter IN (SELECT DISTINCT quarter FROM quotas)
),
rollup AS (
    SELECT
        owner_id, close_quarter AS quarter,
        SUM(CASE WHEN is_closed = 0 THEN amount_usd ELSE 0 END)                   AS open_pipeline_usd,
        -- Simple stage weighting: stage_order / 6. Swap for your own probabilities.
        SUM(CASE WHEN is_closed = 0 THEN amount_usd * stage_order / 6.0 ELSE 0 END) AS weighted_pipeline_usd,
        SUM(CASE WHEN is_won = 1 THEN amount_usd ELSE 0 END)                       AS won_usd,
        SUM(is_closed = 0)                                                         AS open_deals
    FROM deals
    GROUP BY owner_id, close_quarter
)
SELECT
    COALESCE(o.owner_name, r.owner_id)                          AS owner,
    r.quarter,
    CAST(q.quota_usd AS REAL)                                   AS quota_usd,
    ROUND(r.won_usd)                                            AS won_usd,
    ROUND(r.open_pipeline_usd)                                  AS open_pipeline_usd,
    ROUND(r.weighted_pipeline_usd)                              AS weighted_pipeline_usd,
    r.open_deals,
    ROUND(r.open_pipeline_usd /
          NULLIF(MAX(q.quota_usd - r.won_usd, 0), 0), 2)        AS coverage_ratio,
    CASE
        WHEN q.quota_usd IS NULL                    THEN 'no quota (no owner or inactive)'
        WHEN r.won_usd >= q.quota_usd               THEN 'quota met'
        WHEN r.open_pipeline_usd / (q.quota_usd - r.won_usd) < 3 THEN 'under 3x coverage'
        ELSE 'ok'
    END                                                         AS status
FROM rollup r
LEFT JOIN stg_owners o ON o.owner_id = r.owner_id
LEFT JOIN quotas     q ON q.owner_id = r.owner_id AND q.quarter = r.quarter
ORDER BY r.quarter, owner;
