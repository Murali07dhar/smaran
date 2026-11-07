#!/usr/bin/env bash
# Run api :8000, ai :8001, voice :8002 natively (no Docker). Needs Postgres 16 + Redis running locally.
# Usage: scripts/native-up.sh [start|stop]   (logs in .run/)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; RUN="$ROOT/.run"; mkdir -p "$RUN" "$RUN/media"
if [ "${1:-start}" = "stop" ]; then for f in "$RUN"/*.pid; do [ -f "$f" ] && kill "$(cat "$f")" 2>/dev/null || true; done; exit 0; fi
[ -f "$RUN/env" ] || cat > "$RUN/env" <<EOT
export DATABASE_URL=postgresql+psycopg://smaran:smaran@localhost:5432/smaran
export REDIS_URL=redis://localhost:6379/0
export JWT_SECRET=$(python3 -c 'import secrets;print(secrets.token_hex(32))')
export MEDIA_KEY_B64=$(python3 -c 'import os,base64;print(base64.b64encode(os.urandom(32)).decode())')
export MEDIA_DIR=$RUN/media
export AI_SERVICE_URL=http://localhost:8001
export VOICE_SERVICE_URL=http://localhost:8002
export STRICT_MODULES=1
export SYNC_PULL_HOLDBACK_SECONDS=0
export CORS_ORIGINS=http://localhost:5173,http://localhost:5174
EOT
. "$RUN/env"
(cd "$ROOT/services/ai" && AI_STATE_DB="$RUN/ai.sqlite" nohup .venv/bin/uvicorn app.asgi:app --port 8001 >"$RUN/ai.log" 2>&1 & echo $! >"$RUN/ai.pid")
(cd "$ROOT/services/voice" && VOICE_MODELS_MODE=off VOICE_REQUIRE_AUTH=false nohup .venv/bin/uvicorn app.main:app --port 8002 >"$RUN/voice.log" 2>&1 & echo $! >"$RUN/voice.pid")
(cd "$ROOT/services/api" && .venv/bin/alembic upgrade head >"$RUN/migrate.log" 2>&1 && .venv/bin/python seed.py >>"$RUN/migrate.log" 2>&1 || true
 nohup .venv/bin/uvicorn app.main:app --port 8000 >"$RUN/api.log" 2>&1 & echo $! >"$RUN/api.pid")
sleep 4; echo "api :8000  ai :8001  voice :8002  (logs: $RUN)"
