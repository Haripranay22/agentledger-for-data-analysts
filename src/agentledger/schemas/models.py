"""
Core Pydantic models for AgentLedger.

Every LLM input/output goes through these schemas.
No untyped dicts reach the agent layer.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

# ── Transaction ────────────────────────────────────────────────────────────────

class Transaction(BaseModel):
    """A single bank transaction from Plaid."""

    transaction_id: str
    account_id: str
    user_id: str
    transaction_date: date
    amount: float  # positive = credit (income), negative = debit (expense)
    merchant_name: str | None = None
    description: str
    plaid_category: list[str] = Field(default_factory=list)
    pending: bool = False


class CategorizedTransaction(Transaction):
    """Transaction enriched with our ML categorization."""

    our_category: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    is_income: bool
    is_recurring: bool
    is_essential: bool
    categorization_source: Literal["ml_model", "llm_fallback", "rule_based"]


# ── Cash Flow Metrics ──────────────────────────────────────────────────────────

class CashFlowMetrics(BaseModel):
    """
    8 core metrics computed deterministically in Python + dbt SQL.
    LLMs NEVER compute these — they only consume them.
    """

    user_id: str
    avg_monthly_income: float
    income_cv: float = Field(description="Coefficient of variation — income stability")
    avg_monthly_expenses: float
    dti_ratio: float = Field(description="Debt-to-income ratio")
    total_nsf_events: int = Field(description="NSF / overdraft event count")
    discretionary_spending_ratio: float
    rent_to_income_ratio: float
    cash_buffer_days: float = Field(description="Days of expenses covered by avg balance")
    months_analyzed: int


# ── Risk Assessment ────────────────────────────────────────────────────────────

class RiskFactor(BaseModel):
    """A single risk factor or strength with citations."""

    description: str
    severity: Literal["low", "medium", "high"]
    citations: list[str] = Field(
        description="transaction_ids supporting this claim, format: tx:abc123"
    )


class RiskAssessment(BaseModel):
    """
    Structured output from the Risk Analyst LangGraph node.
    Every claim must cite source transaction_ids — no hallucination allowed.
    """

    risk_score: int = Field(ge=0, le=100, description="0=lowest risk, 100=highest")
    recommendation: Literal["approve", "approve_with_conditions", "decline", "manual_review"]
    risk_factors: list[RiskFactor]
    strengths: list[RiskFactor]
    confidence: float = Field(ge=0.0, le=1.0)
    insufficient_data_areas: list[str] = Field(default_factory=list)
    reasoning_summary: str = Field(description="1-2 sentence plain-English summary")


# ── Validation ─────────────────────────────────────────────────────────────────

class CitationCheck(BaseModel):
    """Result of validating a single citation."""

    transaction_id: str
    found: bool
    claim_supported: bool
    reason: str | None = None


class ValidationResult(BaseModel):
    """Output of the Validator node."""

    overall_validity: float = Field(ge=0.0, le=1.0)
    citation_checks: list[CitationCheck]
    hallucinated_claims: list[str]
    passed: bool  # True if overall_validity >= 0.85
    feedback_for_risk_analyst: str | None = None  # Set if passed=False


# ── Workflow State ─────────────────────────────────────────────────────────────

class WorkflowState(BaseModel):
    """LangGraph state passed between all nodes."""

    user_id: str
    loan_amount: float
    loan_purpose: str | None = None

    # Populated as pipeline progresses
    raw_transactions: list[Transaction] = Field(default_factory=list)
    transactions: list[CategorizedTransaction] = Field(default_factory=list)
    metrics: CashFlowMetrics | None = None
    risk_assessment: RiskAssessment | None = None
    validation_result: ValidationResult | None = None
    escalate_to_human: bool = False
    escalation_reasons: list[str] = Field(default_factory=list)
    retry_count: int = 0
    final_report_path: str | None = None
    final_report_pdf_path: str | None = None
    run_id: str | None = None
