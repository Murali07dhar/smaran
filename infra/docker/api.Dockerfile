# syntax=docker/dockerfile:1.7
# Build context = repository root.  docker build -f infra/docker/api.Dockerfile .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

ARG REQUIREMENTS_FILE=services/api/requirements.txt
COPY ${REQUIREMENTS_FILE} /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

RUN useradd --create-home --uid 10001 smaran \
    && mkdir -p /data/media && chown smaran:smaran /data/media

COPY --chmod=0755 infra/docker/healthcheck.py /usr/local/bin/healthcheck.py
COPY --chmod=0755 infra/docker/api-entrypoint.sh /usr/local/bin/entrypoint.sh
COPY --chown=smaran:smaran services/api/ /app/

USER smaran
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
