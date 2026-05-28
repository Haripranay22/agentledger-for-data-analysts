"""Unit tests for the HITL human-review persistence layer."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.review_store import ReviewStore


@pytest.fixture
def store(tmp_path: Path) -> ReviewStore:
    return ReviewStore(reviews_dir=tmp_path / "reviews")


class TestSave:
    def test_save_returns_record(self, store: ReviewStore) -> None:
        rec = store.save("run-abc", reviewer="Alice", decision="approve")
        assert rec["reviewer"] == "Alice"
        assert rec["decision"] == "approve"

    def test_save_creates_file(self, store: ReviewStore) -> None:
        store.save("run-abc", reviewer="Alice", decision="approve")
        assert (store.reviews_dir / "run-abc.json").exists()

    def test_save_rejects_unknown_decision(self, store: ReviewStore) -> None:
        with pytest.raises(ValueError, match="Unknown decision"):
            store.save("run-abc", reviewer="Alice", decision="maybe")

    def test_save_stores_all_fields(self, store: ReviewStore) -> None:
        rec = store.save(
            "run-xyz",
            reviewer="Bob",
            decision="decline",
            notes="High DTI",
            ai_recommendation="manual_review",
            escalation_reasons=["Low confidence: 0.45"],
        )
        assert rec["notes"] == "High DTI"
        assert rec["ai_recommendation"] == "manual_review"
        assert rec["escalation_reasons"] == ["Low confidence: 0.45"]
        assert "timestamp" in rec


class TestLoad:
    def test_load_missing_returns_none(self, store: ReviewStore) -> None:
        assert store.load("nonexistent") is None

    def test_load_after_save(self, store: ReviewStore) -> None:
        store.save("run-123", reviewer="Carol", decision="defer", notes="Need bank statement")
        rec = store.load("run-123")
        assert rec is not None
        assert rec["decision"] == "defer"
        assert rec["notes"] == "Need bank statement"

    def test_load_roundtrip_preserves_all_fields(self, store: ReviewStore) -> None:
        store.save(
            "run-999",
            reviewer="Dave",
            decision="approve_with_conditions",
            notes="Requires co-signer",
            ai_recommendation="manual_review",
            escalation_reasons=["Ambiguous risk score: 52"],
        )
        rec = store.load("run-999")
        assert rec is not None
        assert rec["reviewer"] == "Dave"
        assert rec["escalation_reasons"] == ["Ambiguous risk score: 52"]


class TestDelete:
    def test_delete_existing(self, store: ReviewStore) -> None:
        store.save("run-del", reviewer="Eve", decision="approve")
        assert store.delete("run-del") is True
        assert store.load("run-del") is None

    def test_delete_nonexistent(self, store: ReviewStore) -> None:
        assert store.delete("no-such-run") is False

    def test_overwrite_review(self, store: ReviewStore) -> None:
        store.save("run-ow", reviewer="Frank", decision="approve")
        store.save("run-ow", reviewer="Frank", decision="decline", notes="Changed mind")
        rec = store.load("run-ow")
        assert rec is not None
        assert rec["decision"] == "decline"
