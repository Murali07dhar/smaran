#!/bin/sh
# Runs Alembic migrations (when alembic.ini exists) then starts the given command.
# Set RUN_MIGRATIONS=0 for sidecar containers that reuse this image (e.g. insights-scan).
set -eu
if [ "${RUN_MIGRATIONS:-1}" = "1" ] && [ -f alembic.ini ]; then
  echo "[entrypoint] alembic upgrade head"
  alembic upgrade head
fi
exec "$@"
