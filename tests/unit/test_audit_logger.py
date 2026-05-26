"""Unit tests for the AuditLogger."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from agentledger.audit.logger import AuditLogger


def _mock_boto3(upload_side_effect: Exception | None = None) -> MagicMock:
    """Return a MagicMock that stands in for the boto3 module."""
    mock_client = MagicMock()
    if upload_side_effect:
        mock_client.upload_file.side_effect = upload_side_effect
    mock_b3 = MagicMock()
    mock_b3.client.return_value = mock_client
    return mock_b3


def _make_logger(tmp_dir: Path, run_id: str = "run_abc123") -> AuditLogger:
    return AuditLogger(run_id=run_id, log_dir=tmp_dir)


# ── Initialization ─────────────────────────────────────────────────────────────

def test_creates_log_dir_on_init():
    with tempfile.TemporaryDirectory() as tmp:
        log_dir = Path(tmp) / "audit" / "logs"
        AuditLogger(run_id="run_001", log_dir=log_dir)
        assert log_dir.exists()


def test_starts_with_empty_records():
    with tempfile.TemporaryDirectory() as tmp:
        al = _make_logger(Path(tmp))
        assert al._records == []


# ── log() ──────────────────────────────────────────────────────────────────────

def test_log_appends_record():
    with tempfile.TemporaryDirectory() as tmp:
        al = _make_logger(Path(tmp))
        al.log("ingest", "transaction_pulled", inputs={"user_id": "u1"}, outputs={"count": 10})
        assert len(al._records) == 1


def test_log_record_has_required_fields():
    with tempfile.TemporaryDirectory() as tmp:
        al = _make_logger(Path(tmp), run_id="run_xyz")
        al.log("risk_assess", "llm_call", inputs={"prompt_len": 500}, outputs={"score": 30})
        record = al._records[0]
        assert record["run_id"] == "run_xyz"
        assert record["node"] == "risk_assess"
        assert record["event_type"] == "llm_call"
        assert "timestamp" in record
        assert record["inputs"] == {"prompt_len": 500}
        assert record["outputs"] == {"score": 30}


def test_log_stores_latency():
    with tempfile.TemporaryDirectory() as tmp:
        al = _make_logger(Path(tmp))
        al.log("validate", "citation_check", inputs={}, outputs={}, latency_ms=142.5)
        assert al._records[0]["latency_ms"] == 142.5


def test_log_latency_none_when_not_provided():
    with tempfile.TemporaryDirectory() as tmp:
        al = _make_logger(Path(tmp))
        al.log("profile", "dq_check", inputs={}, outputs={})
        assert al._records[0]["latency_ms"] is None


def test_log_merges_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        al = _make_logger(Path(tmp))
        al.log("report", "memo_saved", inputs={}, outputs={},
               metadata={"memo_path": "/tmp/memo.md"})
        assert al._records[0]["memo_path"] == "/tmp/memo.md"


def test_multiple_logs_accumulate():
    with tempfile.TemporaryDirectory() as tmp:
        al = _make_logger(Path(tmp))
        for i in range(5):
            al.log(f"node_{i}", "event", inputs={}, outputs={})
        assert len(al._records) == 5


# ── flush() ────────────────────────────────────────────────────────────────────

def test_flush_creates_jsonl_file():
    with tempfile.TemporaryDirectory() as tmp:
        al = _make_logger(Path(tmp), run_id="run_flush")
        al.log("ingest", "pulled", inputs={}, outputs={})
        path = al.flush()
        assert path.exists()
        assert path.name == "run_run_flush.jsonl"


def test_flush_writes_valid_jsonl():
    with tempfile.TemporaryDirectory() as tmp:
        al = _make_logger(Path(tmp))
        al.log("ingest", "event_a", inputs={"x": 1}, outputs={"y": 2})
        al.log("profile", "event_b", inputs={"x": 3}, outputs={"y": 4})
        path = al.flush()
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2
        for line in lines:
            record = json.loads(line)
            assert "run_id" in record
            assert "timestamp" in record


def test_flush_with_no_records_creates_empty_file():
    with tempfile.TemporaryDirectory() as tmp:
        al = _make_logger(Path(tmp), run_id="empty_run")
        path = al.flush()
        assert path.exists()
        assert path.read_text().strip() == ""


def test_flush_returns_correct_path():
    with tempfile.TemporaryDirectory() as tmp:
        al = _make_logger(Path(tmp), run_id="my_run")
        path = al.flush()
        assert "my_run" in path.name


# ── Context manager ────────────────────────────────────────────────────────────

def test_context_manager_flushes_on_exit():
    with tempfile.TemporaryDirectory() as tmp:
        log_dir = Path(tmp)
        with AuditLogger(run_id="ctx_run", log_dir=log_dir) as al:
            al.log("ingest", "event", inputs={}, outputs={})
        # After exit, the file should exist
        expected = log_dir / "run_ctx_run.jsonl"
        assert expected.exists()


def test_context_manager_returns_self():
    with tempfile.TemporaryDirectory() as tmp:
        logger_instance = AuditLogger(run_id="r1", log_dir=Path(tmp))
        result = logger_instance.__enter__()
        assert result is logger_instance
        logger_instance.__exit__(None, None, None)


# ── Timestamp ─────────────────────────────────────────────────────────────────

def test_timestamp_is_iso_format():
    with tempfile.TemporaryDirectory() as tmp:
        al = _make_logger(Path(tmp))
        al.log("node", "event", inputs={}, outputs={})
        ts = al._records[0]["timestamp"]
        from datetime import datetime
        # Should parse without error
        datetime.fromisoformat(ts)


def test_timestamp_includes_timezone():
    with tempfile.TemporaryDirectory() as tmp:
        al = _make_logger(Path(tmp))
        al.log("node", "event", inputs={}, outputs={})
        ts = al._records[0]["timestamp"]
        assert "+" in ts or ts.endswith("Z") or "+00:00" in ts


# ── S3 shipping ────────────────────────────────────────────────────────────────

def test_ship_to_s3_skips_when_no_bucket():
    with tempfile.TemporaryDirectory() as tmp:
        al = AuditLogger(run_id="no_bucket", log_dir=Path(tmp))
        path = al.flush()
        result = al.ship_to_s3(path)
        assert result is None


def test_ship_to_s3_skips_when_boto3_missing():
    with tempfile.TemporaryDirectory() as tmp:
        al = AuditLogger(run_id="no_boto3", log_dir=Path(tmp), s3_bucket="my-bucket")
        path = al.flush()
        # Remove boto3 from sys.modules so the import inside ship_to_s3 raises ImportError
        with patch.dict(sys.modules, {"boto3": None}):  # type: ignore[dict-item]
            result = al.ship_to_s3(path)
        assert result is None


def test_ship_to_s3_returns_uri_on_success():
    with tempfile.TemporaryDirectory() as tmp:
        al = AuditLogger(run_id="s3_run", log_dir=Path(tmp), s3_bucket="audit-bucket")
        al.log("ingest", "event", inputs={}, outputs={})
        path = al.flush()

        with patch.dict(sys.modules, {"boto3": _mock_boto3()}):
            result = al.ship_to_s3(path)

        assert result == "s3://audit-bucket/audit-logs/run_s3_run.jsonl"


def test_ship_to_s3_returns_none_on_upload_error():
    with tempfile.TemporaryDirectory() as tmp:
        al = AuditLogger(run_id="err_run", log_dir=Path(tmp), s3_bucket="audit-bucket")
        path = al.flush()

        mock_b3 = _mock_boto3(upload_side_effect=Exception("S3 connection refused"))
        with patch.dict(sys.modules, {"boto3": mock_b3}):
            result = al.ship_to_s3(path)

        assert result is None


def test_ship_to_s3_uses_env_bucket() -> None:
    import os
    with tempfile.TemporaryDirectory() as tmp:
        with patch.dict(os.environ, {"AUDIT_S3_BUCKET": "env-bucket"}):
            al = AuditLogger(run_id="env_run", log_dir=Path(tmp))
            assert al._s3_bucket == "env-bucket"
            path = al.flush()
            with patch.dict(sys.modules, {"boto3": _mock_boto3()}):
                result = al.ship_to_s3(path)
        assert result == "s3://env-bucket/audit-logs/run_env_run.jsonl"


def test_flush_and_ship_returns_both():
    with tempfile.TemporaryDirectory() as tmp:
        al = AuditLogger(run_id="both_run", log_dir=Path(tmp), s3_bucket="my-bucket")
        al.log("node", "event", inputs={}, outputs={})
        with patch.dict(sys.modules, {"boto3": _mock_boto3()}):
            local_path, s3_uri = al.flush_and_ship()
        assert local_path.exists()
        assert s3_uri is not None and s3_uri.startswith("s3://")


def test_custom_s3_prefix():
    with tempfile.TemporaryDirectory() as tmp:
        al = AuditLogger(
            run_id="prefix_run", log_dir=Path(tmp),
            s3_bucket="my-bucket", s3_prefix="credit/audit/"
        )
        path = al.flush()
        with patch.dict(sys.modules, {"boto3": _mock_boto3()}):
            result = al.ship_to_s3(path)
        assert result == "s3://my-bucket/credit/audit/run_prefix_run.jsonl"
