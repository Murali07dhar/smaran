# syntax=docker/dockerfile:1.7
# Build context = repository root.  docker build -f infra/docker/ai.Dockerfile .
# NOTE: services/ai (Claude 2) must ship requirements.txt and expose an ASGI app at APP_MODULE.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_MODULE=app.main:app
WORKDIR /app

ARG REQUIREMENTS_FILE=services/ai/requirements.txt
COPY ${REQUIREMENTS_FILE} /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

RUN useradd --create-home --uid 10001 smaran
COPY --chmod=0755 infra/docker/healthcheck.py /usr/local/bin/healthcheck.py
COPY --chown=smaran:smaran services/ai/ /app/

USER smaran
EXPOSE 8001
CMD ["sh", "-c", "exec uvicorn ${APP_MODULE} --host 0.0.0.0 --port 8001 --proxy-headers"]
