"""Explicit, budget-bounded CLI for reviewed external RAG regression cases."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Never

from pydantic import ValidationError
from qdrant_client import AsyncQdrantClient

from gerclaw_api.config import get_settings
from gerclaw_api.modules.evals.models import RAGEvaluationRunConfig, RAGRetrievalEvalCaseSet
from gerclaw_api.modules.evals.runner import run_opt_in_rag_retrieval_evaluation
from gerclaw_api.modules.rag.runtime import create_rag_runtime


class RAGEvaluationCliError(RuntimeError):
    """A stable CLI boundary error that never echoes case-file content."""


def load_rag_case_set(path: Path) -> RAGRetrievalEvalCaseSet:
    """Load one reviewed JSON case file without exposing invalid sensitive content."""

    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
        return RAGRetrievalEvalCaseSet.model_validate(value)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as error:
        raise RAGEvaluationCliError("RAG evaluation case file is invalid") from error


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-external-rag",
        action="store_true",
        help="explicitly permit configured embedding and rerank provider calls",
    )
    parser.add_argument(
        "--cases", type=Path, required=True, help="reviewed synthetic JSON case set"
    )
    parser.add_argument(
        "--index-version",
        required=True,
        help="expected immutable local corpus index version",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-cases", type=int, default=20)
    args = parser.parse_args(argv)
    if not args.allow_external_rag:
        parser.error("--allow-external-rag is required; this command may incur provider cost")
    return args


async def run(args: argparse.Namespace) -> dict[str, object]:
    """Create the production retrieval graph only after explicit CLI opt-in."""

    case_set = load_rag_case_set(args.cases)
    config = RAGEvaluationRunConfig(
        allow_external_rag=True,
        index_version=args.index_version,
        top_k=args.top_k,
        max_cases=args.max_cases,
    )
    settings = get_settings()
    qdrant_key = (
        settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key is not None else None
    )
    qdrant = AsyncQdrantClient(url=str(settings.qdrant_url).rstrip("/"), api_key=qdrant_key)
    runtime = create_rag_runtime(settings, qdrant)
    try:
        report = await run_opt_in_rag_retrieval_evaluation(
            runtime.module,
            case_set.cases,
            config=config,
        )
        return report.model_dump(mode="json")
    finally:
        await runtime.aclose()
        await qdrant.close()


def main() -> Never:
    try:
        result = asyncio.run(run(parse_args()))
    except RAGEvaluationCliError as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(2) from error
    except Exception as error:
        print(
            json.dumps(
                {"ok": False, "error": "RAG evaluation runtime is unavailable"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from error
    print(json.dumps({"ok": True, "report": result}, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0)


if __name__ == "__main__":  # pragma: no cover - explicit CLI boundary
    main()
