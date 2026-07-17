ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE} AS runtime

# Keep custom or cached base images reproducible even if they declare a non-root user.
# The final runtime is explicitly dropped back to the unprivileged gerclaw account.
USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN pip install --no-cache-dir uv==0.11.17

ENV UV_HTTP_RETRIES=5 \
    UV_HTTP_TIMEOUT=120 \
    UV_LINK_MODE=copy

WORKDIR /app
COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY migrations ./migrations
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

RUN addgroup --system gerclaw \
    && adduser --system --ingroup gerclaw --home /app gerclaw \
    && mkdir -p /app/workspaces \
    && chown -R gerclaw:gerclaw /app

USER gerclaw

# The test image is deliberately separate from the production runtime image.
# It is only selected by the Compose `test` profile and includes test-only
# dependencies and sources; the default image remains free of both.
FROM runtime AS test

USER root
COPY tests ./tests
COPY evals ./evals
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --all-extras --dev \
    && chown -R gerclaw:gerclaw /app/.venv

USER gerclaw

# Keep the production stage last so an unqualified `docker build` never
# selects the test image. Compose also names this target explicitly.
FROM runtime AS production

USER gerclaw
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"

CMD ["uvicorn", "gerclaw_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
