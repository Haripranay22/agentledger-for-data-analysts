"""Unit tests for the Langfuse observability tracer."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clear_tracer_module() -> None:
    """Force reimport of tracer so _langfuse_enabled resets between tests."""
    sys.modules.pop("agentledger.observability.tracer", None)


# ── build_llm_client — no Langfuse configured ─────────────────────────────────

def test_build_llm_client_no_langfuse_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_tracer_module()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    mock_instructor = MagicMock()
    mock_instructor.from_openai.return_value = MagicMock()
    mock_openai = MagicMock()

    with patch.dict(sys.modules, {"instructor": mock_instructor, "openai": mock_openai}):
        from agentledger.observability.tracer import build_llm_client
        client = build_llm_client()

    mock_instructor.from_openai.assert_called_once()
    assert client is not None


def test_build_llm_client_raises_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_tracer_module()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    mock_instructor = MagicMock()
    mock_openai = MagicMock()

    with patch.dict(sys.modules, {"instructor": mock_instructor, "openai": mock_openai}):
        from agentledger.observability.tracer import build_llm_client
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            build_llm_client()


def test_build_llm_client_langfuse_keys_but_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_tracer_module()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")

    mock_instructor = MagicMock()
    mock_instructor.from_openai.return_value = MagicMock()
    mock_openai = MagicMock()

    # langfuse not installed → ImportError when trying to use it
    with patch.dict(sys.modules, {
        "instructor": mock_instructor,
        "openai": mock_openai,
        "langfuse": None,
        "langfuse.openai": None,
    }):
        from agentledger.observability.tracer import build_llm_client
        client = build_llm_client()

    # Should fall back to plain OpenAI + instructor
    mock_instructor.from_openai.assert_called_once()
    assert client is not None


def test_build_llm_client_langfuse_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_tracer_module()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")

    mock_instructor = MagicMock()
    mock_instructor.from_openai.return_value = MagicMock()

    mock_langfuse_openai_mod = MagicMock()
    mock_langfuse_openai_mod.OpenAI = MagicMock(return_value=MagicMock())

    with patch.dict(sys.modules, {
        "instructor": mock_instructor,
        "langfuse.openai": mock_langfuse_openai_mod,
    }):
        from agentledger.observability.tracer import build_llm_client
        client = build_llm_client()

    mock_langfuse_openai_mod.OpenAI.assert_called_once_with(api_key="sk-test")
    mock_instructor.from_openai.assert_called_once()
    assert client is not None


# ── flush_traces ───────────────────────────────────────────────────────────────

def test_flush_traces_no_op_when_langfuse_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_tracer_module()
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    # Should not raise even if langfuse is not installed
    from agentledger.observability.tracer import flush_traces
    flush_traces()  # no-op
