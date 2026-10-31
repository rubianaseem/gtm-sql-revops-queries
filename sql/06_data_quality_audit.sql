-- 06_data_quality_audit.sql
-- Question: which records will quietly break the other five queries?
--
-- One row per issue per record. Each check is a small SELECT joined with
-- UNION ALL, so adding a check is adding a block. Severity:
--   high   = changes a number leadership sees (pipeline, coverage, revenue)
--   medium = breaks attribution, routing or dedupe
--   low    = tidy-up

WITH
dup_contacts AS (
    SELECT c.contact_id, c.email, p.contact_id AS keep_id, p.records_for_person
    FROM stg_contacts c
    JOIN stg_people p ON p.email_key = c.email_key
    WHERE p.records_for_person > 1 AND c.contact_id <> p.contact_id
),
dup_companies AS (
    SELECT c.company_id, c.company_name, k.company_id AS keep_id
    FROM stg_companies c
    JOIN (SELECT name_key, MIN(company_id) AS company_id, COUNT(*) AS n
          FROM stg_companies GROUP BY name_key HAVING n > 1) k
      ON k.name_key = c.name_key AND k.company_id <> c.company_id
),
history_stats AS (
    SELECT deal_id, COUNT(*) AS changes FROM stg_stage_history GROUP BY deal_id
),
backward AS (
    SELECT deal_id, stage, prev_stage, changed_at FROM (
        SELECT deal_id, stage, stage_order, changed_at,
               LAG(stage)       OVER (PARTITION BY deal_id ORDER BY changed_at) AS prev_stage,
               LAG(stage_order) OVER (PARTITION BY deal_id ORDER BY changed_at) AS prev_order
        FROM stg_stage_history
    ) WHERE stage_order BETWEEN 1 AND 5 AND prev_order > stage_order
),
raw_history_dupes AS (
    SELECT trim(deal_id) AS deal_id, COUNT(*) - 1 AS extra_rows
    FROM raw_deal_stage_history
    GROUP BY trim(deal_id), lower(trim(deal_stage)), datetime(changed_at)
    HAVING COUNT(*) > 1
),
issues AS (
SELECT 'duplicate_contact' AS issue, 'medium' AS severity, 'contact' AS record_type,
       contact_id AS record_id,
       'Same email as ' || keep_id || ' after lower-casing and trimming: "' || email || '"' AS detail,
       'Merge into ' || keep_id || ' (keep the oldest record)' AS suggested_fix
FROM dup_contacts
UNION ALL
SELECT 'duplicate_company', 'medium', 'company', company_id,
       '"' || company_name || '" matches ' || keep_id || ' on name key',
       'Merge into ' || keep_id || ' after checking the domain'
FROM dup_companies
UNION ALL
SELECT 'company_missing_domain', 'low', 'company', company_id,
       '"' || company_name || '" has no domain, so enrichment and matching skip it',
       'Add the domain'
FROM stg_companies WHERE domain IS NULL
UNION ALL
SELECT 'contact_no_company', 'low', 'contact', contact_id,
       email || ' has no company association', 'Associate a company or mark as individual'
FROM stg_contacts WHERE company_id IS NULL
UNION ALL
SELECT 'orphan_deal', 'high', 'deal', d.deal_id,
       'company_id ' || COALESCE(d.company_id, '(blank)') || ' is not in the company export',
       'Re-associate the deal to the right company or confirm the company was deleted'
FROM stg_deals d LEFT JOIN stg_companies c ON c.company_id = d.company_id
WHERE c.company_id IS NULL
UNION ALL
SELECT 'deal_no_owner', 'high', 'deal', deal_id,
       'Open deal worth ' || CAST(amount AS INTEGER) || ' ' || currency || ' has no owner',
       'Assign an owner; it is missing from every rep forecast'
FROM stg_deals WHERE owner_id IS NULL AND COALESCE(is_closed, 0) = 0
UNION ALL
SELECT 'deal_owner_inactive', 'high', 'deal', d.deal_id,
       'Open deal owned by ' || COALESCE(o.owner_name, d.owner_id) ||
       CASE WHEN o.owner_id IS NULL THEN ' (unknown owner id)' ELSE ' (deactivated)' END,
       'Reassign to an active rep'
FROM stg_deals d LEFT JOIN stg_owners o ON o.owner_id = d.owner_id
WHERE d.owner_id IS NOT NULL AND COALESCE(o.is_active, 0) = 0 AND COALESCE(d.is_closed, 0) = 0
UNION ALL
SELECT 'unmapped_stage', 'high', 'deal', deal_id,
       'Stage "' || raw_stage || '" is not in stage_map.csv, so this deal is missing from funnel and coverage',
       'Add the stage to stage_map.csv or fix the deal'
FROM stg_deals WHERE stage IS NULL
UNION ALL
SELECT 'missing_fx_rate', 'high', 'deal', deal_id,
       'Currency ' || currency || ' has no rate in fx_rates, amount_usd is empty',
       'Add the rate to sample_fx_rates.csv'
FROM stg_deals WHERE amount_usd IS NULL AND amount IS NOT NULL
UNION ALL
SELECT 'currency_assumed', 'low', 'deal', deal_id,
       'Currency blank, assumed USD',
       'Set the deal currency'
FROM stg_deals WHERE currency_raw IS NULL
UNION ALL
SELECT 'negative_or_zero_amount', 'high', 'deal', deal_id,
       'Amount is ' || COALESCE(CAST(amount AS INTEGER), 'blank'),
       'Fix the amount; refunds and credits belong in billing, not the deal'
FROM stg_deals WHERE amount IS NULL OR amount <= 0
UNION ALL
SELECT 'close_date_in_past', 'high', 'deal', deal_id,
       'Open deal with close date ' || close_date || ', ' ||
       CAST(julianday(:as_of) - julianday(close_date) AS INTEGER) || ' days ago',
       'Ask the owner to update the close date or close the deal'
FROM stg_deals WHERE is_closed = 0 AND close_date < date(:as_of)
UNION ALL
SELECT 'no_stage_history', 'medium', 'deal', d.deal_id,
       'Deal is in ' || COALESCE(d.stage, d.raw_stage) || ' with no stage history rows',
       'Export property history again; it cannot appear in funnel or velocity'
FROM stg_deals d LEFT JOIN history_stats h ON h.deal_id = d.deal_id
WHERE h.deal_id IS NULL
UNION ALL
SELECT 'backward_stage_move', 'medium', 'deal', deal_id,
       'Moved back from ' || prev_stage || ' to ' || stage || ' on ' || date(changed_at),
       'Check with the owner; require a reason for stage regressions'
FROM backward
UNION ALL
SELECT 'duplicate_history_row', 'low', 'deal', deal_id,
       extra_rows || ' exact duplicate stage history row(s)',
       'None needed; stg_stage_history drops them'
FROM raw_history_dupes
UNION ALL
SELECT 'unknown_campaign', 'medium', 'touch', t.touch_id,
       'Touch points at campaign ' || t.campaign_id || ', which is not in the campaign export',
       'Find the campaign or map it; attribution counts it as Unknown campaign'
FROM stg_touches t LEFT JOIN stg_campaigns c ON c.campaign_id = t.campaign_id
WHERE c.campaign_id IS NULL
)
SELECT * FROM issues
ORDER BY CASE severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, issue, record_id;
