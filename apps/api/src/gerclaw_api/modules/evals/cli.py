"""CLI entry point for the committed deterministic safety evaluation baseline."""

from __future__ import annotations

import json
from typing import Never

from gerclaw_api.modules.evals.runner import run_golden_cases, run_output_safety_golden_cases


def main() -> Never:
    safety_results = run_golden_cases()
    output_safety_results = run_output_safety_golden_cases()
    case_count = len(safety_results) + len(output_safety_results)
    passed_count = sum(result.passed for result in safety_results) + sum(
        result.passed for result in output_safety_results
    )
    print(
        json.dumps(
            {
                "schema_version": "eval-run-v1",
                "kind": "deterministic_safety_policy",
                "case_count": case_count,
                "passed_count": passed_count,
                "external_model_or_rag": False,
                "safety_results": [result.model_dump(mode="json") for result in safety_results],
                "output_safety_results": [
                    result.model_dump(mode="json") for result in output_safety_results
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    raise SystemExit(0)


if __name__ == "__main__":  # pragma: no cover - explicit CLI boundary
    main()
