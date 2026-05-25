"""
Integration tests for pipeline nodes that require no external APIs.

Covers: profile_node, analyze_node, validate_node, hitl_check_node, report_node.
Uses synthetic CategorizedTransaction objects — no Plaid, no LLM, no ML model needed.
"""

from __future__ import annotations

import tempfile
import uuid
from datetime import date
from pathlib import Path

import pytest

from agentledger.schemas.models import (
    CategorizedTransaction,
    RiskAssessment,
    RiskFactor,
    Transaction,
    ValidationResult,
    WorkflowState,
)
from agentledger.workflow.nodes import (
    analyze_node,
    hitl_check_node,
    profile_node,
    report_node,
    validate_node,
)

# ── Shared factories ───────────────────────────────────────────────────────────

def _txn(
    txn_id: str,
    amount: float,
    category: str,
    is_income: bool,
    month: int = 1,
    day: int = 15,
    description: str = "test",
    account_id: str = "acc_001",
    is_essential: bool = False,
    is_recurring: bool = False,
) -> CategorizedTransaction:
    return CategorizedTransaction(
        transaction_id=txn_id,
        account_id=account_id,
        user_id="usr_test",
        transaction_date=date(2024, month, day),
        amount=amount,
        description=description,
        our_category=category,
        confidence_score=0.95,
        is_income=is_income,
        is_recurring=is_recurring,
        is_essential=is_essential,
        categorization_source="ml_model",
    )


def _raw_txn(txn_id: str, description: str = "test", account_id: str = "acc") -> Transaction:
    return Transaction(
        transaction_id=txn_id,
        account_id=account_id,
        user_id="usr_test",
        transaction_date=date(2024, 1, 15),
        amount=-100.0,
        description=description,
    )


def _make_risk_assessment(
    risk_score: int = 30,
    recommendation: str = "approve",
    confidence: float = 0.90,
    tx_ids: list[str] | None = None,
) -> RiskAssessment:
    ids = tx_ids or ["txn_001", "txn_002"]
    return RiskAssessment(
        risk_score=risk_score,
        recommendation=recommendation,  # type: ignore[arg-type]
        confidence=confidence,
        reasoning_summary="Test risk summary.",
        risk_factors=[
            RiskFactor(description="Minor factor", severity="low", citations=[ids[0]])
        ],
        strengths=[
            RiskFactor(description="Strong income", severity="low", citations=[ids[1]])
        ],
        insufficient_data_areas=[],
    )


def _base_state(**kwargs) -> WorkflowState:
    return WorkflowState(
        user_id="usr_test",
        loan_amount=10_000.0,
        run_id=str(uuid.uuid4()),
        **kwargs,
    )


def _six_months_transactions(user_id: str = "usr_test") -> list[CategorizedTransaction]:
    """Minimal two-transaction-per-month set (income + rent) for 6 months."""
    txns = []
    for m in range(1, 7):
        txns.append(_txn(f"inc_{m}", 5000.0, "income_salary", True,  month=m, day=5))
        txns.append(_txn(f"rnt_{m}", -1800.0, "rent_mortgage", False, month=m, day=1,
                         is_essential=True, is_recurring=True))
        txns.append(_txn(f"dbt_{m}", -650.0,  "debt_payment",  False, month=m, day=10,
                         is_recurring=True))
    return txns


# ── profile_node ───────────────────────────────────────────────────────────────

class TestProfileNode:

    def test_passes_valid_transactions(self):
        raw = [_raw_txn("t1", "grocery", "acc_01")]
        state = _base_state(raw_transactions=raw)
        result = profile_node(state)
        assert len(result.raw_transactions) == 1

    def test_drops_empty_description(self):
        raw = [_raw_txn("t1", "", "acc_01")]
        state = _base_state(raw_transactions=raw)
        result = profile_node(state)
        assert len(result.raw_transactions) == 0

    def test_drops_empty_account_id(self):
        raw = [_raw_txn("t1", "valid description", "")]
        state = _base_state(raw_transactions=raw)
        result = profile_node(state)
        assert len(result.raw_transactions) == 0

    def test_drops_future_dated_transaction(self):
        txn = Transaction(
            transaction_id="t_future",
            account_id="acc_01",
            user_id="usr_test",
            transaction_date=date(2099, 1, 1),
            amount=-50.0,
            description="future transaction",
        )
        state = _base_state(raw_transactions=[txn])
        result = profile_node(state)
        assert len(result.raw_transactions) == 0

    def test_keeps_valid_and_drops_invalid(self):
        raw = [
            _raw_txn("t_good", "valid", "acc_01"),
            _raw_txn("t_bad",  "",      "acc_01"),
        ]
        state = _base_state(raw_transactions=raw)
        result = profile_node(state)
        assert len(result.raw_transactions) == 1
        assert result.raw_transactions[0].transaction_id == "t_good"

    def test_empty_input_returns_empty(self):
        state = _base_state(raw_transactions=[])
        result = profile_node(state)
        assert result.raw_transactions == []


# ── analyze_node ───────────────────────────────────────────────────────────────

