"""
Database persistence layer.

Writes completed pipeline runs to PostgreSQL.
Called once at the end of report_node — one function, no ORM.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import TYPE_CHECKING

import psycopg2
import psycopg2.extras

if TYPE_CHECKING:
    from agentledger.schemas.models import WorkflowState

logger = logging.getLogger(__name__)


def _get_conn() -> psycopg2.connection:  # type: ignore[name-defined]
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set in .env")
    return psycopg2.connect(url)


def save_run(state: WorkflowState) -> None:
    """Persist a completed pipeline run and all related records to Postgres."""
    if not state.run_id:
        logger.warning("[db] No run_id on state — skipping persist")
        return

    run_id = uuid.UUID(state.run_id) if len(state.run_id) == 36 else uuid.uuid4()
    m = state.metrics
    ra = state.risk_assessment
    vr = state.validation_result

    try:
        conn = _get_conn()
        conn.autocommit = False
        cur = conn.cursor()

        # ── runs ──────────────────────────────────────────────────────────────
        cur.execute(
            """
            INSERT INTO runs (
                run_id, user_id, loan_amount, loan_purpose,
                avg_monthly_income, avg_monthly_expenses, income_cv,
                dti_ratio, total_nsf_events, discretionary_spending_ratio,
                rent_to_income_ratio, cash_buffer_days, months_analyzed,
                risk_score, recommendation, confidence, reasoning_summary, model_used,
                citation_validity, validation_passed,
                escalated_to_human, escalation_reasons,
                report_path, report_pdf_path
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s
            )
            ON CONFLICT (run_id) DO NOTHING
            """,
            (
                str(run_id), state.user_id, state.loan_amount, state.loan_purpose,
                m.avg_monthly_income if m else None,
                m.avg_monthly_expenses if m else None,
                m.income_cv if m else None,
                m.dti_ratio if m else None,
                m.total_nsf_events if m else None,
                m.discretionary_spending_ratio if m else None,
                m.rent_to_income_ratio if m else None,
                m.cash_buffer_days if m else None,
                m.months_analyzed if m else None,
                ra.risk_score if ra else None,
                ra.recommendation if ra else None,
                ra.confidence if ra else None,
                ra.reasoning_summary if ra else None,
                os.environ.get("OPENROUTER_MODEL"),
                vr.overall_validity if vr else None,
                vr.passed if vr else None,
                state.escalate_to_human,
                state.escalation_reasons or [],
                state.final_report_path,
                state.final_report_pdf_path,
            ),
        )

        # ── transactions ──────────────────────────────────────────────────────
        if state.transactions:
            psycopg2.extras.execute_batch(
                cur,
                """
                INSERT INTO transactions (
                    run_id, transaction_id, account_id, user_id,
                    transaction_date, amount, merchant_name, description,
                    our_category, confidence_score,
                    is_income, is_recurring, is_essential, categorization_source
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                [
                    (
                        str(run_id), t.transaction_id, t.account_id, t.user_id,
                        t.transaction_date, t.amount, t.merchant_name, t.description,
                        t.our_category, t.confidence_score,
                        t.is_income, t.is_recurring, t.is_essential,
                        t.categorization_source,
                    )
                    for t in state.transactions
                ],
            )

        # ── risk_factors + strengths ──────────────────────────────────────────
        if ra:
            factors = (
                [("risk", f) for f in ra.risk_factors] +
                [("strength", f) for f in ra.strengths]
            )
            if factors:
                psycopg2.extras.execute_batch(
                    cur,
                    """
                    INSERT INTO risk_factors (run_id, factor_type, severity, description, citations)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    [
                        (str(run_id), ftype, f.severity, f.description, f.citations)
                        for ftype, f in factors
                    ],
                )

        # ── citation_checks ───────────────────────────────────────────────────
        if vr and vr.citation_checks:
            psycopg2.extras.execute_batch(
                cur,
                """
                INSERT INTO citation_checks (run_id, transaction_id, found, claim_supported, reason)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    (str(run_id), c.transaction_id, c.found, c.claim_supported, c.reason)
                    for c in vr.citation_checks
                ],
            )

        conn.commit()
        logger.info("[db] Run persisted | run_id=%s | user=%s", run_id, state.user_id)

    except Exception:
        logger.exception("[db] Failed to persist run — pipeline result still valid")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass
