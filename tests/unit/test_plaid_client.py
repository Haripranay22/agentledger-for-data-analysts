"""Unit tests for PlaidClient — all Plaid API calls are mocked."""

from __future__ import annotations

import sys
from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest  # noqa: E402 (import after sys.modules setup below)

# ── Stub the entire plaid SDK (optional dep, not installed in CI) ──────────────

for _mod in [
    "plaid",
    "plaid.api",
    "plaid.api.plaid_api",
    "plaid.model",
    "plaid.model.item_public_token_exchange_request",
    "plaid.model.products",
    "plaid.model.sandbox_public_token_create_request",
    "plaid.model.transactions_get_request",
    "plaid.model.transactions_get_request_options",
]:
    sys.modules.setdefault(_mod, MagicMock())

from agentledger.connectors.plaid_client import PlaidClient  # noqa: E402,I001


# ── Factory: bypass __init__, inject a mock _client ───────────────────────────

def _make_client() -> PlaidClient:
    """Create a PlaidClient without touching the real plaid SDK."""
    client: PlaidClient = PlaidClient.__new__(PlaidClient)
    client._client = MagicMock()
    return client


def _raw_txn(
    txn_id: str = "txn_001",
    account_id: str = "acc_001",
    amount: float = -45.50,
    txn_date: date = date(2024, 3, 15),
    merchant_name: str | None = "WHOLE FOODS",
    name: str = "Whole Foods Market",
    category: list[str] | None = None,
    pending: bool = False,
) -> dict[str, Any]:
    return {
        "transaction_id": txn_id,
        "account_id": account_id,
        "date": txn_date,
        "amount": amount,
        "merchant_name": merchant_name,
        "name": name,
        "category": category or ["Food and Drink", "Groceries"],
        "pending": pending,
    }


def _api_response(raw_txns: list[dict[str, Any]]) -> MagicMock:
    """Mock Plaid API response that supports response['transactions']."""
    resp = MagicMock()
    resp.__getitem__ = lambda self, k: raw_txns if k == "transactions" else None
    return resp


# ── _map_transaction ───────────────────────────────────────────────────────────

def test_map_transaction_basic_fields():
    client = _make_client()
    txn = client._map_transaction(_raw_txn(), user_id="u1")
    assert txn.transaction_id == "txn_001"
    assert txn.account_id == "acc_001"
    assert txn.user_id == "u1"
    assert txn.amount == -45.50
    assert txn.transaction_date == date(2024, 3, 15)


def test_map_transaction_merchant_name_present():
    client = _make_client()
    txn = client._map_transaction(_raw_txn(merchant_name="STARBUCKS"), user_id="u1")
    assert txn.merchant_name == "STARBUCKS"


def test_map_transaction_merchant_name_none():
    client = _make_client()
    txn = client._map_transaction(_raw_txn(merchant_name=None), user_id="u1")
    assert txn.merchant_name is None


def test_map_transaction_description_from_name():
    client = _make_client()
    txn = client._map_transaction(_raw_txn(name="AMAZON PRIME *ABCDE"), user_id="u1")
    assert txn.description == "AMAZON PRIME *ABCDE"


def test_map_transaction_plaid_category_preserved():
    client = _make_client()
    txn = client._map_transaction(_raw_txn(category=["Transfer", "Debit"]), user_id="u1")
    assert txn.plaid_category == ["Transfer", "Debit"]


def test_map_transaction_category_none_becomes_empty_list():
    client = _make_client()
    raw = _raw_txn()
    raw["category"] = None
    txn = client._map_transaction(raw, user_id="u1")
    assert txn.plaid_category == []


def test_map_transaction_pending_true():
    client = _make_client()
    txn = client._map_transaction(_raw_txn(pending=True), user_id="u1")
    assert txn.pending is True


def test_map_transaction_pending_defaults_false():
    client = _make_client()
    raw = _raw_txn()
    del raw["pending"]
    txn = client._map_transaction(raw, user_id="u1")
    assert txn.pending is False


def test_map_transaction_positive_amount_income():
    client = _make_client()
    txn = client._map_transaction(
        _raw_txn(amount=5000.0, name="PAYROLL DEPOSIT"), user_id="u1"
    )
    assert txn.amount == 5000.0


def test_map_transaction_user_id_assigned():
    client = _make_client()
    txn = client._map_transaction(_raw_txn(), user_id="borrower_99")
    assert txn.user_id == "borrower_99"


# ── get_transactions ───────────────────────────────────────────────────────────

def test_get_transactions_returns_correct_count():
    client = _make_client()
    client._client.transactions_get.return_value = _api_response(
        [_raw_txn("t1"), _raw_txn("t2", amount=-100.0)]
    )
    result = client.get_transactions("access-sandbox-xxx", user_id="u1", months=6)
    assert len(result) == 2


def test_get_transactions_maps_user_id():
    client = _make_client()
    client._client.transactions_get.return_value = _api_response(
        [_raw_txn("txn_007", merchant_name="NETFLIX")]
    )
    result = client.get_transactions("tok", user_id="usr_42")
    assert result[0].user_id == "usr_42"
    assert result[0].merchant_name == "NETFLIX"


def test_get_transactions_empty_response():
    client = _make_client()
    client._client.transactions_get.return_value = _api_response([])
    result = client.get_transactions("tok", user_id="u1")
    assert result == []


def test_get_transactions_propagates_api_error():
    client = _make_client()
    client._client.transactions_get.side_effect = Exception("Plaid API 401")
    with pytest.raises(Exception, match="Plaid API 401"):
        client.get_transactions("bad-token", user_id="u1")


def test_get_transactions_calls_api_once():
    client = _make_client()
    client._client.transactions_get.return_value = _api_response([])
    client.get_transactions("tok", user_id="u1", months=3)
    client._client.transactions_get.assert_called_once()


# ── create_sandbox_access_token ────────────────────────────────────────────────

def _sandbox_mocks(client: PlaidClient, access_token: str = "access-sandbox-xyz") -> None:
    pt_resp = MagicMock()
    pt_resp.__getitem__ = lambda self, k: "public-sandbox-token" if k == "public_token" else None
    exchange_resp = MagicMock()
    exchange_resp.__getitem__ = lambda self, k: access_token if k == "access_token" else None
    client._client.sandbox_public_token_create.return_value = pt_resp
    client._client.item_public_token_exchange.return_value = exchange_resp


def test_create_sandbox_access_token_returns_string():
    client = _make_client()
    _sandbox_mocks(client)
    token = client.create_sandbox_access_token()
    assert token == "access-sandbox-xyz"


def test_create_sandbox_access_token_calls_both_endpoints():
    client = _make_client()
    _sandbox_mocks(client)
    client.create_sandbox_access_token()
    client._client.sandbox_public_token_create.assert_called_once()
    client._client.item_public_token_exchange.assert_called_once()


def test_create_sandbox_access_token_custom_token():
    client = _make_client()
    _sandbox_mocks(client, access_token="access-sandbox-custom")
    token = client.create_sandbox_access_token(institution_id="ins_999999")
    assert token == "access-sandbox-custom"
