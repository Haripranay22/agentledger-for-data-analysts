"""
Cash Flow Analyzer — Deterministic Python implementation.

CRITICAL: This module computes all financial metrics in Python.
The same logic is mirrored in dbt/models/marts/fct_user_metrics.sql.
Outputs are reconciled against dbt SQL before the LLM layer sees any numbers.

Interview talking point:
  "I compute the same 8 metrics in both Python and dbt SQL and assert they match.
   That's my data quality story — if they differ, something's wrong upstream."
"""

from __future__ import annotations

import logging
from collections import defaultdict
from statistics import mean, stdev

from agentledger.schemas.models import CashFlowMetrics, CategorizedTransaction

logger = logging.getLogger(__name__)


def compute_metrics(
    user_id: str,
    transactions: list[CategorizedTransaction],
) -> CashFlowMetrics:
    """
    Compute all 8 cash-flow metrics from categorized transactions.

    Args:
        user_id: The borrower being analyzed.
        transactions: Categorized and validated transactions.

    Returns:
        CashFlowMetrics — fully deterministic, no estimation.
    """
    if not transactions:
        raise ValueError(f"No transactions provided for user={user_id}")

    # Group by month
    monthly_income: dict[str, float] = defaultdict(float)
    monthly_expenses: dict[str, float] = defaultdict(float)
    monthly_nsf: dict[str, int] = defaultdict(int)
    monthly_balances: dict[str, list[float]] = defaultdict(list)
    monthly_debt: dict[str, float] = defaultdict(float)
    monthly_discretionary: dict[str, float] = defaultdict(float)
    monthly_rent: dict[str, float] = defaultdict(float)

    for txn in transactions:
        month_key = txn.transaction_date.strftime("%Y-%m")
        amt = abs(txn.amount)

        if txn.is_income:
            monthly_income[month_key] += amt
        else:
            monthly_expenses[month_key] += amt

            if txn.our_category == "nsf_fee":
                monthly_nsf[month_key] += 1
            if txn.our_category == "debt_payment":
                monthly_debt[month_key] += amt
            if not txn.is_essential:
                monthly_discretionary[month_key] += amt
            if txn.our_category == "rent_mortgage":
                monthly_rent[month_key] += amt

    months = sorted(set(list(monthly_income.keys()) + list(monthly_expenses.keys())))
    n_months = len(months)

    if n_months == 0:
        raise ValueError("No monthly data could be derived.")

    # 1. Average monthly income
    income_series = [monthly_income.get(m, 0.0) for m in months]
    avg_monthly_income = mean(income_series)

    # 2. Income stability — coefficient of variation (lower = more stable)
    income_cv = (stdev(income_series) / avg_monthly_income) if avg_monthly_income > 0 else 999.0

    # 3. Average monthly expenses
    expense_series = [monthly_expenses.get(m, 0.0) for m in months]
    avg_monthly_expenses = mean(expense_series)

    # 4. Debt-to-income ratio
    avg_debt_payment = mean([monthly_debt.get(m, 0.0) for m in months])
    dti_ratio = avg_debt_payment / avg_monthly_income if avg_monthly_income > 0 else 999.0

    # 5. NSF / overdraft event count (total, not monthly average)
    total_nsf_events = sum(monthly_nsf.values())

    # 6. Discretionary spending ratio
    avg_discretionary = mean([monthly_discretionary.get(m, 0.0) for m in months])
    discretionary_spending_ratio = (
        avg_discretionary / avg_monthly_expenses if avg_monthly_expenses > 0 else 0.0
    )

    # 7. Rent-to-income ratio
    avg_rent = mean([monthly_rent.get(m, 0.0) for m in months])
    rent_to_income_ratio = avg_rent / avg_monthly_income if avg_monthly_income > 0 else 0.0

    # 8. Cash buffer days — avg surplus / daily expense rate
    avg_surplus = avg_monthly_income - avg_monthly_expenses
    daily_expense = avg_monthly_expenses / 30.0
    cash_buffer_days = avg_surplus / daily_expense if daily_expense > 0 else 0.0

    metrics = CashFlowMetrics(
        user_id=user_id,
        avg_monthly_income=round(avg_monthly_income, 2),
        income_cv=round(income_cv, 4),
        avg_monthly_expenses=round(avg_monthly_expenses, 2),
        dti_ratio=round(dti_ratio, 4),
        total_nsf_events=total_nsf_events,
        discretionary_spending_ratio=round(discretionary_spending_ratio, 4),
        rent_to_income_ratio=round(rent_to_income_ratio, 4),
        cash_buffer_days=round(cash_buffer_days, 1),
        months_analyzed=n_months,
    )

    logger.info(
        "Metrics computed for user=%s | income=%.0f | dti=%.2f | nsf=%d | buffer_days=%.0f",
        user_id,
        metrics.avg_monthly_income,
        metrics.dti_ratio,
        metrics.total_nsf_events,
        metrics.cash_buffer_days,
    )
    return metrics
