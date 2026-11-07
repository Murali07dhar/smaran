"""Pure-logic tests (no FastAPI / SQLAlchemy / Redis needed)."""
import importlib.util
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

API = Path(__file__).resolve().parents[2]


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, API / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rules = _load("app/modules/sync/rules.py", "_sync_rules")
protocol = _load("app/modules/coop/protocol.py", "_coop_protocol")

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_lww_higher_version_wins():
    assert rules.lww_decision(3, T0, 4, T0) == (True, 4)


def test_lww_lower_version_is_stale():
    assert rules.lww_decision(3, T0, 2, T0 + timedelta(days=1))[0] is False


def test_lww_tie_uses_client_ts_and_bumps_version():
    assert rules.lww_decision(3, T0, 3, T0 + timedelta(seconds=5)) == (True, 4)
    assert rules.lww_decision(3, T0, 3, T0 - timedelta(seconds=5))[0] is False


def test_lww_handles_naive_stored_timestamp():
    naive = datetime(2026, 1, 1)  # e.g. SQLite round-trip
    assert rules.lww_decision(1, naive, 1, T0 + timedelta(seconds=1)) == (True, 2)


def test_to_jsonable_converts_uuid_datetime_decimal():
    u = uuid.uuid4()
    out = rules.to_jsonable({"id": u, "at": T0, "n": Decimal("1.5"), "s": {2, 1}})
    assert out == {"id": str(u), "at": "2026-01-01T00:00:00Z", "n": 1.5, "s": [1, 2]}


def test_sanitize_hides_media_secrets_only_for_media():
    p = {"id": "x", "enc_path": "/p", "nonce": "n", "mime": "image/png"}
    assert rules.sanitize_pull_payload("media_assets", p) == {"id": "x", "mime": "image/png"}
    assert rules.sanitize_pull_payload("reminders", p) == p


def test_apply_order_parents_first():
    order = sorted(["game_events", "game_sessions", "reminder_events", "reminders"], key=rules.apply_priority)
    assert order == ["reminders", "game_sessions", "reminder_events", "game_events"]


def test_entity_classification():
    assert "game_events" in rules.APPEND_ONLY_ENTITIES and "reminders" in rules.LWW_ENTITIES
    assert "alerts" not in rules.PUSHABLE_ENTITIES and "alerts" in rules.KNOWN_ENTITIES


# ---- co-op protocol --------------------------------------------------------
def test_join_code_shape_and_alphabet():
    for _ in range(500):
        c = protocol.generate_join_code()
        assert len(c) == 6 and set(c) <= set(protocol.JOIN_CODE_ALPHABET)
        assert not set(c) & set("ILO01")


def test_join_code_normalisation():
    assert protocol.normalize_join_code(" abc-234 ") == "ABC234"
    assert protocol.normalize_join_code("ABC10O") is None  # ambiguous characters are never valid
    assert protocol.normalize_join_code("ABC") is None
    assert protocol.normalize_join_code("") is None


def test_client_message_validation():
    assert protocol.validate_client_message('{"type":"hint","seq":99,"payload":{"x":1}}') == ("hint", {"x": 1})
    assert protocol.validate_client_message('{"type":"encourage"}') == ("encourage", {})
    for bad in ('not json', '[]', '{"type":"join"}', '{"type":"hint","payload":[1]}', '{"type":"leave"}'):
        try:
            protocol.validate_client_message(bad)
        except protocol.ProtocolError:
            continue
        raise AssertionError(f"accepted {bad!r}")
    try:
        protocol.validate_client_message('{"type":"hint","payload":{"a":"' + "x" * 20000 + '"}}')
    except protocol.ProtocolError as e:
        assert e.code == "message_too_large"
    else:
        raise AssertionError("oversized message accepted")
