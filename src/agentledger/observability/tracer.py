"""
Opt-in Langfuse observability for LLM calls.

Enabled automatically when LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set.
Requires: pip install agentledger[observability]

When active, every risk_assess_node call is recorded as a Langfuse generation
with: user_id, run_id, model, token counts, latency, and structured output.
When not configured, this module is a no-op — no import cost, no errors.

Usage:
    from agentledger.observability.tracer import build_llm_client, flush_traces
    client = build_llm_client()   # instructor-patched, Langfuse-wrapped if configured
    ...
    flush_traces()                # call before process exit
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_langfuse_enabled: bool = False


def _langfuse_configured() -> bool:
    return bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
    )


def build_llm_client() -> Any:
    """
    Return an instructor-patched OpenAI client.

    If Langfuse is configured and installed, the underlying OpenAI client is
    replaced with langfuse.openai.OpenAI so every chat.completions.create call
    is automatically traced (model, tokens, latency, input/output).
    Falls back to plain openai.OpenAI with a warning if Langfuse is unavailable.
    """
    global _langfuse_enabled
    import instructor

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable not set")

    base_url = os.environ.get("OPENAI_BASE_URL") or None  # e.g. https://openrouter.ai/api/v1

    if _langfuse_configured():
        try:
            from langfuse.openai import OpenAI  # type: ignore[import-untyped]

            _langfuse_enabled = True
            logger.info(
                "Langfuse tracing enabled — traces → %s",
                os.environ.get("LANGFUSE_HOST", "http://localhost:3000"),
            )
            return instructor.from_openai(OpenAI(api_key=api_key, base_url=base_url))
        except ImportError:
            logger.warning(
                "LANGFUSE_PUBLIC_KEY is set but langfuse is not installed. "
                "pip install agentledger[observability]  — falling back to plain OpenAI."
            )
        except Exception as exc:
            logger.warning("Langfuse init failed (%s) — falling back to plain OpenAI.", exc)

    from openai import OpenAI

    _langfuse_enabled = False
    return instructor.from_openai(OpenAI(api_key=api_key, base_url=base_url))


def flush_traces() -> None:
    """
    Flush pending Langfuse traces before process exit.

    Safe to call even when Langfuse is not configured or not installed.
    """
    if not _langfuse_enabled:
        return
    try:
        import langfuse  # type: ignore[import-untyped]

        langfuse.flush()
        logger.debug("Langfuse traces flushed")
    except Exception as exc:
        logger.debug("Langfuse flush skipped: %s", exc)
