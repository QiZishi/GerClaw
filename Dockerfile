FROM python:3.12-slim AS api-builder

ARG PYTHON_PACKAGE_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple

ENV UV_DEFAULT_INDEX=${PYTHON_PACKAGE_INDEX} \
    UV_HTTP_RETRIES=5 \
    UV_HTTP_TIMEOUT=120 \
    UV_LINK_MODE=copy \
    PATH=/app/.venv/bin:$PATH

WORKDIR /app/api

RUN pip install --no-cache-dir --index-url "${PYTHON_PACKAGE_INDEX}" uv==0.11.17

COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/README.md apps/api/alembic.ini ./
COPY apps/api/migrations ./migrations
COPY apps/api/src ./src
COPY apps/api/scripts ./scripts
COPY apps/api/evals/rag-retrieval-reviewed-v1.json ./evals/rag-retrieval-reviewed-v1.json

RUN uv sync --frozen --no-dev

FROM node:22-bookworm-slim AS web-builder

ARG NPM_REGISTRY=https://registry.npmmirror.com
ARG NEXT_PUBLIC_APP_NAME=GerClaw
ARG NEXT_PUBLIC_APP_VERSION=1.0.0

ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_APP_NAME=${NEXT_PUBLIC_APP_NAME} \
    NEXT_PUBLIC_APP_VERSION=${NEXT_PUBLIC_APP_VERSION}

WORKDIR /app/mvp

COPY apps/mvp/package.json apps/mvp/package-lock.json ./
RUN npm ci --registry="${NPM_REGISTRY}" --no-audit --no-fund

COPY apps/mvp ./
RUN npm run build

FROM python:3.12-slim AS production

ARG QDRANT_VERSION=1.18.2

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/api/.venv/bin:$PATH \
    NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=7860 \
    GERCLAW_API_URL=http://127.0.0.1:8000 \
    GERCLAW_KNOWLEDGE_BASE_PATH=/app/knowledge-base

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        ca-certificates \
        curl \
        libstdc++6 \
        postgresql \
        redis-server \
    && curl -fsSL --retry 5 \
        "https://github.com/qdrant/qdrant/releases/download/v${QDRANT_VERSION}/qdrant-x86_64-unknown-linux-gnu.tar.gz" \
        -o /tmp/qdrant.tar.gz \
    && tar -xzf /tmp/qdrant.tar.gz -C /tmp \
    && install -m 0755 /tmp/qdrant /usr/local/bin/qdrant \
    && rm -f /tmp/qdrant.tar.gz /tmp/qdrant \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=api-builder /app/api /app/api
COPY --from=web-builder /app/mvp/public /app/web/public
COPY --from=web-builder /app/mvp/.next/standalone /app/web
COPY --from=web-builder /app/mvp/.next/static /app/web/.next/static
COPY knowledge-base /app/knowledge-base
COPY docker-entrypoint.sh /app/docker-entrypoint.sh

RUN addgroup --system gerclaw \
    && adduser --system --shell /bin/sh --ingroup gerclaw --home /app gerclaw \
    && mkdir -p /app/workspaces \
    && chmod 755 /app/docker-entrypoint.sh \
    && chown -R gerclaw:gerclaw /app

USER gerclaw

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/', timeout=3)"

ENTRYPOINT ["/app/docker-entrypoint.sh"]