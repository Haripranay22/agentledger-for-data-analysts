"""Unit tests for MemoGenerator (Markdown + HTML output)."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from agentledger.reporting.memo_generator import MemoGenerator
from agentledger.schemas.models import (
    CashFlowMetrics,
    RiskAssessment,
    RiskFactor,
    ValidationResult,
    WorkflowState,
)

# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_metrics(user_id: str = "USER_TEST") -> CashFlowMetrics:
    return CashFlowMetrics(
        user_id=user_id,
        avg_monthly_income=5500.0,
        income_cv=0.08,
        avg_monthly_expenses=3200.0,
        dti_ratio=0.12,
        total_nsf_events=0,
        discretionary_spending_ratio=0.31,
        rent_to_income_ratio=0.33,
        cash_buffer_days=43.0,
        months_analyzed=6,
    )


def _make_risk_assessment(recommendation: str = "approve") -> RiskAssessment:
    return RiskAssessment(
        risk_score=25,
        recommendation=recommendation,  # type: ignore[arg-type]
        confidence=0.91,
        reasoning_summary="Strong W-2 income with zero overdrafts and healthy buffer.",
        risk_factors=[
            RiskFactor(
                description="Moderate discretionary spending",
                severity="low",
                citations=["tx:abc123"],
            )
        ],
        strengths=[
            RiskFactor(
                description="Consistent salary deposits",
                severity="low",
                citations=["tx:def456"],
            )
        ],
        insufficient_data_areas=[],
    )


def _make_validation() -> ValidationResult:
    return ValidationResult(
        overall_validity=0.97,
        citation_checks=[],
        hallucinated_claims=[],
        passed=True,
        feedback_for_risk_analyst=None,
    )


def _make_state(
    escalate: bool = False,
    recommendation: str = "approve",
) -> WorkflowState:
    state = WorkflowState(
        user_id="USER_TEST",
        loan_amount=15000.0,
        loan_purpose="Home Improvement",
        run_id=str(uuid.uuid4()),
        metrics=_make_metrics(),
        risk_assessment=_make_risk_assessment(recommendation),
        validation_result=_make_validation(),
        escalate_to_human=escalate,
        escalation_reasons=["Low confidence: 0.55"] if escalate else [],
    )
    return state


# ── Markdown output ────────────────────────────────────────────────────────────

def test_markdown_contains_section_headers():
    md = MemoGenerator().generate_markdown(_make_state())
    for section in ["Executive Summary", "Cash Flow Analysis", "Risk Factors",
                    "Strengths", "Recommendation", "Methodology", "Audit"]:
        assert section in md, f"Section '{section}' missing from markdown"


def test_markdown_contains_borrower_metadata():
    md = MemoGenerator().generate_markdown(_make_state())
    assert "USER_TEST" in md
    assert "15000" in md        # Jinja2 %.0f format — no commas
    assert "Home Improvement" in md


def test_markdown_contains_metric_values():
    md = MemoGenerator().generate_markdown(_make_state())
    assert "5500" in md     # avg_monthly_income
    assert "3200" in md     # avg_monthly_expenses
    assert "12.0%" in md    # dti_ratio


def test_markdown_contains_risk_score_and_recommendation():
    md = MemoGenerator().generate_markdown(_make_state())
    assert "25" in md
    assert "APPROVE" in md


def test_markdown_contains_risk_factor_description():
    md = MemoGenerator().generate_markdown(_make_state())
    assert "Moderate discretionary spending" in md


def test_markdown_contains_strength_description():
    md = MemoGenerator().generate_markdown(_make_state())
    assert "Consistent salary deposits" in md


def test_markdown_no_escalation_block_when_not_escalated():
    md = MemoGenerator().generate_markdown(_make_state(escalate=False))
    assert "Escalated for Human Review" not in md


def test_markdown_has_escalation_block_when_escalated():
    md = MemoGenerator().generate_markdown(_make_state(escalate=True))
    assert "Escalated for Human Review" in md
    assert "Low confidence" in md


def test_markdown_contains_run_id():
    state = _make_state()
    md = MemoGenerator().generate_markdown(state)
    assert state.run_id in md


# ── HTML output ───────────────────────────────────────────────────────────────

def test_html_is_valid_html_document():
    html = MemoGenerator().generate_html(_make_state())
    assert "<!DOCTYPE html>" in html
    assert "<html" in html
    assert "</html>" in html


def test_html_contains_borrower_data():
    html = MemoGenerator().generate_html(_make_state())
    assert "USER_TEST" in html
    assert "15000" in html    # Jinja2 %.0f format — no commas


def test_html_contains_recommendation_class():
    html = MemoGenerator().generate_html(_make_state(recommendation="approve"))
    assert "decision-approve" in html


def test_html_decline_recommendation_class():
    html = MemoGenerator().generate_html(_make_state(recommendation="decline"))
    assert "decision-decline" in html


def test_html_contains_risk_score():
    html = MemoGenerator().generate_html(_make_state())
    assert ">25<" in html  # risk score in a div


# ── File saving ────────────────────────────────────────────────────────────────

def test_save_creates_markdown_file():
    state = _make_state()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = MemoGenerator().save(state, Path(tmpdir))
        assert path.exists()
        assert path.suffix == ".md"
        content = path.read_text()
        assert "USER_TEST" in content


def test_save_filename_format():
    state = _make_state()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = MemoGenerator().save(state, Path(tmpdir))
        assert f"memo_USER_TEST_{state.run_id[:8]}" in path.name


def test_save_creates_output_dir_if_missing():
    state = _make_state()
    with tempfile.TemporaryDirectory() as tmpdir:
        new_dir = Path(tmpdir) / "deep" / "nested"
        MemoGenerator().save(state, new_dir)
        assert new_dir.exists()
