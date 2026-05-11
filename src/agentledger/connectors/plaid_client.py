"""
Plaid sandbox client wrapper.

Pulls transaction history for synthetic borrower personas.
Raw JSON is persisted to S3 before any transformation.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any

import plaid
from plaid.api import plaid_api
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions

from agentledger.schemas.models import Transaction

logger = logging.getLogger(__name__)


class PlaidClient:
    """
    Thin wrapper around the Plaid API.

    Isolates all Plaid-specific logic so the rest of the codebase
    is unaffected if Plaid changes their API.
    """

    def __init__(self, client_id: str, secret: str, env: str = "sandbox") -> None:
        configuration = plaid.Configuration(
            host=plaid.Environment.Sandbox if env == "sandbox" else plaid.Environment.Production,
            api_key={"clientId": client_id, "secret": secret},
        )
        api_client = plaid.ApiClient(configuration)
        self._client = plaid_api.PlaidApi(api_client)
        logger.info("PlaidClient initialized for env=%s", env)

    def get_transactions(
        self,
        access_token: str,
        user_id: str,
        months: int = 6,
    ) -> list[Transaction]:
        """
        Pull transaction history for a given access token.

        Args:
            access_token: Plaid access token for the user.
            user_id: Our internal user identifier.
            months: How many months of history to pull.

        Returns:
            List of Transaction objects ready for the warehouse.
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=30 * months)

        request = TransactionsGetRequest(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date,
            options=TransactionsGetRequestOptions(count=500, offset=0),
        )

        response = self._client.transactions_get(request)
        transactions = response["transactions"]

        logger.info(
            "Pulled %d transactions for user=%s (%s to %s)",
            len(transactions),
            user_id,
            start_date,
            end_date,
        )

        return [self._map_transaction(t, user_id) for t in transactions]

    def _map_transaction(self, raw: Any, user_id: str) -> Transaction:
        """Map Plaid transaction dict to our Transaction schema."""
        return Transaction(
            transaction_id=raw["transaction_id"],
            account_id=raw["account_id"],
            user_id=user_id,
            transaction_date=raw["date"],
            amount=raw["amount"],
            merchant_name=raw.get("merchant_name"),
            description=raw.get("name", ""),
            plaid_category=raw.get("category") or [],
            pending=raw.get("pending", False),
        )

    def get_raw_json(self, access_token: str, months: int = 6) -> dict[str, Any]:
        """Return raw Plaid response for archiving to S3."""
        end_date = date.today()
        start_date = end_date - timedelta(days=30 * months)
        request = TransactionsGetRequest(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date,
        )
        response = self._client.transactions_get(request)
        return dict(response)
