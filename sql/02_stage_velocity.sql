-- 02_stage_velocity.sql
-- Question: how long do deals sit in each stage, and how often do they go backward?
--
-- LEAD() pairs each stage change with the next one for the same deal, so
-- time in stage = next change - this change. The last stage of an open
-- deal has no next change; it runs until :as_of.

WITH ordered AS (
    SELECT
        h.deal_id, h.stage, h.stage_order, h.changed_at,
        LEAD(h.changed_at)  OVER w AS next_changed_at,
        LAG(h.stage_order)  OVER w AS prev_stage_order,
        d.is_closed
    FROM stg_stage_history h
    JOIN stg_deals d ON d.deal_id = h.deal_id
    WINDOW w AS (PARTITION BY h.deal_id ORDER BY h.changed_at)
),
spans AS (
    SELECT
        deal_id, stage, stage_order,
        julianday(COALESCE(next_changed_at,
                  CASE WHEN is_closed = 1 THEN changed_at ELSE :as_of END))
          - julianday(changed_at)                   AS days_in_stage,
        next_changed_at IS NULL AND is_closed = 0   AS is_current,
        prev_stage_order IS NOT NULL
          AND stage_order BETWEEN 1 AND 5
          AND stage_order < prev_stage_order        AS is_backward_entry
    FROM ordered
    WHERE stage_order BETWEEN 1 AND 5               -- open stages only
)
SELECT
    stage_order,
    stage,
    COUNT(*)                                        AS stage_visits,
    COUNT(DISTINCT deal_id)                         AS deals,
    ROUND(AVG(days_in_stage), 1)                    AS avg_days,
    ROUND(MAX(days_in_stage), 1)                    AS max_days,
    SUM(is_current)                                 AS open_deals_here_now,
    SUM(is_backward_entry)                          AS backward_entries
FROM spans
GROUP BY stage_order, stage
ORDER BY stage_order;
