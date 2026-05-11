"""
Evaluation Harness — runs all 30 ground-truth scenarios through the pipeline.

Metrics tracked:
  - Categorization accuracy
  - Numerical metric accuracy (must be 100%)
  - Recommendation agreement with expert label
  - Risk score MAE
  - Citation faithfulness
  - Hallucination rate
  - Time saved per file (vs 4-hour manual baseline)

Run: python evals/runner.py --scenario-dir evals/scenarios/
"""

from __future__ import annotations

import json
import time
from pathlib import Path
import yaml


def load_scenarios(scenario_dir: str = "evals/scenarios") -> list[dict]:
    """Load all YAML scenario files."""
    scenarios = []
    for path in sorted(Path(scenario_dir).glob("*.yaml")):
        with open(path) as f:
            scenarios.append(yaml.safe_load(f))
    return scenarios


def run_eval(scenario: dict) -> dict:
    """Run a single scenario and return results. TODO: wire up graph."""
    start = time.perf_counter()
    # TODO Week 3: invoke credit_analysis_graph on synthetic data
    elapsed = time.perf_counter() - start
    return {
        "scenario_id": scenario["scenario_id"],
        "status": "not_implemented",
        "latency_s": elapsed,
    }


def main(scenario_dir: str = "evals/scenarios", output: str = "evals/reports/latest.json") -> None:
    scenarios = load_scenarios(scenario_dir)
    print(f"Loaded {len(scenarios)} scenarios")
    results = [run_eval(s) for s in scenarios]
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results written to {output}")


if __name__ == "__main__":
    main()
