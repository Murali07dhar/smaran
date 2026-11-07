"""packages/contracts/src/domain.ts must mirror app/models.py (fields, nullability, enums, no secrets)."""
import re
from pathlib import Path

import pytest

from app import models as m
from app.core.db import Base

DOMAIN_TS = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "src" / "domain.ts"
SECRET_COLUMNS = {"User": {"password_hash", "pin_hash"}, "MediaAsset": {"enc_path", "nonce"}}

pytestmark = pytest.mark.skipif(not DOMAIN_TS.exists(), reason="packages/contracts not present")


def parse_interfaces() -> dict[str, dict[str, str]]:
    src = DOMAIN_TS.read_text()
    out = {}
    for name, body in re.findall(r"export interface (\w+) \{\n(.*?)\n\}", src, flags=re.S):
        fields = {}
        for line in body.splitlines():
            mt = re.match(r"\s+(\w+)(\?)?:\s*(.+?);\s*$", line)
            if mt and mt.group(1) != "[extra":
                fields[mt.group(1)] = mt.group(3)
        out[name] = fields
    return out


IFACES = parse_interfaces() if DOMAIN_TS.exists() else {}


@pytest.mark.parametrize("model", m.ALL_MODELS, ids=lambda c: c.__name__)
def test_interface_matches_model(model):
    assert model.__name__ in IFACES, f"domain.ts lacks interface {model.__name__}"
    table = Base.metadata.tables[model.__tablename__]
    hidden = SECRET_COLUMNS.get(model.__name__, set())
    expected = {c.name: c for c in table.columns if c.name not in hidden}
    got = IFACES[model.__name__]
    assert set(got) == set(expected), f"{model.__name__}: ts={sorted(got)} db={sorted(expected)}"
    for name, col in expected.items():
        nullable_in_ts = "| null" in got[name]
        assert nullable_in_ts == (col.nullable and not col.primary_key), f"{model.__name__}.{name} nullability differs"


@pytest.mark.parametrize("const,values", [
    ("ROLES", m.ROLES), ("LOCALES", m.LOCALES), ("VOICE_PACK_LOCALES", m.VOICE_PACK_LOCALES),
    ("CONSENT_KINDS", m.CONSENT_KINDS), ("MEDIA_KINDS", m.MEDIA_KINDS), ("REMINDER_CATEGORIES", m.REMINDER_CATEGORIES),
    ("REMINDER_EVENT_STATUSES", m.REMINDER_EVENT_STATUSES), ("GAME_DOMAINS", m.GAME_DOMAINS),
    ("EMOTION_LABELS", m.EMOTION_LABELS), ("EMOTION_SOURCES", m.EMOTION_SOURCES), ("ALERT_KINDS", m.ALERT_KINDS),
    ("ALERT_SEVERITIES", m.ALERT_SEVERITIES), ("SYNC_ACTIONS", m.SYNC_ACTIONS),
])
def test_enum_constants_match(const, values):
    match = re.search(rf"export const {const} = \[(.*?)\] as const", DOMAIN_TS.read_text(), flags=re.S)
    assert match, const
    assert tuple(re.findall(r'"([^"]+)"', match.group(1))) == tuple(values)


def test_no_secret_fields_in_wire_types():
    for iface, cols in SECRET_COLUMNS.items():
        assert not (cols & set(IFACES[iface]))
