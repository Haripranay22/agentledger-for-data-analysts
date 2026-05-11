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
        print(f"[AgentLedger] Analyzing borrower={args.user_id} loan=${args.loan_amount:,.0f}")
        # TODO: wire up workflow graph
        print("Pipeline not yet wired — complete Week 1 tasks first.")
    elif args.command == "eval":
        print(f"[AgentLedger] Running evals from {args.scenario_dir}")
        # TODO: wire up eval runner
        print("Eval runner not yet implemented — complete Week 3 tasks first.")


if __name__ == "__main__":
    main()
