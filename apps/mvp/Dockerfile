ARG NODE_IMAGE=public.ecr.aws/docker/library/node:22-alpine

FROM ${NODE_IMAGE} AS dependencies
WORKDIR /app
ARG NPM_REGISTRY=https://registry.npmmirror.com
COPY package.json package-lock.json ./
RUN npm ci --registry="${NPM_REGISTRY}" --no-audit --no-fund

FROM dependencies AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
ARG NEXT_PUBLIC_APP_NAME=GerClaw
ARG NEXT_PUBLIC_APP_VERSION=1.0.0
ENV NEXT_PUBLIC_APP_NAME=${NEXT_PUBLIC_APP_NAME} \
    NEXT_PUBLIC_APP_VERSION=${NEXT_PUBLIC_APP_VERSION}
COPY . .
RUN npm run build

FROM ${NODE_IMAGE} AS production
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

RUN addgroup --system --gid 1001 gerclaw \
    && adduser --system --uid 1001 --ingroup gerclaw gerclaw

COPY --from=builder --chown=gerclaw:gerclaw /app/public ./public
COPY --from=builder --chown=gerclaw:gerclaw /app/.next/standalone ./
COPY --from=builder --chown=gerclaw:gerclaw /app/.next/static ./.next/static

USER gerclaw
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://127.0.0.1:3000/ || exit 1

CMD ["node", "server.js"]
