"""CLI entry point for the committed deterministic safety evaluation baseline."""

from __future__ import annotations

import json
from typing import Never

from gerclaw_api.modules.evals.runner import run_golden_cases


def main() -> Never:
    results = run_golden_cases()
    print(
        json.dumps(
            {
                "schema_version": "eval-run-v1",
                "kind": "deterministic_safety_policy",
                "case_count": len(results),
                "passed_count": sum(result.passed for result in results),
                "external_model_or_rag": False,
                "results": [result.model_dump(mode="json") for result in results],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    raise SystemExit(0)


if __name__ == "__main__":  # pragma: no cover - explicit CLI boundary
    main()
