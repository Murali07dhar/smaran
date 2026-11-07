"""Compare the generated OpenAPI with the ROUTES list of the shared briefing. Exit 1 on any difference.

Usage: python scripts/check_routes.py [path/to/openapi.json]   (default: export from the live app)
"""
import json
import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))
os.environ.setdefault("JWT_SECRET", "openapi-check-only-not-a-real-secret-0123456789")

P = "/api/v1"
# (method, path, required top-level response keys | None). "[]" = list of objects with those keys.
ROUTES = [
    ("post", "/auth/login", {"access_token", "refresh_token", "token_type", "user"}),
    ("post", "/auth/refresh", {"access_token", "refresh_token", "token_type", "user"}),
    ("post", "/auth/patient-pin-login", {"access_token", "refresh_token", "token_type", "user"}),
    ("post", "/auth/register", None), ("get", "/me", None),
    ("post", "/patients", None),
    ("get", "/patients", "[]:id,name,age,language,estimated_stage,last_active_at,open_alerts,severity_band"),
    ("get", "/patients/{patient_id}", None),
    ("post", "/patients/{patient_id}/pin", {"pin", "qr_token", "expires_at"}),
    ("post", "/caregiver-links", None),
    ("get", "/patients/{patient_id}/consents", None), ("post", "/patients/{patient_id}/consents", None),
    ("post", "/sync/push", {"accepted", "rejected", "server_cursor"}),
    ("get", "/sync/pull", {"changes", "server_cursor"}),
    ("post", "/coop/rooms", {"room_id", "join_code", "expires_at"}),
    ("post", "/coop/rooms/join", {"room_id", "ws_token"}),
    ("post", "/media", {"id", "patient_id", "uploader_id", "kind", "mime", "size_bytes", "tags", "created_at"}),
    ("get", "/patients/{patient_id}/media", None),
    ("get", "/media/{media_id}/url", {"url", "expires_at"}),
    ("get", "/media/{media_id}/content", None),
    ("get", "/alerts", "[]:id,patient_id,kind,severity,message,created_at,acknowledged_at"),
    ("post", "/alerts/{alert_id}/ack", None),
    ("get", "/patients/{patient_id}/dashboard/trends", {"days"}),
    ("get", "/patients/{patient_id}/dashboard/cue-comparison", {"with_cue", "without_cue", "by_domain"}),
    ("get", "/patients/{patient_id}/dashboard/triggers", "[]:cue_id,cue_type,valence_label,confidence,last_validated_at,half_life_days"),
    ("get", "/patients/{patient_id}/dashboard/severity", {"band", "gds_style_indicator", "drivers", "disclaimer", "computed_at"}),
    ("get", "/patients/{patient_id}/report.csv", None),
]
for kind in ("reminders", "routines"):
    b = f"/patients/{{patient_id}}/{kind}"
    ROUTES += [("get", b, None), ("post", b, None), ("put", b + "/{item_id}", None), ("delete", b + "/{item_id}", None)]
EXTRA = {"/ws/coop/{room_id}"}  # websocket: not in OpenAPI


def resolve(spec, schema):
    while schema and "$ref" in schema:
        schema = spec["components"]["schemas"][schema["$ref"].split("/")[-1]]
    return schema or {}


def props(spec, schema):
    schema = resolve(spec, schema)
    out = set(schema.get("properties", {}))
    for sub in schema.get("allOf", []):
        out |= props(spec, sub)
    return out


def norm(path):  # path-parameter names differ between modules ({id} vs {patient_id}): compare by position
    import re
    return re.sub(r"\{[^}]+\}", "{}", path)


def main():
    if len(sys.argv) > 1:
        spec = json.loads(Path(sys.argv[1]).read_text())
    else:
        os.environ["ENVIRONMENT"] = "development"
        from app.main import app
        spec = app.openapi()
    have = {}
    for path, item in spec["paths"].items():
        for m, op in item.items():
            if m in ("get", "post", "put", "delete", "patch"):
                have[(m, norm(path[len(P):] if path.startswith(P) else path))] = (path, op)
    problems = []
    want = set()
    for m, path, shape in ROUTES:
        key = (m, norm(path))
        want.add(key)
        if key not in have:
            problems.append(f"MISSING  {m.upper()} {P}{path}")
            continue
        if not shape:
            continue
        op = have[key][1]
        ok = [c for c in op.get("responses", {}) if c.startswith("2")]
        content = (op["responses"][ok[0]].get("content", {}).get("application/json", {}) if ok else {}).get("schema")
        if content is None:
            problems.append(f"NO-SCHEMA {m.upper()} {P}{path}: response model not declared")
            continue
        if isinstance(shape, str):
            keys = set(shape.split(":")[1].split(","))
            item = resolve(spec, content).get("items")
            got = props(spec, item) if item else set()
        else:
            keys, got = shape, props(spec, content)
        if keys - got:
            problems.append(f"SHAPE    {m.upper()} {P}{path}: missing response keys {sorted(keys - got)}")
    extras = sorted(f"{m.upper()} {p}" for (m, p) in have if (m, p) not in want and not p.startswith(("/healthz", "/readyz")))
    print(f"ROUTES expected: {len(want)}  OpenAPI operations: {len(have)}")
    for p in problems:
        print(p)
    for e in extras:
        print(f"EXTRA    {e}  (not in ROUTES; allowed, listed for review)")
    print("RESULT:", "DIFFERENCES FOUND" if problems else "OK (every ROUTES path/method/shape present)")
    sys.exit(1 if problems else 0)


main()
