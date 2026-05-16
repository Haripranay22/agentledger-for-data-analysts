"""
LangGraph nodes — each function is one step in the credit analysis pipeline.

Node execution order (see graph.py for wiring):
  ingest → profile → categorize → analyze → risk_assess → validate → hitl_check → report
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from agentledger.analysis.cash_flow import compute_metrics
from agentledger.prompts.risk_analyst import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from agentledger.schemas.models import (
    CitationCheck,
    RiskAssessment,
    ValidationResult,
    WorkflowState,
)

logger = logging.getLogger(__name__)


def ingest_node(state: WorkflowState, context: dict[str, Any] | None = None) -> WorkflowState:
    """
    Pull transactions from Plaid sandbox.
    Writes: state.raw_transactions (plain Transaction objects, no categorization yet).
    """
    from agentledger.connectors.plaid_client import PlaidClient

    state.run_id = str(uuid.uuid4())
    logger.info("[ingest] run_id=%s | user=%s", state.run_id, state.user_id)

    client_id = os.environ.get("PLAID_CLIENT_ID")
    secret = os.environ.get("PLAID_SECRET")
    if not client_id or not secret:
        raise RuntimeError("PLAID_CLIENT_ID and PLAID_SECRET must be set in .env")

    # Access token: caller passes via context, or fall back to env var
    ctx = context or {}
    access_token = (
        ctx.get("access_token")
        or os.environ.get(f"PLAID_ACCESS_TOKEN_{state.user_id.upper()}")
        or os.environ.get("PLAID_ACCESS_TOKEN")
    )
    if not access_token:
        raise RuntimeError(
            f"No Plaid access_token for user={state.user_id}. "
            "Set PLAID_ACCESS_TOKEN in .env or pass via context['access_token']."
        )

    plaid_env = os.environ.get("PLAID_ENV", "sandbox")
    client = PlaidClient(client_id=client_id, secret=secret, env=plaid_env)
    state.raw_transactions = client.get_transactions(
        access_token=access_token,
        user_id=state.user_id,
        months=int(os.environ.get("PLAID_MONTHS", "6")),
    )
    logger.info("[ingest] Pulled %d raw transactions", len(state.raw_transactions))
    return state


def profile_node(state: WorkflowState, context: dict[str, Any] | None = None) -> WorkflowState:
    """
    Data quality gate: drops malformed transactions before they reach the ML layer.
    Writes: state.raw_transactions (filtered — same type, fewer rows).
    """
    today = date.today()
    original = len(state.raw_transactions)
    passed = []

    for txn in state.raw_transactions:
        issues = []
        if not txn.description.strip():
            issues.append("empty description")
        if not txn.account_id.strip():
            issues.append("empty account_id")
        if txn.transaction_date > today:
            issues.append(f"future-dated ({txn.transaction_date})")

        if issues:
            logger.warning(
                "[profile] DROP tx=%s | %s", txn.transaction_id, "; ".join(issues)
            )
        else:
            if abs(txn.amount) > 50_000:
                logger.warning(
                    "[profile] SUSPICIOUS tx=%s | amount=%.2f — keeping but flagged",
                    txn.transaction_id, txn.amount,
                )
            passed.append(txn)

    state.raw_transactions = passed
    dropped = original - len(passed)
    logger.info(
        "[profile] DQ complete | passed=%d / original=%d | dropped=%d (%.1f%% pass rate)",
        len(passed), original, dropped,
        100.0 * len(passed) / max(original, 1),
    )
    return state


def categorize_node(state: WorkflowState, context: dict[str, Any] | None = None) -> WorkflowState:
    """
    Hybrid ML + LLM categorization.
    Reads:  state.raw_transactions (plain Transaction objects from profile_node).
    Writes: state.transactions (CategorizedTransaction objects).
    ML model handles ~90% of cases; LLM fallback for confidence < 0.70.
    """
    from agentledger.ml.categorizer import TransactionCategorizer

    if not state.raw_transactions:
        logger.warning("[categorize] No raw transactions to categorize — skipping")
        return state

    ctx = context or {}
    model_path = Path(
        ctx.get("model_path")
        or os.environ.get("CATEGORIZER_MODEL_PATH", "models/categorizer.pkl")
    )
    if not model_path.exists():
        raise RuntimeError(
            f"Categorizer model not found at {model_path}. "
            "Run: python scripts/train_categorizer.py"
        )

    categorizer = TransactionCategorizer(model_path=model_path)
    state.transactions = categorizer.categorize(
        state.raw_transactions,
        llm_fallback_fn=_build_llm_category_fallback(),
    )
    logger.info("[categorize] %d transactions categorized", len(state.transactions))
    return state


def _build_llm_category_fallback():
    """
    Returns a function: Transaction → category_str.
    Used by TransactionCategorizer when ML confidence < 0.70.
    Calls Groq with a minimal prompt — no Pydantic overhead needed here.
    """
    import os
    from agentledger.ml.categorizer import CATEGORIES

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logger.warning("[categorize] GROQ_API_KEY not set — LLM fallback disabled")
        return None

    try:
        from groq import Groq
        groq_client = Groq(api_key=api_key)
        model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        categories_str = ", ".join(CATEGORIES)
    except ImportError:
        return None

    def fallback(txn) -> str:
        prompt = (
            f"Classify this bank transaction into exactly one category.\n"
            f"Merchant: {txn.merchant_name or ''}\n"
            f"Description: {txn.description}\n"
            f"Amount: {txn.amount}\n\n"
            f"Categories: {categories_str}\n\n"
            f"Reply with only the category name, nothing else."
        )
        response = groq_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
            temperature=0,
        )
        raw = response.choices[0].message.content.strip().lower().replace(" ", "_")
        return raw if raw in CATEGORIES else "other"

    return fallback


def analyze_node(state: WorkflowState, context: dict[str, Any] | None = None) -> WorkflowState:
    """
    Compute 8 cash-flow metrics deterministically.
    MUST match dbt SQL output before proceeding.
    """
    logger.info("[analyze] Computing cash flow metrics for user=%s", state.user_id)
    if state.transactions:
        state.metrics = compute_metrics(state.user_id, state.transactions)
    return state


def _build_llm_client() -> Any:
    """Create an Instructor-patched Groq client for structured LLM output."""
    import instructor
    from groq import Groq

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable not set")

    return instructor.from_groq(
        Groq(api_key=api_key),
        mode=instructor.Mode.JSON,
    )


def risk_assess_node(state: WorkflowState, context: dict[str, Any] | None = None) -> WorkflowState:
    """
    LLM risk analysis (Gemini).
    Receives pre-computed metrics — never asked to do math.
    Forces citations: every claim must reference transaction_ids.
    """
    logger.info("[risk_assess] Running LLM risk analysis | retry=%d", state.retry_count)

    if state.metrics is None:
        raise RuntimeError("metrics must be computed before risk_assess_node")

    # Slim transaction records — only fields the analyst needs to cite
    txn_records = [
        {
            "transaction_id": t.transaction_id,
            "date": t.transaction_date.isoformat(),
            "amount": t.amount,
            "merchant": t.merchant_name or t.description,
            "category": t.our_category,
            "is_income": t.is_income,
            "is_recurring": t.is_recurring,
        }
        for t in state.transactions
    ]

    validator_feedback = ""
    if state.validation_result and state.validation_result.feedback_for_risk_analyst:
        validator_feedback = (
            f"PREVIOUS ATTEMPT FAILED VALIDATION:\n"
            f"{state.validation_result.feedback_for_risk_analyst}"
        )

    user_prompt = USER_PROMPT_TEMPLATE.format(
        user_id=state.user_id,
        loan_amount=state.loan_amount,
        loan_purpose=state.loan_purpose or "General",
        avg_monthly_income=state.metrics.avg_monthly_income,
        income_cv=state.metrics.income_cv,
        avg_monthly_expenses=state.metrics.avg_monthly_expenses,
        dti_ratio=state.metrics.dti_ratio,
        total_nsf_events=state.metrics.total_nsf_events,
        discretionary_spending_ratio=state.metrics.discretionary_spending_ratio,
        rent_to_income_ratio=state.metrics.rent_to_income_ratio,
        cash_buffer_days=state.metrics.cash_buffer_days,
        months_analyzed=state.metrics.months_analyzed,
        transactions_json=json.dumps(txn_records, indent=2),
        validator_feedback=validator_feedback,
    )

    client = _build_llm_client()
    t0 = time.perf_counter()
    risk_assessment: RiskAssessment = client.chat.completions.create(
        response_model=RiskAssessment,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        max_retries=2,
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    state.risk_assessment = risk_assessment
    logger.info(
        "[risk_assess] score=%d | rec=%s | confidence=%.2f | latency=%.0fms",
        risk_assessment.risk_score,
        risk_assessment.recommendation,
        risk_assessment.confidence,
        latency_ms,
    )
    return state


def validate_node(state: WorkflowState, context: dict[str, Any] | None = None) -> WorkflowState:
    """
    Verify every LLM claim against source data.
    Routes back to risk_assess_node if overall_validity < 0.85.
    """
    logger.info("[validate] Checking citations for risk assessment")

    if state.risk_assessment is None:
        return state

    valid_ids = {t.transaction_id for t in state.transactions}
    all_checks: list[CitationCheck] = []
    hallucinated: list[str] = []

    all_factors = state.risk_assessment.risk_factors + state.risk_assessment.strengths
    for factor in all_factors:
        for citation in factor.citations:
            # Strip "tx:" prefix if present
            raw_id = citation.replace("tx:", "").strip()
            found = raw_id in valid_ids
            if not found:
                hallucinated.append(citation)
            all_checks.append(CitationCheck(
                transaction_id=raw_id,
                found=found,
                claim_supported=found,
                reason=None if found else f"Transaction {raw_id!r} not in source data",
            ))

    if not all_checks:
        # No citations produced at all — fail so the LLM retries with explicit instruction
        overall_validity = 0.0
    else:
        overall_validity = sum(1 for c in all_checks if c.found) / len(all_checks)

    passed = overall_validity >= 0.85

    feedback = None
    if not passed:
        bad = [c.transaction_id for c in all_checks if not c.found]
        feedback = (
            f"Validation failed (validity={overall_validity:.0%}). "
            f"{len(bad)} citation(s) reference unknown transaction_ids: "
            f"{', '.join(bad[:10])}. "
            "Revise your assessment using ONLY transaction_ids present in the provided data."
        )

    state.validation_result = ValidationResult(
        overall_validity=round(overall_validity, 4),
        citation_checks=all_checks,
        hallucinated_claims=hallucinated,
        passed=passed,
        feedback_for_risk_analyst=feedback,
    )

    logger.info(
        "[validate] validity=%.2f | passed=%s | hallucinated=%d",
        overall_validity,
        passed,
        len(hallucinated),
    )
    return state


def hitl_check_node(state: WorkflowState, context: dict[str, Any] | None = None) -> WorkflowState:
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


def report_node(state: WorkflowState, context: dict[str, Any] | None = None) -> WorkflowState:
    """Generate Markdown credit memo + audit log."""
    from pathlib import Path

    from agentledger.reporting.memo_generator import MemoGenerator

    logger.info("[report] Generating credit memo for user=%s", state.user_id)

    if state.risk_assessment is None or state.metrics is None:
        logger.warning("[report] Missing assessment or metrics — skipping memo generation")
        return state

    output_dir = Path("reports") / state.user_id
    path = MemoGenerator().save(state, output_dir)
    state.final_report_path = str(path)
    logger.info("[report] Memo written: %s", path)
    return state
