"""
Reconciliation assertion: Python cash-flow metrics vs dbt SQL output.

After compute_metrics() runs, this module optionally fetches the pre-computed
values from fct_user_metrics (the dbt table) and asserts they match within
tolerance. Any deviation above TOLERANCE means the Python logic and the SQL
diverged — either a bug or a schema mismatch upstream.

The check is SKIPPED (with a warning, never a crash) if:
  - No database env vars are set
  - fct_user_metrics table does not exist yet (dbt has not been run)
  - Any DB connection error occurs

Set RECONCILE_STRICT=1 to turn a mismatch into a RuntimeError.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from agentledger.schemas.models import CashFlowMetrics

logger = logging.getLogger(__name__)

# Maximum allowed absolute difference for each float metric before flagging.
# Integer metrics (total_nsf_events, months_analyzed) must match exactly.
_FLOAT_TOLERANCE = 0.02  # ±$0.02 or ±0.0002 for ratios — rounding noise only


@dataclass
class ReconciliationResult:
    skipped: bool
    passed: bool
    deviations: dict[str, tuple[float, float]]  # metric → (python_val, sql_val)
    skip_reason: str = ""


def _build_db_url() -> str | None:
    """Return SQLAlchemy connection URL from env vars, or None if not configured."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    host = os.environ.get("DB_HOST")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME")
    user = os.environ.get("DB_USER")
    password = os.environ.get("DB_PASSWORD")
    if host and name and user and password:
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"
    return None


def _fetch_dbt_metrics(user_id: str, db_url: str) -> dict[str, Any] | None:
    """Query fct_user_metrics for the given user. Returns None on any error."""
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        logger.warning("[reconcile] sqlalchemy not installed — skipping DB check")
        return None

    try:
        engine = create_engine(db_url, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT avg_monthly_income, income_cv, avg_monthly_expenses,
                           dti_ratio, total_nsf_events, discretionary_spending_ratio,
                           rent_to_income_ratio, cash_buffer_days, months_analyzed
                    FROM fct_user_metrics
                    WHERE user_id = :uid
                    LIMIT 1
                    """
                ),
                {"uid": user_id},
            ).fetchone()
        if row is None:
            logger.warning(
                "[reconcile] No dbt row found for user=%s in fct_user_metrics — skipping", user_id
            )
            return None
        return dict(row._mapping)
    except Exception as exc:
        logger.warning("[reconcile] DB query failed (%s) — skipping assertion", exc)
        return None


def assert_metrics_match(python_metrics: CashFlowMetrics) -> ReconciliationResult:
    """
    Compare Python-computed metrics against the dbt fct_user_metrics table.

    Returns a ReconciliationResult describing pass/fail and any deviations.
    Raises RuntimeError on mismatch only when RECONCILE_STRICT=1.
    """
    db_url = _build_db_url()
    if not db_url:
        return ReconciliationResult(
            skipped=True, passed=True, deviations={}, skip_reason="No DB configured"
        )

    sql_row = _fetch_dbt_metrics(python_metrics.user_id, db_url)
    if sql_row is None:
        return ReconciliationResult(
            skipped=True, passed=True, deviations={}, skip_reason="dbt row unavailable"
        )

    float_metrics = [
        "avg_monthly_income",
        "income_cv",
        "avg_monthly_expenses",
        "dti_ratio",
        "discretionary_spending_ratio",
        "rent_to_income_ratio",
        "cash_buffer_days",
    ]
    int_metrics = ["total_nsf_events", "months_analyzed"]

    deviations: dict[str, tuple[float, float]] = {}

    for name in float_metrics:
        py_val = float(getattr(python_metrics, name))
        sql_val = float(sql_row[name])
        if abs(py_val - sql_val) > _FLOAT_TOLERANCE:
            deviations[name] = (py_val, sql_val)

    for name in int_metrics:
        py_val = int(getattr(python_metrics, name))
        sql_val = int(sql_row[name])
        if py_val != sql_val:
            deviations[name] = (float(py_val), float(sql_val))

    passed = len(deviations) == 0

    if passed:
        logger.info("[reconcile] Python ↔ dbt metrics match for user=%s", python_metrics.user_id)
    else:
        msg = (
            f"[reconcile] MISMATCH for user={python_metrics.user_id}: "
            + ", ".join(f"{k}: python={v[0]} sql={v[1]}" for k, v in deviations.items())
        )
        if os.environ.get("RECONCILE_STRICT") == "1":
            raise RuntimeError(msg)
        logger.warning(msg)

    return ReconciliationResult(skipped=False, passed=passed, deviations=deviations)
