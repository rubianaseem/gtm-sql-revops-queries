-- 07_stalled_deals.sql
-- Question: which open deals have sat in their stage too long with no
-- recent activity from anyone at the account?
--
-- Days in stage comes from the last history row, not the create date.
-- Last activity is the latest touch from any contact at the deal's company,
-- because the champion is often not the primary contact.

WITH last_change AS (
    SELECT deal_id, MAX(changed_at) AS entered_stage_at
    FROM stg_stage_history
    GROUP BY deal_id
),
last_touch AS (
    SELECT c.company_id, MAX(t.touched_at) AS last_touch_at
    FROM stg_touches t
    JOIN stg_contacts c ON c.contact_id = t.contact_id
    WHERE t.touched_at <= :as_of
    GROUP BY c.company_id
),
open_deals AS (
    SELECT
        d.deal_id, d.deal_name, d.stage, d.max_days_in_stage,
        COALESCE(o.owner_name, '(no owner)')                      AS owner,
        ROUND(d.amount_usd)                                       AS amount_usd,
        d.close_date,
        CAST(julianday(:as_of) - julianday(lc.entered_stage_at) AS INTEGER) AS days_in_stage,
        CAST(julianday(:as_of) - julianday(lt.last_touch_at)   AS INTEGER) AS days_since_touch
    FROM stg_deals d
    LEFT JOIN last_change lc ON lc.deal_id = d.deal_id
    LEFT JOIN last_touch  lt ON lt.company_id = d.company_id
    LEFT JOIN stg_owners  o  ON o.owner_id = d.owner_id
    WHERE d.is_closed = 0
)
SELECT
    deal_id, deal_name, owner, stage, amount_usd, close_date,
    days_in_stage, max_days_in_stage, days_since_touch,
    CASE
        WHEN days_in_stage IS NULL                    THEN 'no history'
        WHEN days_in_stage > 2 * max_days_in_stage
         AND COALESCE(days_since_touch, 999) > 21     THEN 'stalled, no activity'
        WHEN days_in_stage > max_days_in_stage        THEN 'over stage limit'
        ELSE 'ok'
    END AS status
FROM open_deals
WHERE days_in_stage IS NULL OR days_in_stage > max_days_in_stage
ORDER BY status DESC, amount_usd DESC;
