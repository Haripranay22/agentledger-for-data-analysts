"""Unit tests for the eval regression store."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from evals.regression_store import RegressionStore


def _make_results(overrides: dict | None = None) -> list[dict]:
    base = [
        {"scenario_id": "scn_001", "passed": True,  "risk_score": 25, "recommendation": "approve",                  "validity": 1.0, "latency_s": 1.2, "failures": []},
        {"scenario_id": "scn_002", "passed": True,  "risk_score": 40, "recommendation": "approve_with_conditions",  "validity": 0.9, "latency_s": 1.5, "failures": []},
        {"scenario_id": "scn_003", "passed": False, "risk_score": 70, "recommendation": "decline",                  "validity": 0.7, "latency_s": 1.8, "failures": ["Citation validity 70% below threshold 85%"]},
    ]
    if overrides:
        for r in base:
            if r["scenario_id"] in overrides:
                r.update(overrides[r["scenario_id"]])
    return base


@pytest.fixture
def store(tmp_path):
    return RegressionStore(db_path=tmp_path / "test.db")


class TestSaveAndLoad:
    def test_save_run_returns_run_id(self, store):
        rid = store.save_run(_make_results(), model="gpt-4o-mini")
        assert isinstance(rid, str) and len(rid) == 36

    def test_list_runs_newest_first(self, store):
        store.save_run(_make_results(), model="gpt-4o-mini")
        store.save_run(_make_results(), model="gpt-4o-mini")
        runs = store.list_runs()
        assert len(runs) == 2
        assert runs[0]["timestamp"] >= runs[1]["timestamp"]

    def test_get_run_results_returns_all_scenarios(self, store):
        rid = store.save_run(_make_results(), model="gpt-4o-mini")
        results = store.get_run_results(rid)
        assert len(results) == 3
        assert results[0]["scenario_id"] == "scn_001"

    def test_passed_field_is_bool(self, store):
        rid = store.save_run(_make_results(), model="gpt-4o-mini")
        results = store.get_run_results(rid)
        assert all(isinstance(r["passed"], bool) for r in results)

    def test_failures_deserialised_as_list(self, store):
        rid = store.save_run(_make_results(), model="gpt-4o-mini")
        results = {r["scenario_id"]: r for r in store.get_run_results(rid)}
        assert results["scn_003"]["failures"] == ["Citation validity 70% below threshold 85%"]
        assert results["scn_001"]["failures"] == []

    def test_duration_stored(self, store):
        store.save_run(_make_results(), model="gpt-4o-mini", duration_s=42.5)
        runs = store.list_runs()
        assert runs[0]["duration_s"] == 42.5


class TestCompare:
    def test_no_previous_returns_none(self, store):
        rid = store.save_run(_make_results(), model="gpt-4o-mini")
        assert store.compare_to_previous(rid) is None

    def test_regression_detected(self, store):
        # First run: scn_001 passes
        store.save_run(_make_results(), model="gpt-4o-mini")
        # Second run: scn_001 now fails
        second = _make_results({"scn_001": {"passed": False, "failures": ["bad rec"]}})
        rid2 = store.save_run(second, model="gpt-4o-mini")
        diff = store.compare_to_previous(rid2)
        assert diff is not None
        regression_ids = [r["scenario_id"] for r in diff["regressions"]]
        assert "scn_001" in regression_ids

    def test_improvement_detected(self, store):
        # First run: scn_003 fails
        store.save_run(_make_results(), model="gpt-4o-mini")
        # Second run: scn_003 now passes
        second = _make_results({"scn_003": {"passed": True, "failures": []}})
        rid2 = store.save_run(second, model="gpt-4o-mini")
        diff = store.compare_to_previous(rid2)
        assert diff is not None
        improvement_ids = [r["scenario_id"] for r in diff["improvements"]]
        assert "scn_003" in improvement_ids

    def test_new_scenario_detected(self, store):
        store.save_run(_make_results(), model="gpt-4o-mini")
        second = _make_results()
        second.append({"scenario_id": "scn_099", "passed": True, "risk_score": 20,
                       "recommendation": "approve", "validity": 1.0, "latency_s": 1.0, "failures": []})
        rid2 = store.save_run(second, model="gpt-4o-mini")
        diff = store.compare_to_previous(rid2)
        assert diff is not None
        new_ids = [r["scenario_id"] for r in diff["new_scenarios"]]
        assert "scn_099" in new_ids

    def test_no_change_produces_empty_regression_list(self, store):
        store.save_run(_make_results(), model="gpt-4o-mini")
        rid2 = store.save_run(_make_results(), model="gpt-4o-mini")
        diff = store.compare_to_previous(rid2)
        assert diff is not None
        assert diff["regressions"] == []
        assert diff["improvements"] == []

    def test_previous_run_id_points_to_correct_run(self, store):
        rid1 = store.save_run(_make_results(), model="gpt-4o-mini")
        rid2 = store.save_run(_make_results(), model="gpt-4o-mini")
        assert store.previous_run_id(rid2) == rid1
        assert store.previous_run_id(rid1) is None
