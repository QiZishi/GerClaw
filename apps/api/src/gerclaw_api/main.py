"""GerClaw ASGI entry point."""

from __future__ import annotations

import uvicorn

from gerclaw_api.application import create_app

app = create_app()


def run() -> None:
    """Run the development server through the installed console script."""

    uvicorn.run("gerclaw_api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":  # pragma: no cover
    run()
