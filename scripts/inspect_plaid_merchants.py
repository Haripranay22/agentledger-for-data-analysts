"""Quick script to print raw Plaid sandbox merchant names."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from dotenv import load_dotenv
load_dotenv()

from agentledger.schemas.models import WorkflowState
from agentledger.workflow.nodes import ingest_node

state = WorkflowState(user_id="sandbox_user_01", loan_amount=20_000.0)
state = ingest_node(state, {})

print(f"{'merchant_name':<35} {'description':<40} {'amount':>10}")
print("-" * 90)
for t in state.raw_transactions:
    print(f"{(t.merchant_name or ''):<35} {t.description:<40} {t.amount:>10.2f}")
