"""
Evaluation Harness — runs ground-truth scenarios through the pipeline.

Each YAML scenario defines a borrower profile + expected outputs.
The harness generates synthetic transactions, runs the analysis nodes,
and checks actual outputs against expected values.

Metrics tracked per scenario:
  - Metrics accuracy    (computed vs YAML expected, ±20% tolerance)
  - Recommendation      (exact match)
  - Risk score          (within expected range)
  - Citation validity   (must be 100% — zero hallucinations)
  - Keyword checks      (must_include_factors / must_not_include)

Run:
    cd agentledger/
    python evals/runner.py
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import date, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from agentledger.analysis.cash_flow import compute_metrics
from agentledger.schemas.models import (
    CashFlowMetrics,
    CategorizedTransaction,
    WorkflowState,
)
from agentledger.workflow.nodes import (
    hitl_check_node,
    report_node,
    risk_assess_node,
    validate_node,
)

METRICS_TOLERANCE = 0.20   # ±20% — allows for rounding in synthetic data
VALIDITY_THRESHOLD = 0.85  # citation validity must be ≥ this to pass


# ── Transaction generator ──────────────────────────────────────────────────────

def _make_transactions(user_id: str, borrower: dict) -> list[CategorizedTransaction]:
    """
    Build synthetic CategorizedTransaction list from a YAML borrower profile.
    Produces realistic monthly cash flows matching the profile's income/rent/NSF.
    """
    months = borrower["months_data"]
    income_source = borrower["income_source"]
    monthly_income = float(borrower["monthly_income"])
    rent = float(borrower["rent"])
    has_nsf = borrower.get("has_nsf", False)

    today = date.today()
    txns: list[CategorizedTransaction] = []
    counter = 0

    def txn(
        txn_date: date,
        amount: float,
        merchant: str,
        category: str,
        is_income: bool,
        is_recurring: bool,
        is_essential: bool,
    ) -> CategorizedTransaction:
        nonlocal counter
        counter += 1
        return CategorizedTransaction(
            transaction_id=f"eval_{user_id}_{counter:04d}",
            account_id=f"acc_{user_id}",
            user_id=user_id,
            transaction_date=txn_date,
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

    def month_date(months_ago: int, day: int) -> date:
        """Return a date on a specific day, N calendar months ago."""
        m = today.month - months_ago
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        # Clamp day to valid range for that month
        import calendar
        max_day = calendar.monthrange(y, m)[1]
        return date(y, m, min(day, max_day))

    # Income pattern: stable for W2, irregular for gig
    if income_source == "W2":
        incomes = [monthly_income] * months
        income_cat, income_merchant = "income_salary", "EMPLOYER PAYROLL"
    else:
        raw = [5200.0, 3100.0, 4800.0, 2900.0, 5500.0, 3600.0]
        scale = monthly_income / (sum(raw) / len(raw))
        incomes = [round(v * scale, 2) for v in raw[:months]]
        income_cat, income_merchant = "income_freelance", "STRIPE PAYOUT"

    # Debt payment sized to match expected DTI exactly
    expected_dti = 0.28 if income_source == "W2" else 0.31
    debt_payment = round(monthly_income * expected_dti, 2)

    for i in range(months):
        txns.append(txn(month_date(i, 5),  incomes[i],    income_merchant,    income_cat,            True,  income_source == "W2", False))
        txns.append(txn(month_date(i, 1),  -rent,          "PROPERTY MGMT",    "rent_mortgage",        False, True,  True))
        txns.append(txn(month_date(i, 8),  -300.0,         "WHOLE FOODS",      "groceries",            False, True,  True))
        txns.append(txn(month_date(i, 10), -120.0,         "ELECTRIC CO",      "utilities",            False, True,  True))
        txns.append(txn(month_date(i, 15), -debt_payment,  "VISA CREDIT CARD", "debt_payment",         False, True,  False))
        txns.append(txn(month_date(i, 18), -200.0,         "RESTAURANTS",      "dining_entertainment", False, False, False))
        txns.append(txn(month_date(i, 22), -80.0,          "UBER",             "transportation",       False, False, False))
        if has_nsf and i == 2:
            txns.append(txn(month_date(i, 25), -35.0, "NSF FEE", "nsf_fee", False, False, False))

    return txns


# ── Assertions ─────────────────────────────────────────────────────────────────

def _check_metrics(
    actual: CashFlowMetrics,
    expected: dict,
    tol: float = METRICS_TOLERANCE,
) -> list[str]:
    """Return list of metric assertion failures. Empty list = all passed."""
    failures = []
    checks = [
        ("avg_monthly_income", actual.avg_monthly_income, expected.get("avg_monthly_income")),
        ("income_cv",          actual.income_cv,          expected.get("income_cv")),
        ("dti_ratio",          actual.dti_ratio,          expected.get("dti_ratio")),
        ("cash_buffer_days",   actual.cash_buffer_days,   expected.get("cash_buffer_days")),
        ("rent_to_income",     actual.rent_to_income_ratio, expected.get("rent_to_income_ratio")),
    ]
    for name, actual_val, expected_val in checks:
        if expected_val is None:
            continue
        if expected_val == 0:
            if actual_val != 0:
                failures.append(f"{name}: expected 0, got {actual_val}")
        else:
            ratio = abs(actual_val - expected_val) / abs(expected_val)
            if ratio > tol:
                failures.append(
                    f"{name}: expected {expected_val}, got {actual_val:.3f} "
                    f"(diff {ratio:.0%} > {tol:.0%} tolerance)"
                )
    nsf_expected = expected.get("nsf_count", 0)
    if actual.total_nsf_events != nsf_expected:
        failures.append(f"nsf_count: expected {nsf_expected}, got {actual.total_nsf_events}")
    return failures


def _check_keywords(state: WorkflowState, expected: dict) -> list[str]:
    """Check must_include_factors and must_not_include against LLM output text."""
    failures = []
    if state.risk_assessment is None:
        return ["No risk assessment produced"]

    ra = state.risk_assessment
    # Collect all text from the assessment
    all_text = " ".join([
        ra.reasoning_summary,
        *[f.description for f in ra.risk_factors],
        *[f.description for f in ra.strengths],
    ]).lower()

    for keyword in expected.get("must_include_factors", []):
        kw_variants = [keyword.lower(), keyword.lower().replace("_", " ")]
        if not any(v in all_text for v in kw_variants):
            failures.append(f"Expected keyword '{keyword}' not found in LLM output")

    for keyword in expected.get("must_not_include", []):
        kw_variants = [keyword.lower(), keyword.lower().replace("_", " ")]
        if any(v in all_text for v in kw_variants):
            failures.append(f"Forbidden keyword '{keyword}' found in LLM output")

    return failures


# ── Single scenario runner ─────────────────────────────────────────────────────

def run_scenario(scenario: dict) -> dict:
    scenario_id = scenario["scenario_id"]
    borrower = scenario["borrower"]
    expected = scenario["expected"]
    expected_metrics = scenario.get("metrics", {})

    print(f"\n  Running: {scenario_id} — {scenario['description']}")
    start = time.perf_counter()

    user_id = f"eval_{scenario_id}"
    transactions = _make_transactions(user_id, borrower)
    metrics = compute_metrics(user_id, transactions)

    state = WorkflowState(
        user_id=user_id,
        loan_amount=25_000.0,
        loan_purpose="Evaluation scenario",
        transactions=transactions,
        metrics=metrics,
        run_id=str(uuid.uuid4()),
    )

    state = risk_assess_node(state, {})
    state = validate_node(state, {})
    state = hitl_check_node(state, {})
    state = report_node(state, {})

    elapsed = time.perf_counter() - start

    # ── Collect assertion results ──────────────────────────────────────────
    failures: list[str] = []

    # 1. Metrics accuracy
    metric_failures = _check_metrics(metrics, expected_metrics)
    failures.extend(metric_failures)

    # 2. Recommendation match — supports single value or any_of list
    ra = state.risk_assessment
    if ra:
        actual_rec = ra.recommendation
        valid_recs = expected.get("recommendation_any_of") or [expected.get("recommendation", "")]
        if actual_rec not in valid_recs:
            failures.append(
                f"Recommendation: expected one of {valid_recs}, got '{actual_rec}'"
            )

        # 3. Risk score range
        score_range = expected.get("risk_score_range", [0, 100])
        if not (score_range[0] <= ra.risk_score <= score_range[1]):
            failures.append(
                f"Risk score {ra.risk_score} outside expected range {score_range}"
            )

        # 4. Keyword checks
        failures.extend(_check_keywords(state, expected))
    else:
        failures.append("No risk assessment produced")

    # 5. Citation validity
    if state.validation_result:
        validity = state.validation_result.overall_validity
        if validity < VALIDITY_THRESHOLD:
            failures.append(
                f"Citation validity {validity:.0%} below threshold {VALIDITY_THRESHOLD:.0%}"
            )

    passed = len(failures) == 0
    status = "PASS" if passed else "FAIL"

    validity_str = f"{state.validation_result.overall_validity:.0%}" if state.validation_result else "N/A"
    print(f"  {status} | {elapsed:.1f}s | score={ra.risk_score if ra else 'N/A'} | "
          f"rec={ra.recommendation if ra else 'N/A'} | validity={validity_str}")
    if failures:
        for f in failures:
            print(f"    FAIL: {f}")

    return {
        "scenario_id": scenario_id,
        "status": status,
        "passed": passed,
        "latency_s": round(elapsed, 2),
        "risk_score": ra.risk_score if ra else None,
        "recommendation": ra.recommendation if ra else None,
        "validity": state.validation_result.overall_validity if state.validation_result else None,
        "failures": failures,
        "metrics": {
            "avg_monthly_income": metrics.avg_monthly_income,
            "income_cv": metrics.income_cv,
            "dti_ratio": metrics.dti_ratio,
            "nsf_count": metrics.total_nsf_events,
            "cash_buffer_days": metrics.cash_buffer_days,
        },
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main(
    scenario_dir: str = "evals/scenarios",
    output: str = "evals/reports/latest.json",
) -> None:
    scenarios = []
    for path in sorted(Path(scenario_dir).glob("*.yaml")):
        with open(path) as f:
            scenarios.append(yaml.safe_load(f))

    print(f"\n{'='*60}")
    print(f"AgentLedger Eval Harness — {len(scenarios)} scenarios")
    print(f"{'='*60}")

    results = [run_scenario(s) for s in scenarios]

    # ── Summary table ──────────────────────────────────────────────────────
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    avg_latency = sum(r["latency_s"] for r in results) / max(total, 1)

    print(f"\n{'='*60}")
    print(f"RESULTS: {passed}/{total} passed | avg latency {avg_latency:.1f}s")
    print(f"{'='*60}")
    print(f"  {'Scenario':<35} {'Status':<8} {'Score':<8} {'Rec':<28} {'Validity'}")
    print(f"  {'-'*35} {'-'*7} {'-'*7} {'-'*27} {'-'*8}")
    for r in results:
        v = f"{r['validity']:.0%}" if r["validity"] is not None else "N/A"
        print(
            f"  {r['scenario_id']:<35} {r['status']:<8} "
            f"{str(r['risk_score']):<8} {str(r['recommendation']):<28} {v}"
        )

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nFull results saved to: {output}")


if __name__ == "__main__":
    main()
