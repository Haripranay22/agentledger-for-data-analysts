"""
AgentLedger CLI.

Usage:
  agentledger analyze --user-id USER_001 --loan-amount 5000
  agentledger eval --scenario-dir evals/scenarios/
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def _run_analyze(args: argparse.Namespace) -> None:
    from dotenv import load_dotenv
    load_dotenv()

    from agentledger.schemas.models import WorkflowState
    from agentledger.workflow.graph import credit_analysis_graph

    print(f"[AgentLedger] Analyzing borrower={args.user_id} loan=${args.loan_amount:,.0f}")

    initial_state = WorkflowState(
        user_id=args.user_id,
        loan_amount=args.loan_amount,
        loan_purpose=args.loan_purpose or "General credit review",
    )

    final_state = WorkflowState(**credit_analysis_graph.invoke(initial_state))

    print(f"\n{'='*60}")
    print(f"USER:     {final_state.user_id}")
    print(f"RUN ID:   {final_state.run_id}")
    print(f"LOAN:     ${final_state.loan_amount:,.0f} — {final_state.loan_purpose}")

    if final_state.metrics:
        m = final_state.metrics
        print("\nMETRICS:")
        print(f"  Avg monthly income:   ${m.avg_monthly_income:>10,.2f}")
        print(f"  Avg monthly expenses: ${m.avg_monthly_expenses:>10,.2f}")
        print(f"  DTI ratio:            {m.dti_ratio:>10.1%}")
        print(f"  Income stability CV:  {m.income_cv:>10.3f}")
        print(f"  NSF events:           {m.total_nsf_events:>10}")
        print(f"  Cash buffer days:     {m.cash_buffer_days:>10.0f}")
        print(f"  Rent-to-income:       {m.rent_to_income_ratio:>10.1%}")

    if final_state.risk_assessment:
        ra = final_state.risk_assessment
        print("\nRISK ASSESSMENT:")
        print(f"  Score:          {ra.risk_score}/100")
        print(f"  Recommendation: {ra.recommendation.upper()}")
        print(f"  Confidence:     {ra.confidence:.0%}")
        print(f"  Summary:        {ra.reasoning_summary}")

    if final_state.validation_result:
        vr = final_state.validation_result
        print("\nVALIDATION:")
        print(f"  Citation validity:  {vr.overall_validity:.0%}")
        print(f"  Hallucinated claims: {len(vr.hallucinated_claims)}")

    if final_state.escalate_to_human:
        print("\nESCALATED TO HUMAN REVIEW:")
        for reason in (final_state.escalation_reasons or []):
            print(f"  • {reason}")

    if final_state.final_report_path:
        print(f"\nREPORT: {final_state.final_report_path}")

    print(f"{'='*60}")


def _run_eval(args: argparse.Namespace) -> None:
    # Resolve scenario dir relative to cwd so the CLI works from any location
    scenario_dir = str(Path(args.scenario_dir).resolve())
    output = str(Path(args.output).resolve())

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "evals"))
    from evals.runner import main as eval_main  # type: ignore[import]

    eval_main(scenario_dir=scenario_dir, output=output)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AgentLedger — AI-augmented credit analysis"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # analyze command
    analyze = subparsers.add_parser("analyze", help="Run full credit analysis on a borrower")
    analyze.add_argument("--user-id", required=True)
    analyze.add_argument("--loan-amount", type=float, required=True)
    analyze.add_argument("--loan-purpose", default=None)
    analyze.add_argument("--output-dir", default="output/memos")

    # eval command
    eval_cmd = subparsers.add_parser("eval", help="Run evaluation harness")
    eval_cmd.add_argument("--scenario-dir", default="evals/scenarios")
    eval_cmd.add_argument("--output", default="evals/reports/latest.json")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    if args.command == "analyze":
        _run_analyze(args)
    elif args.command == "eval":
        _run_eval(args)


if __name__ == "__main__":
    main()
