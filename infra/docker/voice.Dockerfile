# syntax=docker/dockerfile:1.7
# Build context = repository root.  docker build -f infra/docker/voice.Dockerfile .
# NOTE: services/voice (Claude 6) must ship requirements.txt and expose an ASGI app at APP_MODULE.
# AI4Bharat models (IndicConformer, IndicTrans2, Indic TTS) are LARGE: expect a multi-GB image and a
# first-run model download into the /models volume. Not verified in this build (no network).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_MODULE=app.main:app
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

ARG REQUIREMENTS_FILE=services/voice/requirements.txt
COPY ${REQUIREMENTS_FILE} /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

RUN useradd --create-home --uid 10001 smaran \
    && mkdir -p /models /data/media && chown smaran:smaran /models /data/media
COPY --chmod=0755 infra/docker/healthcheck.py /usr/local/bin/healthcheck.py
COPY --chown=smaran:smaran services/voice/ /app/

USER smaran
EXPOSE 8002
CMD ["sh", "-c", "exec uvicorn ${APP_MODULE} --host 0.0.0.0 --port 8002 --proxy-headers"]
