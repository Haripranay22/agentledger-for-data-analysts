"""
Persistence layer for HITL human-review decisions.

Saves one JSON file per run_id under reports/reviews/.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_DEFAULT_REVIEWS_DIR = Path(__file__).parent.parent / "reports" / "reviews"

_REVIEW_DECISIONS = [
    "confirm_ai",
    "approve",
    "approve_with_conditions",
    "manual_review",
    "decline",
    "defer",
]

REVIEW_DECISION_LABELS: dict[str, str] = {
    "confirm_ai":               "Confirm AI recommendation",
    "approve":                  "Approve",
    "approve_with_conditions":  "Approve with conditions",
    "manual_review":            "Manual review — schedule analyst call",
    "decline":                  "Decline",
    "defer":                    "Defer — request more documentation",
}


class ReviewStore:
    def __init__(self, reviews_dir: Path = _DEFAULT_REVIEWS_DIR) -> None:
        self.reviews_dir = reviews_dir

    def _path(self, run_id: str) -> Path:
        return self.reviews_dir / f"{run_id}.json"

    def save(
        self,
        run_id: str,
        reviewer: str,
        decision: str,
        notes: str = "",
        ai_recommendation: str = "",
        escalation_reasons: list[str] | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        """Persist a review and return the saved record."""
        if decision not in _REVIEW_DECISIONS:
            raise ValueError(f"Unknown decision {decision!r}. Valid: {_REVIEW_DECISIONS}")
        record: dict[str, Any] = {
            "run_id": run_id,
            "reviewer": reviewer,
            "decision": decision,
            "notes": notes,
            "ai_recommendation": ai_recommendation,
            "escalation_reasons": escalation_reasons or [],
            "timestamp": timestamp or datetime.now(UTC).isoformat(),
        }
        self.reviews_dir.mkdir(parents=True, exist_ok=True)
        self._path(run_id).write_text(json.dumps(record, indent=2))
        return record

    def load(self, run_id: str) -> dict[str, Any] | None:
        """Return the review for run_id, or None if not found."""
        p = self._path(run_id)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def delete(self, run_id: str) -> bool:
        """Remove a review. Returns True if it existed."""
        p = self._path(run_id)
        if p.exists():
            p.unlink()
            return True
        return False
