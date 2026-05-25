"""
LangGraph state machine wiring.

Compiles all nodes into a directed graph with conditional edges
for the validate → retry → risk_assess loop.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agentledger.schemas.models import WorkflowState
from agentledger.workflow.nodes import (
    analyze_node,
    categorize_node,
    hitl_check_node,
    ingest_node,
    profile_node,
    report_node,
    risk_assess_node,
    validate_node,
)

MAX_RETRIES = 2


def should_retry_or_proceed(state: WorkflowState) -> str:
    """
    Conditional edge after validation.
    Returns 'retry' if validity < 0.85 and retries remain, else 'proceed'.
    """
    vr = state.validation_result
    if vr is None:
        return "proceed"
    if not vr.passed and state.retry_count < MAX_RETRIES:
        state.retry_count += 1
        return "retry"
    return "proceed"


def build_graph() -> CompiledStateGraph:  # type: ignore[type-arg]
    """Compile the full credit analysis workflow graph."""
    graph = StateGraph(WorkflowState)

    # Register nodes
    graph.add_node("ingest", ingest_node)
    graph.add_node("profile", profile_node)
    graph.add_node("categorize", categorize_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("risk_assess", risk_assess_node)
    graph.add_node("validate", validate_node)
    graph.add_node("hitl_check", hitl_check_node)
    graph.add_node("report", report_node)

    # Linear edges
    graph.set_entry_point("ingest")
    graph.add_edge("ingest", "profile")
    graph.add_edge("profile", "categorize")
    graph.add_edge("categorize", "analyze")
    graph.add_edge("analyze", "risk_assess")
    graph.add_edge("risk_assess", "validate")

    # Conditional: validate → retry or proceed
    graph.add_conditional_edges(
        "validate",
        should_retry_or_proceed,
        {"retry": "risk_assess", "proceed": "hitl_check"},
    )

    graph.add_edge("hitl_check", "report")
    graph.add_edge("report", END)

    return graph.compile()


# Singleton — import this to run the pipeline
credit_analysis_graph = build_graph()
