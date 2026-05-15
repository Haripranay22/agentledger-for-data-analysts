"""
Smoke test: risk_assess_node → validate_node → hitl_check_node → report_node

Bypasses ingest/profile/categorize (Week 1 TODOs) by injecting synthetic
pre-categorized transactions directly into WorkflowState.

Usage:
    cd agentledger/
    python scripts/smoke_test_risk_assess.py

Requires: GOOGLE_API_KEY in .env
"""

from __future__ import annotations

import logging
import sys
import uuid

sys.stdout.reconfigure(encoding="utf-8")
from datetime import date, timedelta
from pathlib import Path

# Load .env before any imports that need the API key
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agentledger.analysis.cash_flow import compute_metrics
from agentledger.schemas.models import CashFlowMetrics, CategorizedTransaction, WorkflowState
from agentledger.workflow.nodes import (
    hitl_check_node,
    report_node,
    risk_assess_node,
    validate_node,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def make_synthetic_transactions(user_id: str, scenario: str) -> list[CategorizedTransaction]:
    """
    Generate 6 months of synthetic transactions for two borrower personas.

    scn_001_stable_w2:  Monthly salary $5,500, rent $1,800, no NSF
    scn_002_gig_worker: Irregular income ~$4,200/mo (CV=0.42), no NSF
    """
    today = date.today()
    txns: list[CategorizedTransaction] = []
    tx_counter = 0

    def txn(
        days_ago: int,
        amount: float,
        merchant: str,
        category: str,
        is_income: bool,
        is_recurring: bool,
        is_essential: bool,
    ) -> CategorizedTransaction:
        nonlocal tx_counter
        tx_counter += 1
        return CategorizedTransaction(
            transaction_id=f"tx_{user_id}_{tx_counter:04d}",
            account_id=f"acc_{user_id}",
            user_id=user_id,
            transaction_date=today - timedelta(days=days_ago),
            amount=amount,
            merchant_name=merchant,
            description=merchant,
            plaid_category=[],
            pending=False,
            our_category=category,
            confidence_score=0.95,
            is_income=is_income,
            is_recurring=is_recurring,
            is_essential=is_essential,
            categorization_source="ml_model",
        )

    if scenario == "scn_001_stable_w2":
        for month_offset in range(6):
            base = month_offset * 30
            txns.append(txn(base + 1,  5500.0, "EMPLOYER PAYROLL",    "income_salary",    True,  True,  False))
            txns.append(txn(base + 2, -1800.0, "PROPERTY MGMT",       "rent_mortgage",    False, True,  True))
            txns.append(txn(base + 5,  -320.0, "WHOLE FOODS",         "groceries",        False, True,  True))
            txns.append(txn(base + 8,  -120.0, "ELECTRIC CO",         "utilities",        False, True,  True))
            txns.append(txn(base + 10, -450.0, "VISA CREDIT CARD",    "debt_payment",     False, True,  False))
            txns.append(txn(base + 12, -200.0, "RESTAURANTS & BARS",  "dining_entertainment", False, False, False))
            txns.append(txn(base + 15,  -60.0, "NETFLIX / SPOTIFY",   "subscription",     False, True,  False))
            txns.append(txn(base + 20,  -80.0, "UBER / LYFT",         "transportation",   False, False, False))

    elif scenario == "scn_002_gig_worker":
        # Irregular monthly incomes matching CV ~ 0.42
        incomes = [5200.0, 3100.0, 4800.0, 2900.0, 5500.0, 3600.0]
        for month_offset, income in enumerate(incomes):
            base = month_offset * 30
            txns.append(txn(base + 3,  income,  "STRIPE PAYOUT",       "income_freelance",  True,  False, False))
            txns.append(txn(base + 5, -1400.0, "LANDLORD ZELLE",      "rent_mortgage",     False, True,  True))
            txns.append(txn(base + 7,  -280.0, "TRADER JOES",         "groceries",         False, True,  True))
            txns.append(txn(base + 9,  -100.0, "GAS & ELECTRIC",      "utilities",         False, True,  True))
            txns.append(txn(base + 11, -250.0, "RESTAURANTS & BARS",  "dining_entertainment", False, False, False))
            txns.append(txn(base + 14,  -50.0, "ADOBE / FIGMA",       "subscription",      False, True,  False))
            txns.append(txn(base + 18,  -90.0, "GASOLINE",            "transportation",    False, False, False))

    return txns


def run_smoke_test(scenario: str) -> None:
    logger.info("=" * 60)
    logger.info("SMOKE TEST: %s", scenario)
    logger.info("=" * 60)

    user_id = f"test_{scenario}"
    transactions = make_synthetic_transactions(user_id, scenario)
    metrics = compute_metrics(user_id, transactions)

    state = WorkflowState(
        user_id=user_id,
        loan_amount=25_000.0,
        loan_purpose="Home improvement",
        transactions=transactions,
        metrics=metrics,
        run_id=str(uuid.uuid4()),
    )

    logger.info("Metrics: income=%.0f | dti=%.2f | nsf=%d | buffer_days=%.0f | cv=%.3f",
                metrics.avg_monthly_income, metrics.dti_ratio,
                metrics.total_nsf_events, metrics.cash_buffer_days, metrics.income_cv)

    # --- risk_assess ---
    state = risk_assess_node(state, {})

    ra = state.risk_assessment
    assert ra is not None
    logger.info("Risk score: %d | recommendation: %s | confidence: %.2f",
                ra.risk_score, ra.recommendation, ra.confidence)
    logger.info("Summary: %s", ra.reasoning_summary)

    # --- validate ---
    state = validate_node(state, {})

    vr = state.validation_result
    assert vr is not None
    logger.info("Validation: validity=%.2f | passed=%s | hallucinated=%d",
                vr.overall_validity, vr.passed, len(vr.hallucinated_claims))

    # --- hitl_check ---
    state = hitl_check_node(state, {})
    logger.info("Escalate to human: %s | reasons: %s",
                state.escalate_to_human, state.escalation_reasons)

    # --- report ---
    state = report_node(state, {})
    if state.final_report_path:
        logger.info("Report written: %s", state.final_report_path)
        print("\n" + "=" * 60)
        print(open(state.final_report_path, encoding="utf-8").read())
    else:
        logger.warning("No report generated")

    logger.info("DONE: %s\n", scenario)


if __name__ == "__main__":
    run_smoke_test("scn_001_stable_w2")
    run_smoke_test("scn_002_gig_worker")
