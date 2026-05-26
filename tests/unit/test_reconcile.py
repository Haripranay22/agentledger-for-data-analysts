"""Unit tests for the Python ↔ dbt metrics reconciliation assertion."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agentledger.analysis.reconcile import assert_metrics_match
from agentledger.schemas.models import CashFlowMetrics

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _metrics(**overrides: float | int) -> CashFlowMetrics:
    base: dict = {
        "user_id": "u_test",
        "avg_monthly_income": 5000.00,
        "income_cv": 0.1200,
        "avg_monthly_expenses": 3500.00,
        "dti_ratio": 0.2800,
        "total_nsf_events": 1,
        "discretionary_spending_ratio": 0.3500,
        "rent_to_income_ratio": 0.2000,
        "cash_buffer_days": 12.9,
        "months_analyzed": 6,
    }
    base.update(overrides)
    return CashFlowMetrics(**base)


def _sql_row(**overrides: float | int) -> dict:
    base = {
        "avg_monthly_income": 5000.00,
        "income_cv": 0.1200,
        "avg_monthly_expenses": 3500.00,
        "dti_ratio": 0.2800,
        "total_nsf_events": 1,
        "discretionary_spending_ratio": 0.3500,
        "rent_to_income_ratio": 0.2000,
        "cash_buffer_days": 12.9,
        "months_analyzed": 6,
    }
    base.update(overrides)
    return base


# ── Skipping behavior ─────────────────────────────────────────────────────────

def test_skips_when_no_db_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DB_HOST", raising=False)
    result = assert_metrics_match(_metrics())
    assert result.skipped is True
    assert result.passed is True
    assert "No DB" in result.skip_reason


def test_skips_when_db_query_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/fake")
    with patch("agentledger.analysis.reconcile._fetch_dbt_metrics", return_value=None):
        result = assert_metrics_match(_metrics())
    assert result.skipped is True


# ── Matching ──────────────────────────────────────────────────────────────────

def test_passes_when_metrics_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/fake")
    with patch("agentledger.analysis.reconcile._fetch_dbt_metrics", return_value=_sql_row()):
        result = assert_metrics_match(_metrics())
    assert result.skipped is False
    assert result.passed is True
    assert result.deviations == {}


def test_passes_with_tiny_float_difference(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/fake")
    # Difference of 0.01 is within _FLOAT_TOLERANCE of 0.02
    sql = _sql_row(avg_monthly_income=5000.01)
    with patch("agentledger.analysis.reconcile._fetch_dbt_metrics", return_value=sql):
        result = assert_metrics_match(_metrics(avg_monthly_income=5000.00))
    assert result.passed is True


# ── Mismatch detection ────────────────────────────────────────────────────────

def test_detects_float_metric_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/fake")
    sql = _sql_row(avg_monthly_income=4800.00)  # $200 off — above tolerance
    with patch("agentledger.analysis.reconcile._fetch_dbt_metrics", return_value=sql):
        result = assert_metrics_match(_metrics(avg_monthly_income=5000.00))
    assert result.passed is False
    assert "avg_monthly_income" in result.deviations
    assert result.deviations["avg_monthly_income"] == (5000.00, 4800.00)


def test_detects_int_metric_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/fake")
    sql = _sql_row(total_nsf_events=3)
    with patch("agentledger.analysis.reconcile._fetch_dbt_metrics", return_value=sql):
        result = assert_metrics_match(_metrics(total_nsf_events=1))
    assert result.passed is False
    assert "total_nsf_events" in result.deviations


def test_detects_multiple_deviations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/fake")
    sql = _sql_row(dti_ratio=0.50, rent_to_income_ratio=0.40)
    with patch("agentledger.analysis.reconcile._fetch_dbt_metrics", return_value=sql):
        result = assert_metrics_match(_metrics(dti_ratio=0.28, rent_to_income_ratio=0.20))
    assert result.passed is False
    assert len(result.deviations) == 2


# ── RECONCILE_STRICT mode ─────────────────────────────────────────────────────

def test_strict_mode_raises_on_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/fake")
    monkeypatch.setenv("RECONCILE_STRICT", "1")
    sql = _sql_row(avg_monthly_income=4000.00)
    with patch("agentledger.analysis.reconcile._fetch_dbt_metrics", return_value=sql):
        with pytest.raises(RuntimeError, match="MISMATCH"):
            assert_metrics_match(_metrics(avg_monthly_income=5000.00))


def test_non_strict_mode_logs_warning_not_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/fake")
    monkeypatch.delenv("RECONCILE_STRICT", raising=False)
    sql = _sql_row(avg_monthly_income=4000.00)
    with patch("agentledger.analysis.reconcile._fetch_dbt_metrics", return_value=sql):
        result = assert_metrics_match(_metrics(avg_monthly_income=5000.00))
    assert result.passed is False  # warning logged, no exception


# ── _build_db_url ─────────────────────────────────────────────────────────────

def test_build_db_url_from_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@host/db")
    from agentledger.analysis.reconcile import _build_db_url
    assert _build_db_url() == "postgresql://user:pw@host/db"


def test_build_db_url_from_components(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "agentledger")
    monkeypatch.setenv("DB_USER", "agentledger")
    monkeypatch.setenv("DB_PASSWORD", "secret")
    from agentledger.analysis.reconcile import _build_db_url
    url = _build_db_url()
    assert url is not None
    assert "localhost" in url
    assert "agentledger" in url


def test_build_db_url_none_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DB_HOST", raising=False)
    from agentledger.analysis.reconcile import _build_db_url
    assert _build_db_url() is None
