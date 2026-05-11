-- fct_user_metrics.sql
-- 8 core cash-flow metrics per user, computed in SQL.
-- MUST reconcile with Python output in agentledger/analysis/cash_flow.py.
-- If they differ → data quality issue. Fix upstream.

{{
    config(
        materialized='table',
        description='Final credit analysis features per user — source of truth for LLM risk assessment'
    )
}}

WITH monthly AS (
    SELECT
        user_id,
        DATE_TRUNC('month', transaction_date)::date                  AS month,
        SUM(CASE WHEN is_income      THEN ABS(amount) ELSE 0 END)    AS monthly_income,
        SUM(CASE WHEN NOT is_income  THEN ABS(amount) ELSE 0 END)    AS monthly_expenses,
        SUM(CASE WHEN our_category = 'nsf_fee'        THEN 1 ELSE 0 END) AS nsf_count,
        SUM(CASE WHEN our_category = 'debt_payment'   THEN ABS(amount) ELSE 0 END) AS debt_payments,
        SUM(CASE WHEN NOT is_essential AND NOT is_income THEN ABS(amount) ELSE 0 END) AS discretionary_spend,
        SUM(CASE WHEN our_category = 'rent_mortgage'  THEN ABS(amount) ELSE 0 END) AS rent_payments
    FROM {{ ref('int_transactions_categorized') }}
    GROUP BY 1, 2
)

SELECT
    user_id,

    -- 1. Average monthly income
    ROUND(AVG(monthly_income)::numeric, 2)                                              AS avg_monthly_income,

    -- 2. Income stability — coefficient of variation (lower = more stable)
    ROUND(
        (STDDEV(monthly_income) / NULLIF(AVG(monthly_income), 0))::numeric, 4
    )                                                                                    AS income_cv,

    -- 3. Average monthly expenses
    ROUND(AVG(monthly_expenses)::numeric, 2)                                            AS avg_monthly_expenses,

    -- 4. Debt-to-income ratio
    ROUND(
        (AVG(debt_payments) / NULLIF(AVG(monthly_income), 0))::numeric, 4
    )                                                                                    AS dti_ratio,

    -- 5. NSF / overdraft event count (total)
    SUM(nsf_count)::int                                                                  AS total_nsf_events,

    -- 6. Discretionary spending ratio
    ROUND(
        (AVG(discretionary_spend) / NULLIF(AVG(monthly_expenses), 0))::numeric, 4
    )                                                                                    AS discretionary_spending_ratio,

    -- 7. Rent-to-income ratio
    ROUND(
        (AVG(rent_payments) / NULLIF(AVG(monthly_income), 0))::numeric, 4
    )                                                                                    AS rent_to_income_ratio,

    -- 8. Cash buffer days
    ROUND(
        (
            (AVG(monthly_income) - AVG(monthly_expenses))
            / NULLIF(AVG(monthly_expenses) / 30.0, 0)
        )::numeric, 1
    )                                                                                    AS cash_buffer_days,

    COUNT(DISTINCT month)                                                                AS months_analyzed,
    MIN(month)                                                                           AS analysis_start,
    MAX(month)                                                                           AS analysis_end,
    CURRENT_TIMESTAMP                                                                    AS computed_at

FROM monthly
GROUP BY 1
