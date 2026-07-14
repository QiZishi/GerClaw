ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE} AS runtime

# Keep custom or cached base images reproducible even if they declare a non-root user.
# The final runtime is explicitly dropped back to the unprivileged gerclaw account.
USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN pip install --no-cache-dir uv==0.11.17

WORKDIR /app
COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY migrations ./migrations
COPY src ./src
RUN uv sync --frozen --no-dev --no-cache

RUN addgroup --system gerclaw \
    && adduser --system --ingroup gerclaw --home /app gerclaw \
    && mkdir -p /app/workspaces \
    && chown -R gerclaw:gerclaw /app

USER gerclaw
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"

CMD ["uvicorn", "gerclaw_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
