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
        is_essential=False,
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
