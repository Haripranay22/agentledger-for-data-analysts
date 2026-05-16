"""
One-time script: generate a Plaid sandbox access token.

Run:
    cd agentledger/
    python scripts/get_sandbox_token.py

Copy the printed access-token into .env as:
    PLAID_ACCESS_TOKEN=access-sandbox-...
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

import os
from agentledger.connectors.plaid_client import PlaidClient

client_id = os.environ["PLAID_CLIENT_ID"]
secret = os.environ["PLAID_SECRET"]

client = PlaidClient(client_id=client_id, secret=secret, env="sandbox")
token = client.create_sandbox_access_token()

print("\n" + "=" * 60)
print("Add this line to your .env file:")
print(f"PLAID_ACCESS_TOKEN={token}")
print("=" * 60)