class TestAnalyzeNode:

    def test_computes_metrics_from_transactions(self):
        txns = _six_months_transactions()
        state = _base_state(transactions=txns)
        result = analyze_node(state)
        assert result.metrics is not None
        assert result.metrics.avg_monthly_income == pytest.approx(5000.0, rel=0.01)

    def test_metrics_has_correct_months_analyzed(self):
        txns = _six_months_transactions()
        state = _base_state(transactions=txns)
        result = analyze_node(state)
        assert result.metrics.months_analyzed == 6

    def test_metrics_dtir_ratio(self):
        txns = _six_months_transactions()
        state = _base_state(transactions=txns)
        result = analyze_node(state)
        # debt = $650/mo, income = $5000/mo → DTI = 0.13
        assert result.metrics.dti_ratio == pytest.approx(0.13, rel=0.05)

    def test_metrics_rent_to_income(self):
        txns = _six_months_transactions()
        state = _base_state(transactions=txns)
        result = analyze_node(state)
        assert result.metrics.rent_to_income_ratio == pytest.approx(0.36, rel=0.05)

    def test_skips_if_no_transactions(self):
        state = _base_state(transactions=[])
        result = analyze_node(state)
        assert result.metrics is None

    def test_nsf_count_zero(self):
        txns = _six_months_transactions()
        state = _base_state(transactions=txns)
        result = analyze_node(state)
        assert result.metrics.total_nsf_events == 0

    def test_nsf_count_nonzero(self):
        txns = _six_months_transactions()
        txns.append(_txn("nsf_1", -35.0, "nsf_fee", False, month=3))
        state = _base_state(transactions=txns)
        result = analyze_node(state)
        assert result.metrics.total_nsf_events == 1


# ── validate_node ──────────────────────────────────────────────────────────────

class TestValidateNode:

    def test_passes_when_all_citations_valid(self):
        txns = _six_months_transactions()
        valid_ids = [t.transaction_id for t in txns]
        ra = _make_risk_assessment(tx_ids=valid_ids[:2])
        state = _base_state(transactions=txns, risk_assessment=ra)
        result = validate_node(state)
        assert result.validation_result is not None
        assert result.validation_result.passed is True
        assert result.validation_result.overall_validity == pytest.approx(1.0, abs=0.01)

    def test_fails_when_citations_are_hallucinated(self):
        txns = _six_months_transactions()
        ra = _make_risk_assessment(tx_ids=["fake_id_xyz", "another_fake"])
        state = _base_state(transactions=txns, risk_assessment=ra)
        result = validate_node(state)
        assert result.validation_result.passed is False
        assert result.validation_result.overall_validity < 0.85
        assert len(result.validation_result.hallucinated_claims) == 2

    def test_feedback_set_when_validation_fails(self):
        txns = _six_months_transactions()
        ra = _make_risk_assessment(tx_ids=["bad_id_1", "bad_id_2"])
        state = _base_state(transactions=txns, risk_assessment=ra)
        result = validate_node(state)
        assert result.validation_result.feedback_for_risk_analyst is not None
        assert "bad_id_1" in result.validation_result.feedback_for_risk_analyst

    def test_no_citations_fails_validation(self):
        txns = _six_months_transactions()
        ra = RiskAssessment(
            risk_score=40,
            recommendation="manual_review",
            confidence=0.70,
            reasoning_summary="No citations produced.",
            risk_factors=[RiskFactor(description="vague risk", severity="medium", citations=[])],
            strengths=[],
            insufficient_data_areas=[],
        )
        state = _base_state(transactions=txns, risk_assessment=ra)
        result = validate_node(state)
        assert result.validation_result.passed is False

    def test_skips_without_risk_assessment(self):
        txns = _six_months_transactions()
        state = _base_state(transactions=txns, risk_assessment=None)
        result = validate_node(state)
        assert result.validation_result is None

    def test_strips_tx_prefix_from_citation(self):
        txns = _six_months_transactions()
        valid_id = txns[0].transaction_id
        ra = _make_risk_assessment(tx_ids=[f"tx:{valid_id}", txns[1].transaction_id])
        state = _base_state(transactions=txns, risk_assessment=ra)
        result = validate_node(state)
        assert result.validation_result.passed is True


# ── hitl_check_node ────────────────────────────────────────────────────────────

