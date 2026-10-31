-- 00_staging.sql
-- Clean views on top of the raw CSV tables. Every later query reads these,
-- never the raw_* tables, so a cleaning rule is written once.
-- Raw tables are loaded as TEXT exactly as exported.

DROP VIEW IF EXISTS stg_owners;
CREATE VIEW stg_owners AS
SELECT
    trim(owner_id)               AS owner_id,
    trim(owner_name)             AS owner_name,
    lower(trim(email))           AS email,
    trim(role)                   AS role,
    trim(region)                 AS region,
    lower(trim(status)) = 'active' AS is_active
FROM raw_owners;

DROP VIEW IF EXISTS stg_companies;
CREATE VIEW stg_companies AS
SELECT
    trim(company_id)                         AS company_id,
    trim(company_name)                       AS company_name,
    -- A matching key: lower case, legal suffixes removed. Used only to find
    -- duplicates, never shown as the company name.
    trim(replace(replace(replace(lower(trim(company_name)) || ' ',
         ' ltd ', ' '), ' inc ', ' '), ' corp ', ' ')) AS name_key,
    NULLIF(lower(trim(domain)), '')          AS domain,
    trim(industry)                           AS industry,
    upper(trim(country))                     AS country,
    CAST(NULLIF(trim(employees), '') AS INTEGER) AS employees
FROM raw_companies;

DROP VIEW IF EXISTS stg_contacts;
CREATE VIEW stg_contacts AS
SELECT
    trim(contact_id)                   AS contact_id,
    trim(email)                        AS email,
    lower(trim(email))                 AS email_key,   -- the dedupe key
    trim(first_name)                   AS first_name,
    trim(last_name)                    AS last_name,
    NULLIF(trim(company_id), '')       AS company_id,
    NULLIF(trim(owner_id), '')         AS owner_id,
    lower(trim(lifecycle_stage))       AS lifecycle_stage,
    date(created_date)                 AS created_date
FROM raw_contacts;

-- One row per person: the earliest contact record for each email_key.
DROP VIEW IF EXISTS stg_people;
CREATE VIEW stg_people AS
SELECT * FROM (
    SELECT c.*,
           ROW_NUMBER() OVER (PARTITION BY email_key ORDER BY created_date, contact_id) AS rn,
           COUNT(*)     OVER (PARTITION BY email_key)                                  AS records_for_person
    FROM stg_contacts c
) WHERE rn = 1;

DROP VIEW IF EXISTS stg_campaigns;
CREATE VIEW stg_campaigns AS
SELECT
    trim(campaign_id)                  AS campaign_id,
    trim(campaign_name)                AS campaign_name,
    -- Channel casing drifts ('Paid Social' vs 'paid social'); normalise it.
    upper(substr(trim(channel), 1, 1)) || lower(substr(trim(channel), 2)) AS channel,
    lower(trim(utm_source))            AS utm_source,
    lower(trim(utm_medium))            AS utm_medium
FROM raw_campaigns;

DROP VIEW IF EXISTS stg_deals;
CREATE VIEW stg_deals AS
WITH d AS (
    SELECT
        trim(deal_id)                              AS deal_id,
        trim(deal_name)                            AS deal_name,
        NULLIF(trim(company_id), '')               AS company_id,
        NULLIF(trim(owner_id), '')                 AS owner_id,
        trim(pipeline)                             AS pipeline,
        deal_stage                                 AS raw_stage,
        CAST(NULLIF(trim(amount), '') AS REAL)     AS amount,
        NULLIF(upper(trim(currency)), '')          AS currency_raw,
        date(create_date)                          AS create_date,
        date(close_date)                           AS close_date,
        NULLIF(trim(primary_contact_id), '')       AS primary_contact_id
    FROM raw_deals
)
SELECT
    d.*,
    -- Blank currency means the portal default. This sample assumes USD and
    -- the audit flags every row where that assumption was made.
    COALESCE(d.currency_raw, 'USD')                AS currency,
    sm.stage,
    sm.stage_order,
    sm.is_closed,
    sm.is_won,
    sm.max_days_in_stage,
    d.amount * fx.rate_to_usd                      AS amount_usd,
    strftime('%Y', d.close_date) || '-Q' ||
        ((CAST(strftime('%m', d.close_date) AS INTEGER) + 2) / 3) AS close_quarter
FROM d
LEFT JOIN stage_map sm ON sm.raw_value = lower(trim(d.raw_stage))
LEFT JOIN fx_rates  fx ON fx.currency  = COALESCE(d.currency_raw, 'USD');

-- Stage history with exact duplicate rows removed and labels mapped.
DROP VIEW IF EXISTS stg_stage_history;
CREATE VIEW stg_stage_history AS
SELECT deal_id, raw_stage, stage, stage_order, is_closed, is_won, changed_at FROM (
    SELECT
        trim(h.deal_id)        AS deal_id,
        h.deal_stage           AS raw_stage,
        sm.stage, sm.stage_order, sm.is_closed, sm.is_won,
        datetime(h.changed_at) AS changed_at,
        ROW_NUMBER() OVER (
            PARTITION BY trim(h.deal_id), sm.stage, datetime(h.changed_at)
            ORDER BY h.history_id) AS rn
    FROM raw_deal_stage_history h
    LEFT JOIN stage_map sm ON sm.raw_value = lower(trim(h.deal_stage))
) WHERE rn = 1;

DROP VIEW IF EXISTS stg_touches;
CREATE VIEW stg_touches AS
SELECT
    trim(touch_id)        AS touch_id,
    trim(contact_id)      AS contact_id,
    trim(campaign_id)     AS campaign_id,
    trim(touch_type)      AS touch_type,
    datetime(touched_at)  AS touched_at
FROM raw_touches;
