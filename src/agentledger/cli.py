"""
AgentLedger CLI.

Usage:
  agentledger analyze --user-id USER_001 --loan-amount 5000
  agentledger eval --scenario-dir evals/scenarios/
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


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
    analyze.add_argument("--output-dir", default="reports")

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


def _run_analyze(args: argparse.Namespace) -> None:
    from dotenv import load_dotenv
    load_dotenv()

    print(f"[AgentLedger] Analyzing borrower={args.user_id} loan=${args.loan_amount:,.0f}")

    from typing import cast

    from agentledger.schemas.models import WorkflowState
    from agentledger.workflow.graph import credit_analysis_graph

    initial_state = WorkflowState(
        user_id=args.user_id,
        loan_amount=args.loan_amount,
        loan_purpose=args.loan_purpose,
    )

    try:
        final_state = cast(WorkflowState, credit_analysis_graph.invoke(initial_state))
    except Exception as exc:
        print(f"[AgentLedger] Pipeline failed: {exc}", file=sys.stderr)
        sys.exit(1)

    # Persist state as JSON so the dashboard can load it
    output_dir = Path(args.output_dir) / args.user_id
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / f"state_{(final_state.run_id or 'unknown')[:8]}.json"
    state_path.write_text(
        json.dumps(final_state.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )

    ra = final_state.risk_assessment
    if ra:
        print(f"\n{'='*60}")
        print(f"  Decision:    {ra.recommendation.upper().replace('_', ' ')}")
        print(f"  Risk Score:  {ra.risk_score}/100")
        print(f"  Confidence:  {ra.confidence:.0%}")
        print(f"  Summary:     {ra.reasoning_summary}")
        print(f"{'='*60}")

    if final_state.final_report_path:
        print(f"\n  Memo:        {final_state.final_report_path}")
    print(f"  State JSON:  {state_path}")

    if final_state.escalate_to_human:
        print(f"\n  ⚠  Escalated: {'; '.join(final_state.escalation_reasons)}")


def _run_eval(args: argparse.Namespace) -> None:
    from dotenv import load_dotenv
    load_dotenv()

    print(f"[AgentLedger] Running evals from {args.scenario_dir}")

    # Add project root to path so evals/runner.py can be imported
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

    try:
        from evals.runner import main as eval_main  # type: ignore[import]
    except ImportError as exc:
        print(f"[AgentLedger] Could not import eval runner: {exc}", file=sys.stderr)
        sys.exit(1)

    eval_main(
        scenario_dir=args.scenario_dir,
        output=args.output,
    )


if __name__ == "__main__":
    main()