class TestHitlCheckNode:

    def test_no_escalation_for_clean_assessment(self):
        txns = _six_months_transactions()
        ra = _make_risk_assessment(risk_score=25, confidence=0.92)
        vr = ValidationResult(
            overall_validity=1.0, citation_checks=[], hallucinated_claims=[],
            passed=True, feedback_for_risk_analyst=None,
        )
        state = _base_state(transactions=txns, risk_assessment=ra, validation_result=vr)
        result = hitl_check_node(state)
        assert result.escalate_to_human is False
        assert result.escalation_reasons == []

    def test_escalates_on_low_confidence(self):
        txns = _six_months_transactions()
        ra = _make_risk_assessment(risk_score=25, confidence=0.45)
        state = _base_state(transactions=txns, risk_assessment=ra)
        result = hitl_check_node(state)
        assert result.escalate_to_human is True
        assert any("confidence" in r.lower() for r in result.escalation_reasons)

    def test_escalates_on_ambiguous_risk_score(self):
        txns = _six_months_transactions()
        ra = _make_risk_assessment(risk_score=50, confidence=0.85)
        state = _base_state(transactions=txns, risk_assessment=ra)
        result = hitl_check_node(state)
        assert result.escalate_to_human is True
        assert any("risk score" in r.lower() for r in result.escalation_reasons)

    def test_escalates_on_insufficient_data(self):
        txns = _six_months_transactions()
        ra = RiskAssessment(
            risk_score=30, recommendation="approve", confidence=0.80,
            reasoning_summary="Summary.",
            risk_factors=[], strengths=[],
            insufficient_data_areas=["credit_history", "employment_verification"],
        )
        state = _base_state(transactions=txns, risk_assessment=ra)
        result = hitl_check_node(state)
        assert result.escalate_to_human is True
        assert any("insufficient" in r.lower() for r in result.escalation_reasons)

    def test_escalates_on_failed_validation(self):
        txns = _six_months_transactions()
        ra = _make_risk_assessment(risk_score=30, confidence=0.85)
        vr = ValidationResult(
            overall_validity=0.60, citation_checks=[], hallucinated_claims=["fake"],
            passed=False, feedback_for_risk_analyst="Fix citations.",
        )
        state = _base_state(transactions=txns, risk_assessment=ra, validation_result=vr)
        result = hitl_check_node(state)
        assert result.escalate_to_human is True

    def test_multiple_escalation_reasons_accumulated(self):
        txns = _six_months_transactions()
        ra = _make_risk_assessment(risk_score=50, confidence=0.45)
        state = _base_state(transactions=txns, risk_assessment=ra)
        result = hitl_check_node(state)
        assert len(result.escalation_reasons) >= 2

    def test_skips_without_risk_assessment(self):
        state = _base_state()
        result = hitl_check_node(state)
        assert result.escalate_to_human is False


# ── report_node ────────────────────────────────────────────────────────────────

class TestReportNode:

    def _full_state(self, tmp_dir: Path) -> WorkflowState:
        txns = _six_months_transactions()
        ra = _make_risk_assessment(
            tx_ids=[txns[0].transaction_id, txns[1].transaction_id]
        )
        state = _base_state(transactions=txns, risk_assessment=ra)
        state = analyze_node(state)
        return state

    def test_creates_markdown_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = self._full_state(Path(tmp))
            result = report_node(state)
            assert result.final_report_path is not None
            assert Path(result.final_report_path).exists()
            assert result.final_report_path.endswith(".md")

    def test_memo_contains_user_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = self._full_state(Path(tmp))
            result = report_node(state)
            content = Path(result.final_report_path).read_text()
            assert "usr_test" in content

    def test_memo_contains_risk_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = self._full_state(Path(tmp))
            result = report_node(state)
            content = Path(result.final_report_path).read_text()
            assert "30" in content  # risk_score from _make_risk_assessment

    def test_skips_without_metrics(self):
        txns = _six_months_transactions()
        ra = _make_risk_assessment(
            tx_ids=[txns[0].transaction_id, txns[1].transaction_id]
        )
        state = _base_state(transactions=txns, risk_assessment=ra, metrics=None)
        result = report_node(state)
        assert result.final_report_path is None

    def test_skips_without_risk_assessment(self):
        txns = _six_months_transactions()
        state = _base_state(transactions=txns)
        state = analyze_node(state)
        result = report_node(state)
        assert result.final_report_path is None


# ── End-to-end (no LLM) ────────────────────────────────────────────────────────

class TestPipelineWithoutLLM:
    """
    Runs analyze → validate → hitl_check → report with a pre-built RiskAssessment,
    verifying the nodes compose correctly without any external API calls.
    """

    def test_full_pipeline_approve_path(self):
        txns = _six_months_transactions()
        valid_ids = [t.transaction_id for t in txns[:2]]
        ra = _make_risk_assessment(risk_score=22, confidence=0.91, tx_ids=valid_ids)

        state = _base_state(transactions=txns, risk_assessment=ra)
        state = analyze_node(state)
        state = validate_node(state)
        state = hitl_check_node(state)
        state = report_node(state)

        assert state.metrics is not None
        assert state.validation_result is not None
        assert state.validation_result.passed is True
        assert state.escalate_to_human is False
        assert state.final_report_path is not None

    def test_full_pipeline_escalation_path(self):
        txns = _six_months_transactions()
        ra = _make_risk_assessment(risk_score=50, confidence=0.45,
                                   tx_ids=["bad_id", "another_bad"])

        state = _base_state(transactions=txns, risk_assessment=ra)
        state = analyze_node(state)
        state = validate_node(state)
        state = hitl_check_node(state)
        state = report_node(state)

        assert state.validation_result.passed is False
        assert state.escalate_to_human is True
        assert len(state.escalation_reasons) >= 2
