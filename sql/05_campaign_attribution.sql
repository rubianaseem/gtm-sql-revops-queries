-- 05_campaign_attribution.sql
-- Question: which channels source pipeline (first touch) and which close it
-- out (last touch before the deal was created)?
--
-- Touches are matched through the person (email_key), so a touch logged on
-- a duplicate contact still counts. Only touches on or before the deal's
-- create date count; anything after did not create the deal.

WITH deal_people AS (
    SELECT d.deal_id, d.amount_usd, d.is_won, d.create_date, c.email_key
    FROM stg_deals d
    JOIN stg_contacts c ON c.contact_id = d.primary_contact_id
    WHERE d.amount_usd > 0
),
eligible AS (
    SELECT dp.deal_id, dp.amount_usd, dp.is_won,
           t.touched_at,
           COALESCE(cp.channel, 'Unknown campaign') AS channel
    FROM deal_people dp
    JOIN stg_contacts c  ON c.email_key = dp.email_key
    JOIN stg_touches  t  ON t.contact_id = c.contact_id
    LEFT JOIN stg_campaigns cp ON cp.campaign_id = t.campaign_id
    WHERE date(t.touched_at) <= dp.create_date
),
ranked AS (
    SELECT e.*,
           ROW_NUMBER() OVER (PARTITION BY deal_id ORDER BY touched_at ASC)  AS first_rank,
           ROW_NUMBER() OVER (PARTITION BY deal_id ORDER BY touched_at DESC) AS last_rank
    FROM eligible e
),
credit AS (
    SELECT channel, 'first' AS model, deal_id, amount_usd, is_won FROM ranked WHERE first_rank = 1
    UNION ALL
    SELECT channel, 'last'  AS model, deal_id, amount_usd, is_won FROM ranked WHERE last_rank = 1
)
SELECT
    channel,
    SUM(model = 'first')                                              AS first_touch_deals,
    ROUND(SUM(CASE WHEN model = 'first' THEN amount_usd END))         AS first_touch_pipeline_usd,
    ROUND(SUM(CASE WHEN model = 'first' AND is_won = 1 THEN amount_usd END)) AS first_touch_won_usd,
    SUM(model = 'last')                                               AS last_touch_deals,
    ROUND(SUM(CASE WHEN model = 'last' THEN amount_usd END))          AS last_touch_pipeline_usd,
    ROUND(SUM(CASE WHEN model = 'last' AND is_won = 1 THEN amount_usd END)) AS last_touch_won_usd
FROM credit
GROUP BY channel
ORDER BY first_touch_pipeline_usd DESC;
