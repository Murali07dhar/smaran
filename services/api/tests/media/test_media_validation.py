import io
import uuid

import pytest

from app.modules.media import storage, validation as v
from app.modules.media.http_range import RangeNotSatisfiable, parse_range
from app.modules.media.ids import uuid7

MB = 1024 * 1024


# ---------- MIME / size / magic bytes ----------

def test_mime_allowlist():
    assert v.validate_declared_mime("photo", "image/jpeg") == "image/jpeg"
    assert v.validate_declared_mime("photo", "IMAGE/PNG; charset=binary") == "image/png"
    assert v.validate_declared_mime("audio", "audio/webm;codecs=opus") == "audio/webm"
    for kind, mime in [("photo", "image/gif"), ("photo", "image/svg+xml"), ("photo", "text/html"),
                       ("photo", "audio/mpeg"), ("audio", "image/jpeg"), ("audio", "video/mp4"),
                       ("audio", "application/octet-stream"), ("photo", None), ("photo", "")]:
        with pytest.raises(v.MediaValidationError) as err:
            v.validate_declared_mime(kind, mime)
        assert err.value.status_code == 415


def test_kind_validation():
    assert v.validate_kind(" Photo ") == "photo"
    with pytest.raises(v.MediaValidationError) as err:
        v.validate_kind("video")
    assert err.value.status_code == 422


@pytest.mark.parametrize("kind,limit", [("photo", 10 * MB), ("audio", 20 * MB)])
def test_size_limits(kind, limit):
    assert len(v.read_limited(io.BytesIO(b"a" * limit), kind)) == limit        # exactly at the limit: ok
    with pytest.raises(v.MediaValidationError) as err:
        v.read_limited(io.BytesIO(b"a" * (limit + 1)), kind)                    # one byte over: rejected
    assert err.value.status_code == 413


def test_read_limited_never_reads_more_than_limit_plus_one():
    class Spy(io.BytesIO):
        asked = None
        def read(self, n=-1):
            Spy.asked = n
            return super().read(n)
    v.read_limited(Spy(b"abc"), "photo")
    assert Spy.asked == 10 * MB + 1


def test_empty_file_rejected():
    with pytest.raises(v.MediaValidationError) as err:
        v.read_limited(io.BytesIO(b""), "audio")
    assert err.value.status_code == 422


