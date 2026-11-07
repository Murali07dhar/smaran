#!/usr/bin/env python
"""Export the live OpenAPI schema to packages/contracts/openapi.json.

    cd services/api && python scripts/export_openapi.py [--out PATH] [--with-stubs]

Then regenerate TS types:  cd packages/contracts && pnpm generate   (openapi-typescript)
or both in one go:         services/api/scripts/gen_contracts.sh

Needs no database/redis. --with-stubs also loads mocks/api_stubs so paths of not-yet-merged
modules appear (typed loosely); the Integrator regenerates WITHOUT it once real modules exist.
"""
import argparse
import json
import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
sys.path.insert(0, str(API_ROOT))
os.environ.setdefault("JWT_SECRET", "openapi-export-only-not-a-real-secret-0123456789")

ap = argparse.ArgumentParser()
ap.add_argument("--out", default=str(REPO_ROOT / "packages" / "contracts" / "openapi.json"))
args = ap.parse_args()
os.environ["STRICT_MODULES"] = "1"  # fail loudly if any module is missing
os.environ["ENVIRONMENT"] = "development"  # production disables /openapi.json

from app.main import app  # noqa: E402

spec = app.openapi()
Path(args.out).parent.mkdir(parents=True, exist_ok=True)
Path(args.out).write_text(json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"wrote {args.out}: {len(spec.get('paths', {}))} paths, modules={ {k: v['status'] for k, v in app.state.modules.items()} }")
