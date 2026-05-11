-- stg_transactions.sql
-- Raw Plaid data with light typing + column normalization.
-- No business logic here — that lives in intermediate + marts.

{{
    config(
        materialized='view',
        description='Lightly typed Plaid transactions — one row per transaction'
    )
}}

SELECT
    transaction_id,
    account_id,
    user_id,
    transaction_date::date                          AS transaction_date,
    amount::decimal(12, 2)                          AS amount,
    COALESCE(merchant_name, '')                     AS merchant_name,
    COALESCE(description, '')                       AS description,
    COALESCE(plaid_category, ARRAY[]::text[])       AS plaid_category,
    pending::boolean                                AS pending,
    ingested_at::timestamptz                        AS ingested_at
FROM {{ source('plaid', 'raw_transactions') }}
WHERE
    transaction_date <= CURRENT_DATE              -- no future dates
    AND amount BETWEEN -50000 AND 50000           -- sanity bounds
