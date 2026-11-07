"""Pure validation helpers for the media / reminders / routines module.

No FastAPI or SQLAlchemy imports, so everything here is unit-testable on its own and the
rules can be ported to other runtimes. Upload failures raise ``MediaValidationError``
carrying the HTTP status the router should return.
"""

import io
import json
import re
from datetime import datetime, timezone

# ---------------------------------------------------------------- media limits

PHOTO_MIMES = frozenset({"image/jpeg", "image/png", "image/webp"})
AUDIO_MIMES = frozenset(
    {
        "audio/mpeg",
        "audio/mp4",
        "audio/x-m4a",
        "audio/aac",
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/ogg",
        "audio/webm",
    }
)
ALLOWED_MIMES = {"photo": PHOTO_MIMES, "audio": AUDIO_MIMES}
MAX_BYTES = {"photo": 10 * 1024 * 1024, "audio": 20 * 1024 * 1024}
MAX_IMAGE_PIXELS = 48_000_000  # decompression-bomb guard (~48 MP)

MAX_TAGS = 20
MAX_TAG_LEN = 50
MAX_TAGS_JSON_BYTES = 2048


class MediaValidationError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def validate_kind(kind: str | None) -> str:
    value = (kind or "").strip().lower()
    if value not in ALLOWED_MIMES:
        raise MediaValidationError(422, "kind must be 'photo' or 'audio'")
    return value


def normalize_mime(content_type: str | None) -> str:
    """'Audio/WebM; codecs=opus' -> 'audio/webm'."""
    return (content_type or "").split(";", 1)[0].strip().lower()


def validate_declared_mime(kind: str, content_type: str | None) -> str:
    mime = normalize_mime(content_type)
    if mime not in ALLOWED_MIMES[kind]:
        raise MediaValidationError(415, f"Unsupported media type '{mime or 'unknown'}' for kind '{kind}'")
    return mime


def read_limited(fileobj, kind: str) -> bytes:
    """Read an upload without ever holding more than limit+1 bytes. 413 if larger than the limit."""
    limit = MAX_BYTES[kind]
    data = fileobj.read(limit + 1)
    if len(data) > limit:
        raise MediaValidationError(413, f"File too large: {kind} limit is {limit // (1024 * 1024)} MB")
    if len(data) == 0:
        raise MediaValidationError(422, "File is empty")
    return data


def sniff_matches(mime: str, data: bytes) -> bool:
    """Check magic bytes so a declared Content-Type cannot disguise other content."""
    head = data[:16]
    if mime == "image/jpeg":
        return head[:3] == b"\xff\xd8\xff"
    if mime == "image/png":
        return head[:8] == b"\x89PNG\r\n\x1a\n"
    if mime == "image/webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if mime == "audio/mpeg":
        return head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0)
    if mime == "audio/aac":
        return head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xF6) == 0xF0)
    if mime in ("audio/wav", "audio/x-wav", "audio/wave"):
        return head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    if mime == "audio/ogg":
        return head[:4] == b"OggS"
    if mime == "audio/webm":
        return head[:4] == b"\x1a\x45\xdf\xa3"
    if mime in ("audio/mp4", "audio/x-m4a"):
        return head[4:8] == b"ftyp"
    return False


def check_content(mime: str, data: bytes) -> None:
    if not sniff_matches(mime, data):
        raise MediaValidationError(415, "File content does not match its declared type")


# ---------------------------------------------------------------- image metadata

_ORIENTATION_TAG = 0x0112