def test_magic_bytes_must_match_declared_type(jpeg_bytes, wav_bytes):
    v.check_content("image/jpeg", jpeg_bytes())
    v.check_content("audio/wav", wav_bytes)
    v.check_content("audio/mpeg", b"ID3\x04\x00" + b"\x00" * 20)
    v.check_content("audio/webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 20)
    v.check_content("audio/ogg", b"OggS" + b"\x00" * 20)
    v.check_content("audio/mp4", b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 20)
    for mime, data in [("image/jpeg", b"<html><script>alert(1)</script>"), ("image/png", jpeg_bytes()),
                       ("audio/wav", b"MZ\x90\x00 an exe"), ("audio/mpeg", b"\x00\x00\x00\x00")]:
        with pytest.raises(v.MediaValidationError) as err:
            v.check_content(mime, data)
        assert err.value.status_code == 415


# ---------- EXIF / GPS ----------

PIL = pytest.importorskip("PIL")


def _exif_of(data):
    from PIL import Image
    return Image.open(io.BytesIO(data)).getexif()


def test_gps_is_stripped_but_orientation_kept(jpeg_bytes):
    original = jpeg_bytes(with_gps=True)
    assert 0x8825 in _exif_of(original)
    cleaned = v.strip_image_metadata(original)
    exif = _exif_of(cleaned)
    assert 0x8825 not in exif
    assert exif.get(0x0112) == 6


def test_image_without_metadata_is_returned_untouched(jpeg_bytes):
    clean = jpeg_bytes(with_gps=False)
    assert v.strip_image_metadata(clean) == clean


def test_corrupt_image_is_rejected():
    with pytest.raises(v.MediaValidationError) as err:
        v.strip_image_metadata(b"\xff\xd8\xff this is not really a jpeg")
    assert err.value.status_code == 415


def test_oversized_dimensions_rejected(monkeypatch, jpeg_bytes):
    monkeypatch.setattr(v, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(v.MediaValidationError) as err:
        v.strip_image_metadata(jpeg_bytes())
    assert err.value.status_code == 413


# ---------- tags / steps ----------

def test_tags_parsing():
    assert v.parse_tags(None) == []
    assert v.parse_tags("  ") == []
    assert v.parse_tags("family, wedding ,1998") == ["family", "wedding", "1998"]
    assert v.parse_tags('["a","b"]') == ["a", "b"]
    assert v.parse_tags('{"person": "Maa", "year": 1998}') == {"person": "Maa", "year": 1998}


@pytest.mark.parametrize("bad", ["[1,2]", "{oops", '["' + "x" * 51 + '"]', ",".join(str(i) for i in range(21)), '{"a": [1]}', '[""]'])
def test_bad_tags_rejected(bad):
    with pytest.raises(v.MediaValidationError) as err:
        v.parse_tags(bad)
    assert err.value.status_code == 422


def test_steps_validation():
    assert v.validate_steps(["wake", {"title": "brush teeth"}]) == [
        {"order": 1, "title": "wake"}, {"order": 2, "title": "brush teeth"}]  # D1: legacy strings normalised
    assert v.normalize_steps(["a"]) == [{"order": 1, "title": "a"}]
    for bad in ([], "x", [1], [""], [{}], ["s"] * 51, [{"t": "x" * 20000}]):
        with pytest.raises(ValueError):
            v.validate_steps(bad)


# ---------- RRULE ----------

@pytest.mark.parametrize("rule", [
    "FREQ=DAILY;BYHOUR=8;BYMINUTE=0",
    "RRULE:FREQ=WEEKLY;BYDAY=MO,TH;BYHOUR=9;BYMINUTE=30",
    "DTSTART:20261101T080000\nRRULE:FREQ=DAILY;COUNT=3",
    "FREQ=HOURLY;INTERVAL=2",
    "FREQ=DAILY;UNTIL=20301231T000000Z",
    "  FREQ=MONTHLY;BYMONTHDAY=1  ",
])
def test_valid_rrules(rule):
    assert v.validate_rrule(rule) == rule.strip()


@pytest.mark.parametrize("rule", [
    "", "   ", "hello", "BYHOUR=8", "FREQ=FOO", "FREQ=DAILY;BYHOUR=99", "RRULE:",
    "FREQ=SECONDLY", "FREQ=MINUTELY;INTERVAL=5",
    "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=30",          # never fires
    "FREQ=DAILY;UNTIL=20200101T000000Z",             # already over
    "FREQ=DAILY\x00", "FREQ=DAILY;" + "X" * 1100,
])
def test_invalid_rrules(rule):
    with pytest.raises(ValueError):
        v.validate_rrule(rule)


def test_rrule_must_be_a_string():
    with pytest.raises(ValueError):
        v.validate_rrule(None)  # type: ignore[arg-type]


# ---------- Range ----------

def test_range_parsing():
    assert parse_range(None, 100) is None
    assert parse_range("bytes=0-9", 100) == (0, 9)
    assert parse_range("bytes=90-", 100) == (90, 99)
    assert parse_range("bytes=-10", 100) == (90, 99)
    assert parse_range("bytes=50-5000", 100) == (50, 99)
    assert parse_range("bytes=-500", 100) == (0, 99)
    assert parse_range("bytes=0-1,5-6", 100) is None       # multi-range: ignored
    assert parse_range("items=0-1", 100) is None
    assert parse_range("bytes=9-3", 100) is None
    for bad in ("bytes=100-", "bytes=500-600", "bytes=-0"):
        with pytest.raises(RangeNotSatisfiable):
            parse_range(bad, 100)


# ---------- storage / ids ----------

def test_storage_round_trip_and_permissions(media_env):
    rel = storage.relative_path(uuid.uuid4(), uuid.uuid4())
    storage.write_ciphertext(rel, b"\x01\x02\x03")
    assert storage.read_ciphertext(rel) == b"\x01\x02\x03"
    full = media_env["dir"].resolve() / rel
    assert oct(full.stat().st_mode & 0o777) == "0o600"
    assert not [p for p in full.parent.iterdir() if p.name.startswith(".tmp-")]
    storage.remove_ciphertext(rel)
    storage.remove_ciphertext(rel)  # idempotent
    with pytest.raises(FileNotFoundError):
        storage.read_ciphertext(rel)


def test_storage_blocks_path_traversal():
    with pytest.raises(ValueError):
        storage.read_ciphertext("../../etc/passwd")


def test_uuid7_shape_and_order():
    a = uuid7(now_ms=1_700_000_000_000)
    b = uuid7(now_ms=1_700_000_000_001)
    assert a.version == 7 and a.variant == uuid.RFC_4122
    assert a < b
    assert uuid7() != uuid7()
