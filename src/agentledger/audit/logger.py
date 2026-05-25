"""
Audit Logger — structured JSON logs for every AI decision.

Every LLM call, every categorization, every metric computation
is logged with: run_id, timestamp, node_name, input_hash, output, latency_ms.

Logs are written locally and optionally shipped to S3.
This is the compliance story: a regulator can trace any credit decision
back to the raw transaction that supported it.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AuditLogger:
    """Write structured audit records for every AI decision."""

    def __init__(self, run_id: str, log_dir: Path = Path("logs/audit")) -> None:
        self.run_id = run_id
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._records: list[dict[str, Any]] = []

    def log(
        self,
        node: str,
        event_type: str,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        latency_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a single audit event."""
        record = {
            "run_id": self.run_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "node": node,
            "event_type": event_type,
            "latency_ms": latency_ms,
            "inputs": inputs,
            "outputs": outputs,
            **(metadata or {}),
        }
        self._records.append(record)
        logger.debug("AUDIT | node=%s | event=%s", node, event_type)

    def flush(self) -> Path:
        """Write all records to a JSONL file and return the path."""
        out_path = self.log_dir / f"run_{self.run_id}.jsonl"
        with open(out_path, "w") as f:
            for record in self._records:
                f.write(json.dumps(record) + "\n")
        logger.info("Audit log written: %s (%d records)", out_path, len(self._records))
        return out_path

    def __enter__(self) -> AuditLogger:
        return self

    def __exit__(self, *_: Any) -> None:
        self.flush()