def strip_image_metadata(data: bytes) -> bytes:
    """Remove EXIF (including GPS) and XMP from a photo; keep only EXIF Orientation + ICC profile.

    * No-op (returns ``data`` unchanged) if Pillow is not installed, or if the image carries no
      EXIF/XMP at all (so clean files are never re-encoded).
    * JPEG is re-saved with quality="keep" / subsampling="keep" (re-uses the original quantization
      tables, so visual quality is preserved). WebP is re-saved at quality 95.
    * Raises MediaValidationError if the bytes are not a decodable, non-animated image.
    """
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:  # Pillow is optional per the assignment
        return data

    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > MAX_IMAGE_PIXELS:
            raise MediaValidationError(413, "Image dimensions are too large")
        if getattr(img, "is_animated", False):
            raise MediaValidationError(415, "Animated images are not supported")
        exif = img.getexif()
        has_xmp = "xmp" in img.info or "XML:com.adobe.xmp" in img.info
        if len(exif) == 0 and not has_xmp:
            img.load()  # still make sure it decodes
            return data
        orientation = exif.get(_ORIENTATION_TAG)
        clean_exif = Image.Exif()
        if orientation:
            clean_exif[_ORIENTATION_TAG] = orientation
        exif_bytes = clean_exif.tobytes() if orientation else b""
        fmt = img.format
        img.load()
        save_kwargs: dict = {}
        icc = img.info.get("icc_profile")
        if icc:
            save_kwargs["icc_profile"] = icc
        out = io.BytesIO()
        if fmt == "JPEG":
            img.save(out, "JPEG", quality="keep", subsampling="keep", exif=exif_bytes, **save_kwargs)
        elif fmt == "PNG":
            img.save(out, "PNG", exif=exif_bytes, **save_kwargs)
        elif fmt == "WEBP":
            img.save(out, "WEBP", quality=95, method=4, exif=exif_bytes, **save_kwargs)
        else:
            raise MediaValidationError(415, "Unsupported image format")
        return out.getvalue()
    except MediaValidationError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError, KeyError) as exc:
        raise MediaValidationError(415, "File is not a valid image") from exc


# ---------------------------------------------------------------- tags & steps

def _is_simple(value) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def parse_tags(raw: str | None):
    """Parse the multipart ``tags`` field into JSON-storable data.

    Accepts a JSON array of strings, a JSON object of simple values, or a comma separated list.
    """
    if raw is None or not raw.strip():
        return []
    text = raw.strip()
    if text[0] in "[{":
        try:
            value = json.loads(text)
        except ValueError as exc:
            raise MediaValidationError(422, "tags is not valid JSON") from exc
    else:
        value = [part.strip() for part in text.split(",") if part.strip()]

    if isinstance(value, list):
        if len(value) > MAX_TAGS or not all(isinstance(t, str) and 0 < len(t.strip()) <= MAX_TAG_LEN for t in value):
            raise MediaValidationError(422, f"tags: at most {MAX_TAGS} non-empty strings of {MAX_TAG_LEN} characters")
        value = [t.strip() for t in value]
    elif isinstance(value, dict):
        ok = len(value) <= MAX_TAGS and all(
            isinstance(k, str)
            and 0 < len(k) <= MAX_TAG_LEN
            and (_is_simple(v) and (not isinstance(v, str) or len(v) <= 200))
            for k, v in value.items()
        )
        if not ok:
            raise MediaValidationError(422, f"tags: at most {MAX_TAGS} keys with simple values")
    else:
        raise MediaValidationError(422, "tags must be a JSON array, object or comma separated list")

    if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > MAX_TAGS_JSON_BYTES:
        raise MediaValidationError(422, "tags are too large")
    return value


MAX_STEPS = 50
MAX_STEPS_JSON_BYTES = 16 * 1024


def normalize_steps(steps) -> list:
    """D1: canonical step shape is {"order": int, "title": str, "media_id"?: uuid}. Legacy plain strings (and
    objects missing `order`/`title`) are normalised on read and on write; unknown keys are kept."""
    out: list = []
    for i, item in enumerate(steps or [], start=1):
        if isinstance(item, str):
            out.append({"order": i, "title": item.strip()})
        elif isinstance(item, dict):
            step = dict(item)
            title = step.get("title", step.get("text", step.get("label", "")))
            step["title"] = str(title).strip()
            step["order"] = int(step["order"]) if isinstance(step.get("order"), (int, float)) else i
            step.pop("text", None)
            step.pop("label", None)
            if not step.get("media_id"):
                step.pop("media_id", None)
            out.append(step)
    return sorted(out, key=lambda x: x["order"])


