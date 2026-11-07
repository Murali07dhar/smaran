#!/usr/bin/env bash
# Regenerate packages/contracts/openapi.json + src/schema.d.ts..
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python "$HERE/export_openapi.py" "$@"
cd "$HERE/../../../packages/contracts"
if command -v pnpm >/dev/null 2>&1; then pnpm install --silent && pnpm generate; else npm install --silent && npm run generate; fi
