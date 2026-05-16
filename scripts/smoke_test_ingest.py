"""
Smoke test: ingest_node → profile_node → categorize_node

Verifies the three new nodes work end-to-end with real Plaid sandbox data.

Usage:
    cd agentledger/
    python scripts/smoke_test_ingest.py
"""

from __future__ import annotations

import logging
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from agentledger.schemas.models import WorkflowState
from agentledger.workflow.nodes import categorize_node, ingest_node, profile_node

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    state = WorkflowState(
        user_id="sandbox_user_01",
        loan_amount=20_000.0,
        loan_purpose="Debt consolidation",
    )

    logger.info("=" * 60)
    logger.info("SMOKE TEST: ingest → profile → categorize")
    logger.info("=" * 60)

    # --- ingest ---
    state = ingest_node(state, {})
    logger.info("After ingest: %d raw transactions", len(state.raw_transactions))

    # --- profile ---
    state = profile_node(state, {})
    logger.info("After profile: %d transactions passed DQ", len(state.raw_transactions))

    # --- categorize ---
    state = categorize_node(state, {})
    logger.info("After categorize: %d categorized transactions", len(state.transactions))

    # Summary
    print("\n" + "=" * 60)
    print(f"Total transactions pulled:     {len(state.raw_transactions)}")
    print(f"Total after categorization:    {len(state.transactions)}")

    category_counts = Counter(t.our_category for t in state.transactions)
    print("\nCategory breakdown:")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:<30} {count:>4}")

    source_counts = Counter(t.categorization_source for t in state.transactions)
    print("\nCategorization source:")
    for src, count in source_counts.items():
        print(f"  {src:<20} {count:>4} ({100*count/len(state.transactions):.0f}%)")

    low_conf = [t for t in state.transactions if t.confidence_score < 0.70]
    print(f"\nLow-confidence transactions:   {len(low_conf)}")

    print("=" * 60)
    print("Ingest pipeline smoke test PASSED")


if __name__ == "__main__":
    main()
