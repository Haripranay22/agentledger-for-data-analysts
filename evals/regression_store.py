"""
Eval regression store — persists every eval run to SQLite and surfaces
pass→fail regressions between consecutive runs.

Schema
------
runs        (run_id, timestamp, model, passed, total, duration_s)
scenario_results (run_id, scenario_id, passed, risk_score, recommendation,
                  validity, latency_s, failures_json)

Usage
-----
    from evals.regression_store import RegressionStore
    store = RegressionStore()
    run_id = store.save_run(results, model="gpt-4o-mini")
    diff = store.compare_to_previous(run_id)
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent / "history.db"


class RegressionStore:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id      TEXT PRIMARY KEY,
                    timestamp   TEXT NOT NULL,
                    model       TEXT NOT NULL,
                    passed      INTEGER NOT NULL,
                    total       INTEGER NOT NULL,
                    duration_s  REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS scenario_results (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id          TEXT NOT NULL REFERENCES runs(run_id),
                    scenario_id     TEXT NOT NULL,
                    passed          INTEGER NOT NULL,
                    risk_score      INTEGER,
                    recommendation  TEXT,
                    validity        REAL,
                    latency_s       REAL,
                    failures_json   TEXT NOT NULL DEFAULT '[]'
                );

                CREATE INDEX IF NOT EXISTS idx_sr_run
                    ON scenario_results(run_id);
                CREATE INDEX IF NOT EXISTS idx_sr_scenario
                    ON scenario_results(scenario_id);
            """)

    # ── Write ──────────────────────────────────────────────────────────────────

    def save_run(
        self,
        results: list[dict[str, Any]],
        model: str,
        duration_s: float = 0.0,
        run_id: str | None = None,
    ) -> str:
        """Persist a completed eval run. Returns the run_id."""
        rid = run_id or str(uuid.uuid4())
        ts = datetime.now(UTC).isoformat()
        passed = sum(1 for r in results if r["passed"])

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?)",
                (rid, ts, model, passed, len(results), round(duration_s, 2)),
            )
            conn.executemany(
                """INSERT INTO scenario_results
                   (run_id, scenario_id, passed, risk_score, recommendation,
                    validity, latency_s, failures_json)
                   VALUES (?,?,?,?,?,?,?,?)""",
                [
                    (
                        rid,
                        r["scenario_id"],
                        int(r["passed"]),
                        r.get("risk_score"),
                        r.get("recommendation"),
                        r.get("validity"),
                        r.get("latency_s"),
                        json.dumps(r.get("failures", [])),
                    )
                    for r in results
                ],
            )
        return rid

    # ── Read ───────────────────────────────────────────────────────────────────

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent runs newest-first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_run_results(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM scenario_results WHERE run_id=? ORDER BY scenario_id",
                (run_id,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["failures"] = json.loads(d.pop("failures_json", "[]"))
            d["passed"] = bool(d["passed"])
            out.append(d)
        return out

    def previous_run_id(self, current_run_id: str) -> str | None:
        """Return the run_id of the run immediately before current_run_id."""
        with self._connect() as conn:
            # Get timestamp of current run
            row = conn.execute(
                "SELECT timestamp FROM runs WHERE run_id=?", (current_run_id,)
            ).fetchone()
            if not row:
                return None
            ts = row["timestamp"]
            prev = conn.execute(
                "SELECT run_id FROM runs WHERE timestamp < ? ORDER BY timestamp DESC LIMIT 1",
                (ts,),
            ).fetchone()
        return prev["run_id"] if prev else None

    # ── Comparison ─────────────────────────────────────────────────────────────

    def compare_to_previous(
        self, current_run_id: str
    ) -> dict[str, Any] | None:
        """
        Diff current run against the immediately preceding run.
        Returns None if there is no previous run to compare against.

        Return structure:
        {
            "previous_run_id": str,
            "previous_timestamp": str,
            "regressions":   list[dict],  # PASS → FAIL
            "improvements":  list[dict],  # FAIL → PASS
            "new_scenarios": list[dict],  # not in previous run
            "unchanged_fail":list[dict],  # still failing
        }
        """
        prev_id = self.previous_run_id(current_run_id)
        if prev_id is None:
            return None

        current = {r["scenario_id"]: r for r in self.get_run_results(current_run_id)}
        previous = {r["scenario_id"]: r for r in self.get_run_results(prev_id)}

        with self._connect() as conn:
            prev_meta = dict(
                conn.execute(
                    "SELECT * FROM runs WHERE run_id=?", (prev_id,)
                ).fetchone()
            )

        regressions, improvements, new_scenarios, unchanged_fail = [], [], [], []

        for sid, cur in current.items():
            if sid not in previous:
                new_scenarios.append(cur)
            elif previous[sid]["passed"] and not cur["passed"]:
                regressions.append(cur)
            elif not previous[sid]["passed"] and cur["passed"]:
                improvements.append(cur)
            elif not cur["passed"]:
                unchanged_fail.append(cur)

        return {
            "previous_run_id": prev_id,
            "previous_timestamp": prev_meta["timestamp"],
            "previous_passed": prev_meta["passed"],
            "previous_total": prev_meta["total"],
            "regressions": regressions,
            "improvements": improvements,
            "new_scenarios": new_scenarios,
            "unchanged_fail": unchanged_fail,
        }
