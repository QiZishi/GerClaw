"""One-shot production corpus index command."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict

from qdrant_client import AsyncQdrantClient

from gerclaw_api.config import get_settings
from gerclaw_api.logging import configure_logging
from gerclaw_api.modules.rag.runtime import create_rag_runtime


async def _sync() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    api_key = (
        settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key is not None else None
    )
    client = AsyncQdrantClient(url=str(settings.qdrant_url).rstrip("/"), api_key=api_key)
    runtime = create_rag_runtime(settings, client)
    try:
        report = await runtime.indexer.sync()
        print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
        return 1 if report.failed else 0
    finally:
        await runtime.aclose()
        await client.close()


def main() -> None:
    """Run a full idempotent corpus reconciliation."""

    raise SystemExit(asyncio.run(_sync()))


if __name__ == "__main__":
    main()