def validate_steps(steps) -> list:
    """Routine steps are stored as JSON. Shape is not fixed by the contract: a list whose items are
    strings or flat-ish objects. Recommended item shape: {"order": int, "title": str, "media_id": uuid?}.
    """
    if not isinstance(steps, list) or not (1 <= len(steps) <= MAX_STEPS):
        raise ValueError(f"steps must be a list of 1 to {MAX_STEPS} items")
    for item in steps:
        if isinstance(item, str):
            if not item.strip():
                raise ValueError("step text must not be empty")
        elif isinstance(item, dict):
            if not item:
                raise ValueError("step objects must not be empty")
        else:
            raise ValueError("each step must be a string or an object")
    if len(json.dumps(steps, ensure_ascii=False).encode("utf-8")) > MAX_STEPS_JSON_BYTES:
        raise ValueError("steps are too large")
    normalized = normalize_steps(steps)
    if any(not st["title"] for st in normalized):
        raise ValueError("each step needs a non-empty title")
    return normalized


# ---------------------------------------------------------------- RRULE

MAX_RRULE_LEN = 1000
_FORBIDDEN_FREQ = {"SECONDLY", "MINUTELY"}  # a reminder every minute is spam, not care
_FREQ_RE = re.compile(r"FREQ=([A-Z]+)")


def validate_rrule(value: str) -> str:
    """Validate an iCalendar RRULE string with python-dateutil. Returns the stripped string.

    Accepted: 'FREQ=DAILY;BYHOUR=8;BYMINUTE=0', 'RRULE:FREQ=WEEKLY;BYDAY=MO,TH;BYHOUR=9',
    optionally preceded by a 'DTSTART:...' line. Rejects unparsable rules, rules without FREQ,
    SECONDLY/MINUTELY frequency, and rules that can never fire.
    Raises ValueError (pydantic turns this into a 422).
    """
    from dateutil.rrule import rrulestr

    if not isinstance(value, str):
        raise ValueError("schedule must be a string")
    text = value.strip()
    if not text:
        raise ValueError("schedule must not be empty")
    if len(text) > MAX_RRULE_LEN:
        raise ValueError(f"schedule is longer than {MAX_RRULE_LEN} characters")
    if any(ord(c) < 32 and c not in "\r\n" for c in text):
        raise ValueError("schedule contains control characters")

    freqs = _FREQ_RE.findall(text.upper())
    if not freqs:
        raise ValueError("schedule must contain FREQ=")
    bad = _FORBIDDEN_FREQ.intersection(freqs)
    if bad:
        raise ValueError(f"FREQ={sorted(bad)[0]} is too frequent for a reminder (use HOURLY or slower)")

    now = datetime.now()
    last_error: Exception | None = None
    rule = None
    # Floating UNTIL needs a naive DTSTART, UNTIL with 'Z' needs an aware one: try both.
    for dtstart in (now, now.replace(tzinfo=timezone.utc)):
        try:
            rule = rrulestr(text, dtstart=dtstart)
            break
        except Exception as exc:  # dateutil raises ValueError/TypeError/KeyError/... for bad input
            last_error = exc
    if rule is None:
        raise ValueError(f"invalid RRULE: {last_error}")
    try:
        first = next(iter(rule), None)
    except Exception as exc:
        raise ValueError(f"invalid RRULE: {exc}") from exc
    if first is None:
        raise ValueError("schedule never produces an occurrence")
    return text


# ---------------------------------------------------------------- misc

LOCALES = ("as", "bn", "ne", "brx", "mni", "en", "lus", "kha", "grt")  # last three: voice-pack-only
CATEGORIES = ("medicine", "hydration", "activity", "appointment")


def ensure_utc(value: datetime) -> datetime:
    """SQLite (tests) returns naive datetimes; Postgres returns aware. Always emit aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
