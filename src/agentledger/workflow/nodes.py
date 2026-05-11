"""
LangGraph nodes — each function is one step in the credit analysis pipeline.

Node execution order (see graph.py for wiring):
  ingest → profile → categorize → analyze → risk_assess → validate → hitl_check → report

Interview talking point:
  "LangGraph gives stateful control — I can loop the validator back to the
   risk analyst with specific feedback, which you can't do cleanly with a simple chain."
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from agentledger.analysis.cash_flow import compute_metrics
from agentledger.schemas.models import (
    RiskAssessment,
    ValidationResult,
    WorkflowState,
)

logger = logging.getLogger(__name__)


def ingest_node(state: WorkflowState, context: dict[str, Any]) -> WorkflowState:
    """
    Pull transactions from Plaid and persist raw JSON to S3.
    Populated: state.transactions (pre-categorization)
    """
    logger.info("[ingest] Starting for user=%s", state.user_id)
    # TODO Week 1: wire up PlaidClient + S3 persistence
    state.run_id = str(uuid.uuid4())
    return state


def profile_node(state: WorkflowState, context: dict[str, Any]) -> WorkflowState:
    """
    Data quality checks + schema validation.
    Rejects malformed transactions before they reach the ML layer.
    """
    logger.info("[profile] Running DQ checks on %d transactions", len(state.transactions))
    # TODO Week 1: implement DQ checks (null fields, future dates, amount bounds)
    return state


def categorize_node(state: WorkflowState, context: dict[str, Any]) -> WorkflowState:
    """
    Hybrid ML + LLM categorization.
    ML model handles 90%+ of cases; LLM fallback for confidence < 0.70.
    """
    logger.info("[categorize] Categorizing %d transactions", len(state.transactions))
    # TODO Week 1: wire up TransactionCategorizer
    return state


def analyze_node(state: WorkflowState, context: dict[str, Any]) -> WorkflowState:
    """
    Compute 8 cash-flow metrics deterministically.
    MUST match dbt SQL output before proceeding.
    """
    logger.info("[analyze] Computing cash flow metrics for user=%s", state.user_id)
    if state.transactions:
        state.metrics = compute_metrics(state.user_id, state.transactions)
    return state


def risk_assess_node(state: WorkflowState, context: dict[str, Any]) -> WorkflowState:
    """
    LLM risk analysis (Gemini).
    Receives pre-computed metrics — never asked to do math.
    Forces citations: every claim must reference transaction_ids.
    """
    logger.info("[risk_assess] Running LLM risk analysis | retry=%d", state.retry_count)
    # TODO Week 2: implement via Google AI API + Instructor + Pydantic schema
    return state


def validate_node(state: WorkflowState, context: dict[str, Any]) -> WorkflowState:
    """
    Verify every LLM claim against source data.
    Routes back to risk_assess_node if overall_validity < 0.85.
    """
    logger.info("[validate] Checking citations for risk assessment")
    # TODO Week 2: implement citation checker
    return state


def hitl_check_node(state: WorkflowState, context: dict[str, Any]) -> WorkflowState:
    """
    Rules-based escalation to human analyst.
    Escalation triggers: confidence < 0.6, validator rejected > 2 claims,
    risk score 40-60, insufficient data, new merchant patterns.
    """
    if state.risk_assessment is None:
        return state

    reasons = []
    ra = state.risk_assessment

    if ra.confidence < 0.6:
        reasons.append(f"Low confidence: {ra.confidence:.2f}")
    if 40 <= ra.risk_score <= 60:
        reasons.append(f"Ambiguous risk score: {ra.risk_score}")
    if ra.insufficient_data_areas:
        reasons.append(f"Insufficient data: {', '.join(ra.insufficient_data_areas)}")
    if state.validation_result and not state.validation_result.passed:
        reasons.append("Validation failed after max retries")

    state.escalate_to_human = len(reasons) > 0
    state.escalation_reasons = reasons

    if state.escalate_to_human:
        logger.warning("[hitl] Escalating to human | reasons=%s", reasons)
    else:
        logger.info("[hitl] No escalation needed")

    return state


def report_node(state: WorkflowState, context: dict[str, Any]) -> WorkflowState:
    """
    Generate Markdown credit memo + PDF + audit log.
    """
    logger.info("[report] Generating credit memo for user=%s", state.user_id)
    # TODO Week 3: implement Jinja2 template + WeasyPrint PDF
    return state
