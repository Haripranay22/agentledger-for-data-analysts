"""Unit tests for the deterministic Cash Flow Analyzer."""

from __future__ import annotations

from datetime import date

import pytest

from agentledger.analysis.cash_flow import compute_metrics
from agentledger.schemas.models import CategorizedTransaction


def make_txn(
    txn_id: str,
    amount: float,
    category: str,
    is_income: bool,
    month: int = 1,
    is_essential: bool = False,
) -> CategorizedTransaction:
    return CategorizedTransaction(
        transaction_id=txn_id,
        account_id="acc_001",
        user_id="user_001",
        transaction_date=date(2024, month, 15),
        amount=amount,
        description="test transaction",
        our_category=category,
        confidence_score=0.95,
        is_income=is_income,
        is_recurring=False,
        is_essential=is_essential,
        categorization_source="ml_model",
    )


def test_avg_monthly_income():
    txns = [
        make_txn("t1", 5000.0, "income_salary", True, month=1),
        make_txn("t2", 5500.0, "income_salary", True, month=2),
        make_txn("t3", -1500.0, "rent_mortgage", False, month=1),
    ]
    metrics = compute_metrics("user_001", txns)
    assert metrics.avg_monthly_income == pytest.approx(5250.0, rel=0.01)


def test_nsf_count():
    txns = [
        make_txn("t1", 5000.0, "income_salary", True, month=1),
        make_txn("t2", -35.0, "nsf_fee", False, month=1),
        make_txn("t3", -35.0, "nsf_fee", False, month=2),
    ]
    metrics = compute_metrics("user_001", txns)
    assert metrics.total_nsf_events == 2


def test_no_transactions_raises():
    with pytest.raises(ValueError):
        compute_metrics("user_001", [])


def test_dti_ratio():
    txns = [
        make_txn("t1", 5000.0,  "income_salary", True,  month=1),
        make_txn("t2", -650.0,  "debt_payment",  False, month=1),
        make_txn("t3", 5000.0,  "income_salary", True,  month=2),
        make_txn("t4", -650.0,  "debt_payment",  False, month=2),
    ]
    metrics = compute_metrics("user_001", txns)
    # DTI = avg_debt / avg_income = 650 / 5000 = 0.13
    assert metrics.dti_ratio == pytest.approx(0.13, rel=0.01)


def test_income_cv_zero_for_stable_income():
    txns = [
        make_txn(f"t{i}", 5000.0, "income_salary", True, month=i)
        for i in range(1, 7)
    ]
    metrics = compute_metrics("user_001", txns)
    assert metrics.income_cv == pytest.approx(0.0, abs=1e-9)


def test_income_cv_positive_for_variable_income():
    txns = [
        make_txn("t1", 2000.0, "income_freelance", True, month=1),
        make_txn("t2", 8000.0, "income_freelance", True, month=2),
        make_txn("t3", 3000.0, "income_freelance", True, month=3),
    ]
    metrics = compute_metrics("user_001", txns)
    assert metrics.income_cv > 0.3


def test_cash_buffer_days():
    # income $6000, expenses $3000 → surplus $3000, daily expense $100 → 30 days
    txns = [
        make_txn("t1", 6000.0,  "income_salary",  True,  month=1),
        make_txn("t2", -3000.0, "rent_mortgage",  False, month=1),
        make_txn("t3", 6000.0,  "income_salary",  True,  month=2),
        make_txn("t4", -3000.0, "rent_mortgage",  False, month=2),
    ]
    metrics = compute_metrics("user_001", txns)
    assert metrics.cash_buffer_days == pytest.approx(30.0, rel=0.01)


def test_cash_buffer_days_negative_when_expenses_exceed_income():
    txns = [
        make_txn("t1", 2000.0,  "income_salary", True,  month=1),
        make_txn("t2", -3000.0, "rent_mortgage", False, month=1),
        make_txn("t3", 2000.0,  "income_salary", True,  month=2),
        make_txn("t4", -3000.0, "rent_mortgage", False, month=2),
    ]
    metrics = compute_metrics("user_001", txns)
    assert metrics.cash_buffer_days < 0


def test_discretionary_spending_ratio():
    # essential: rent ($1000), groceries ($200) — non-essential: dining ($400)
    # total_expenses = 1600, discretionary = 400, ratio = 0.25
    txns = [
        make_txn("t1",  5000.0,  "income_salary",        True,  month=1),
        make_txn("t2", -1000.0,  "rent_mortgage",        False, month=1, is_essential=True),
        make_txn("t3",  -200.0,  "groceries",            False, month=1, is_essential=True),
        make_txn("t4",  -400.0,  "dining_entertainment", False, month=1, is_essential=False),
        make_txn("t5",  5000.0,  "income_salary",        True,  month=2),
        make_txn("t6", -1000.0,  "rent_mortgage",        False, month=2, is_essential=True),
        make_txn("t7",  -200.0,  "groceries",            False, month=2, is_essential=True),
        make_txn("t8",  -400.0,  "dining_entertainment", False, month=2, is_essential=False),
    ]
    metrics = compute_metrics("user_001", txns)
    assert metrics.discretionary_spending_ratio == pytest.approx(0.25, rel=0.01)


def test_rent_to_income_ratio():
    txns = [
        make_txn("t1", 4000.0,  "income_salary", True,  month=1),
        make_txn("t2", -1600.0, "rent_mortgage", False, month=1),
        make_txn("t3", 4000.0,  "income_salary", True,  month=2),
        make_txn("t4", -1600.0, "rent_mortgage", False, month=2),
    ]
    metrics = compute_metrics("user_001", txns)
    assert metrics.rent_to_income_ratio == pytest.approx(0.40, rel=0.01)


def test_months_analyzed():
    txns = [
        make_txn(f"t{m}", 5000.0, "income_salary", True, month=m)
        for m in range(1, 7)
    ]
    metrics = compute_metrics("user_001", txns)
    assert metrics.months_analyzed == 6


def test_nsf_count_zero_when_none():
    txns = [
        make_txn("t1", 5000.0,  "income_salary", True,  month=1),
        make_txn("t2", -1000.0, "rent_mortgage", False, month=1),
        make_txn("t3", 5000.0,  "income_salary", True,  month=2),
        make_txn("t4", -1000.0, "rent_mortgage", False, month=2),
    ]
    metrics = compute_metrics("user_001", txns)
    assert metrics.total_nsf_events == 0
