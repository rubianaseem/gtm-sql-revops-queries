-- 03_lead_to_deal_cohort.sql
-- Question: for people created each month, how many became a deal, and how fast?
--
-- The cohort is people, not contact records: stg_people keeps one row per
-- email_key, so a duplicate contact does not inflate the denominator.
-- A deal counts for a person if it names any of their contact records.

WITH person_records AS (
    SELECT p.email_key, p.created_date, c.contact_id
    FROM stg_people p
    JOIN stg_contacts c ON c.email_key = p.email_key
),
first_deal AS (
    SELECT pr.email_key, MIN(d.create_date) AS first_deal_date
    FROM person_records pr
    JOIN stg_deals d ON d.primary_contact_id = pr.contact_id
    GROUP BY pr.email_key
),
cohort AS (
    SELECT
        strftime('%Y-%m', p.created_date) AS cohort_month,
        p.email_key,
        julianday(f.first_deal_date) - julianday(p.created_date) AS days_to_deal
    FROM stg_people p
    LEFT JOIN first_deal f ON f.email_key = p.email_key
)
SELECT
    cohort_month,
    COUNT(*)                                                   AS people,
    SUM(days_to_deal IS NOT NULL)                              AS became_deal,
    ROUND(100.0 * SUM(days_to_deal IS NOT NULL) / COUNT(*), 1) AS conversion_pct,
    SUM(days_to_deal <= 30)                                    AS within_30d,
    SUM(days_to_deal <= 90)                                    AS within_90d,
    ROUND(AVG(days_to_deal), 1)                                AS avg_days_to_deal,
    -- Cohorts younger than 90 days have not had a full window yet.
    julianday(:as_of) - julianday(cohort_month || '-01') < 90  AS window_incomplete
FROM cohort
GROUP BY cohort_month
ORDER BY cohort_month;
