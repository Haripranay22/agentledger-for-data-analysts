"""
Full end-to-end smoke test: all 8 nodes via the compiled LangGraph.

ingest → profile → categorize → analyze → risk_assess → validate → hitl_check → report

This is the first test that runs the complete pipeline on live Plaid sandbox data.

Usage:
    cd agentledger/
    python scripts/smoke_test_full_pipeline.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from agentledger.schemas.models import WorkflowState
from agentledger.workflow.graph import credit_analysis_graph

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def run(user_id: str, loan_amount: float, loan_purpose: str) -> WorkflowState:
    logger.info("=" * 60)
    logger.info("FULL PIPELINE: %s | loan=$%.0f", user_id, loan_amount)
    logger.info("=" * 60)

    initial_state = WorkflowState(
        user_id=user_id,
        loan_amount=loan_amount,
        loan_purpose=loan_purpose,
    )

    final_state = WorkflowState(**credit_analysis_graph.invoke(initial_state))

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"USER:          {final_state.user_id}")
    print(f"RUN ID:        {final_state.run_id}")
    print(f"LOAN:          ${final_state.loan_amount:,.0f} — {final_state.loan_purpose}")

    print(f"\nINGEST:        {len(final_state.raw_transactions)} raw transactions pulled")
    print(f"CATEGORIZE:    {len(final_state.transactions)} transactions categorized")

    if final_state.metrics:
        m = final_state.metrics
        print(f"\nMETRICS:")
        print(f"  Avg monthly income:    ${m.avg_monthly_income:>10,.2f}")
        print(f"  Avg monthly expenses:  ${m.avg_monthly_expenses:>10,.2f}")
        print(f"  DTI ratio:             {m.dti_ratio:>10.1%}")
        print(f"  Income CV:             {m.income_cv:>10.3f}  (lower = more stable)")
        print(f"  NSF events:            {m.total_nsf_events:>10}")
        print(f"  Cash buffer days:      {m.cash_buffer_days:>10.0f}")
        print(f"  Rent-to-income:        {m.rent_to_income_ratio:>10.1%}")
        print(f"  Months analyzed:       {m.months_analyzed:>10}")

    if final_state.risk_assessment:
        ra = final_state.risk_assessment
        print(f"\nRISK ASSESSMENT:")
        print(f"  Score:         {ra.risk_score}/100")
        print(f"  Recommendation:{ra.recommendation.upper()}")
        print(f"  Confidence:    {ra.confidence:.0%}")
        print(f"  Summary:       {ra.reasoning_summary}")

    if final_state.validation_result:
        vr = final_state.validation_result
        print(f"\nVALIDATION:")
        print(f"  Validity:      {vr.overall_validity:.0%}")
        print(f"  Passed:        {vr.passed}")
        print(f"  Hallucinated:  {len(vr.hallucinated_claims)} claims")

    print(f"\nESCALATE:      {final_state.escalate_to_human}")
    if final_state.escalation_reasons:
        for r in final_state.escalation_reasons:
            print(f"  • {r}")

    if final_state.final_report_path:
        print(f"\nREPORT:        {final_state.final_report_path}")

    print("=" * 60)
    return final_state


if __name__ == "__main__":
    run(
        user_id="sandbox_user_01",
        loan_amount=25_000.0,
        loan_purpose="Debt consolidation",
    )
