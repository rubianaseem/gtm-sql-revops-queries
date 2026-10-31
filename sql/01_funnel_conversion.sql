-- 01_funnel_conversion.sql
-- Question: of the deals that reached each stage, what share reached the next?
--
-- Built from stage history, not the current stage. A deal now in Demo that
-- once reached Proposal counts as reaching Proposal. Counting current stage
-- instead undercounts every stage a deal went backward from.

WITH furthest AS (
    SELECT deal_id,
           MAX(stage_order) AS furthest_order      -- Closed Lost is 0, so it never wins MAX
    FROM stg_stage_history
    WHERE stage_order IS NOT NULL
    GROUP BY deal_id
),
stages AS (
    SELECT DISTINCT stage, stage_order FROM stage_map WHERE stage_order >= 1
),
reached AS (
    SELECT s.stage_order, s.stage,
           COUNT(f.deal_id) AS deals_reached
    FROM stages s
    LEFT JOIN furthest f ON f.furthest_order >= s.stage_order
    GROUP BY s.stage_order, s.stage
),
current_here AS (
    SELECT stage, COUNT(*) AS deals_currently_here
    FROM stg_deals GROUP BY stage
)
SELECT
    r.stage_order,
    r.stage,
    r.deals_reached,
    COALESCE(c.deals_currently_here, 0) AS deals_currently_here,
    LEAD(r.deals_reached) OVER (ORDER BY r.stage_order) AS deals_reached_next,
    ROUND(100.0 * LEAD(r.deals_reached) OVER (ORDER BY r.stage_order)
          / NULLIF(r.deals_reached, 0), 1)             AS conversion_to_next_pct
FROM reached r
LEFT JOIN current_here c ON c.stage = r.stage
ORDER BY r.stage_order;
