# syntax=docker/dockerfile:1.7
# Build context = repository root (pnpm workspace).  docker build -f infra/docker/patient-web.Dockerfile .
# Needs pnpm-lock.yaml committed at the repo root (install uses --frozen-lockfile).
ARG NODE_VERSION=20

FROM node:${NODE_VERSION}-alpine AS build
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH
RUN corepack enable
WORKDIR /repo
COPY . .
RUN pnpm install --frozen-lockfile

# Same-origin by default: nginx proxies /api and /ws to the api container (see nginx.conf).
# NOTE: the variable name VITE_API_BASE_URL is an assumption: align with the app's config.
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ARG APP_DIR=apps/patient-web
RUN pnpm --filter "./${APP_DIR}..." run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
ARG APP_DIR=apps/patient-web
COPY infra/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/${APP_DIR}/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1
