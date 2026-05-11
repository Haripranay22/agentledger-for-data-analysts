-- int_transactions_categorized.sql
-- Join staged transactions with ML categorization output.
-- This is the enriched layer the Cash Flow Analyzer and Risk Analyst consume.

{{
    config(
        materialized='view',
        description='Transactions enriched with ML category, income flags, recurring flags'
    )
}}

SELECT
    t.transaction_id,
    t.account_id,
    t.user_id,
    t.transaction_date,
    t.amount,
    t.merchant_name,
    t.description,
    t.plaid_category,
    t.pending,

    -- ML categorization
    c.our_category,
    c.confidence_score,
    c.categorization_source,

    -- Derived flags (deterministic — no LLM)
    CASE WHEN c.our_category LIKE 'income_%' THEN TRUE ELSE FALSE END   AS is_income,
    CASE WHEN c.our_category IN (
        'rent_mortgage', 'utilities', 'subscription', 'debt_payment'
    ) THEN TRUE ELSE FALSE END                                           AS is_recurring,
    CASE WHEN c.our_category IN (
        'rent_mortgage', 'utilities', 'groceries', 'healthcare'
    ) THEN TRUE ELSE FALSE END                                           AS is_essential

FROM {{ ref('stg_transactions') }} t
LEFT JOIN {{ source('ml', 'categorizations') }} c
    USING (transaction_id)
