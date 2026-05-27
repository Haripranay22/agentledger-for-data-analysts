"""
Audit Logger — structured JSON logs for every AI decision.

Every LLM call, every categorization, every metric computation
is logged with: run_id, timestamp, node_name, input_hash, output, latency_ms.

Logs are written locally and optionally shipped to S3.
This is the compliance story: a regulator can trace any credit decision
back to the raw transaction that supported it.

S3 shipping is opt-in: set AUDIT_S3_BUCKET env var (and optionally
AUDIT_S3_PREFIX, defaults to "audit-logs/").
Requires the `cloud` optional extra: pip install agentledger[cloud].
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AuditLogger:
    """Write structured audit records for every AI decision."""

    def __init__(
        self,
        run_id: str,
        log_dir: Path = Path("logs/audit"),
        s3_bucket: str | None = None,
        s3_prefix: str = "audit-logs/",
    ) -> None:
        self.run_id = run_id
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._records: list[dict[str, Any]] = []
        # S3 config — env vars take precedence over constructor args
        self._s3_bucket = os.environ.get("AUDIT_S3_BUCKET") or s3_bucket
        self._s3_prefix = os.environ.get("AUDIT_S3_PREFIX", s3_prefix)

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
        """Write all records to a local JSONL file and return the path."""
        out_path = self.log_dir / f"run_{self.run_id}.jsonl"
        with open(out_path, "w") as f:
            for record in self._records:
                f.write(json.dumps(record) + "\n")
        logger.info("Audit log written: %s (%d records)", out_path, len(self._records))
        return out_path

    def ship_to_s3(self, local_path: Path) -> str | None:
        """
        Upload a JSONL audit log to S3.

        Returns the s3:// URI on success, None if S3 is not configured or upload fails.
        Requires boto3 (pip install agentledger[cloud]).
        """
        if not self._s3_bucket:
            logger.debug("AUDIT_S3_BUCKET not set — skipping S3 upload")
            return None

        try:
            import boto3  # type: ignore[import-untyped]
        except ImportError:
            logger.warning(
                "boto3 not installed — S3 upload skipped. pip install agentledger[cloud]"
            )
            return None

        key = f"{self._s3_prefix.rstrip('/')}/{local_path.name}"
        s3_uri = f"s3://{self._s3_bucket}/{key}"

        try:
            client = boto3.client("s3")
            client.upload_file(str(local_path), self._s3_bucket, key)
            logger.info("Audit log shipped to %s", s3_uri)
            return s3_uri
        except Exception as exc:
            logger.warning("S3 upload failed for %s: %s", s3_uri, exc)
            return None

    def flush_and_ship(self) -> tuple[Path, str | None]:
        """Write locally and upload to S3. Returns (local_path, s3_uri | None)."""
        local_path = self.flush()
        s3_uri = self.ship_to_s3(local_path)
        return local_path, s3_uri

    def __enter__(self) -> AuditLogger:
        return self

    def __exit__(self, *_: Any) -> None:
        self.flush_and_ship()
