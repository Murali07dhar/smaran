"""API tests for /media (need fastapi, sqlalchemy, httpx, python-multipart, Pillow)."""
import io
import time
import uuid

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
pytest.importorskip("httpx")

from app.core import crypto
from app.modules.media import signing
from app.modules.sync import changelog

MB = 1024 * 1024


def upload(client, patient, *, kind="photo", content=b"", mime="image/jpeg", tags=None, name="f.bin"):
    data = {"patient_id": str(patient.id), "kind": kind}
    if tags is not None:
        data["tags"] = tags
    return client.post("/api/v1/media", data=data, files={"file": (name, io.BytesIO(content), mime)})


def disk_files(media_env):
    return sorted(media_env["dir"].rglob("*.enc")) if media_env["dir"].exists() else []


# ------------------------------------------------------------ happy path & encryption at rest

def test_upload_encrypts_on_disk_and_round_trips(client_for, world, media_env, jpeg_bytes):
    plain = jpeg_bytes()
    c = client_for(world["cg"])
    r = upload(c, world["patient"], content=plain, tags="family,wedding")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "photo" and body["mime"] == "image/jpeg"
    assert body["tags"] == ["family", "wedding"]
    assert body["size_bytes"] == len(plain)
    assert body["uploader_id"] == str(world["cg"].id)
    assert "enc_path" not in body and "nonce" not in body

    (path,) = disk_files(media_env)
    raw = path.read_bytes()
    assert plain not in raw and raw[:3] != b"\xff\xd8\xff"          # unreadable without the key
    assert path.parent.name == str(world["patient"].id)

    # row stores nonce + relative path; ciphertext + nonce decrypt back to the original
    from app.models import MediaAsset
    with world["Session"]() as s:
        asset = s.get(MediaAsset, uuid.UUID(body["id"]))
        assert not asset.enc_path.startswith("/")
        assert crypto.decrypt_bytes(raw, asset.nonce) == plain

    url = c.get(f"/api/v1/media/{body['id']}/url").json()["url"]
    got = c.get(url)
    assert got.status_code == 200
    assert got.content == plain
    assert got.headers["content-type"] == "image/jpeg"
    assert got.headers["cache-control"] == "private, no-store"
    assert got.headers["x-content-type-options"] == "nosniff"


def test_record_change_called_for_media_creation_without_secrets(client_for, world, jpeg_bytes):
    c = client_for(world["cg"])
    body = upload(c, world["patient"], content=jpeg_bytes()).json()
    assert len(changelog.CALLS) == 1
    call = changelog.CALLS[0]
    assert (call["entity"], call["action"]) == ("media_assets", "upsert")
    assert str(call["entity_id"]) == body["id"] and call["patient_id"] == world["patient"].id
    assert call["payload"]["id"] == body["id"]
    assert not {"enc_path", "nonce"} & set(call["payload"])


def test_gps_removed_from_stored_photo(client_for, world, jpeg_bytes):
    from PIL import Image
    c = client_for(world["cg"])
    body = upload(c, world["patient"], content=jpeg_bytes(with_gps=True)).json()
    served = c.get(c.get(f"/api/v1/media/{body['id']}/url").json()["url"]).content
    exif = Image.open(io.BytesIO(served)).getexif()
    assert 0x8825 not in exif and exif.get(0x0112) == 6


def test_list_media_for_patient_and_caregiver(client_for, world, jpeg_bytes):
    upload(client_for(world["cg"]), world["patient"], content=jpeg_bytes())
    for user in (world["cg"], world["patient"], world["hw"]):
        r = client_for(user).get(f"/api/v1/patients/{world['patient'].id}/media")
        assert r.status_code == 200 and len(r.json()) == 1


def test_audio_range_requests(client_for, world, wav_bytes):
    c = client_for(world["cg"])
    body = upload(c, world["patient"], kind="audio", content=wav_bytes, mime="audio/wav").json()
    url = c.get(f"/api/v1/media/{body['id']}/url").json()["url"]
    full = c.get(url)
    assert full.headers["accept-ranges"] == "bytes" and full.content == wav_bytes
    part = c.get(url, headers={"Range": "bytes=0-9"})
    assert part.status_code == 206 and part.content == wav_bytes[:10]
    assert part.headers["content-range"] == f"bytes 0-9/{len(wav_bytes)}"
    assert c.get(url, headers={"Range": f"bytes={len(wav_bytes) + 5}-"}).status_code == 416


# ------------------------------------------------------------ signed URL abuse

def _content_url(c, media_id, sig, exp):
    return f"/api/v1/media/{media_id}/content?sig={sig}&exp={exp}"


def test_signed_url_shape_and_expiry_window(client_for, world, jpeg_bytes):
    c = client_for(world["cg"])
    mid = upload(c, world["patient"], content=jpeg_bytes()).json()["id"]
    r = c.get(f"/api/v1/media/{mid}/url").json()
    assert f"/media/{mid}/content?sig=" in r["url"] and "&exp=" in r["url"]
    exp_ts = int(r["url"].rsplit("exp=", 1)[1])
    assert abs(exp_ts - (time.time() + 600)) < 15


def test_expired_forged_and_tampered_urls_are_refused(client_for, world, jpeg_bytes):
    c = client_for(world["cg"])
    mid = upload(c, world["patient"], content=jpeg_bytes()).json()["id"]

    sig, exp = signing.make_signature(uuid.UUID(mid), now=time.time() - 7200)
    expired = c.get(_content_url(c, mid, sig, exp))
    assert expired.status_code == 403 and "expired" in expired.json()["detail"].lower()

    sig, exp = signing.make_signature(uuid.UUID(mid))
    assert c.get(_content_url(c, mid, "A" * 43, exp)).status_code == 403          # forged
    assert c.get(_content_url(c, mid, sig, exp + 3600)).status_code == 403        # extended expiry
    other = upload(c, world["patient"], content=jpeg_bytes()).json()["id"]
    assert c.get(_content_url(c, other, sig, exp)).status_code == 403              # sig for another asset
    assert c.get(f"/api/v1/media/{mid}/content").status_code == 422               # missing params
    assert c.get(_content_url(c, mid, sig, exp)).status_code == 200                # control: genuine one works


def test_content_route_needs_no_bearer_but_url_route_does(client_for, world, jpeg_bytes):
    from fastapi.testclient import TestClient

    from app.core.security import get_current_user

    c = client_for(world["cg"])
    mid = upload(c, world["patient"], content=jpeg_bytes()).json()["id"]
    url = c.get(f"/api/v1/media/{mid}/url").json()["url"]
    c.app.dependency_overrides.pop(get_current_user)       # from here on: no logged-in user
    anon = TestClient(c.app)
    assert anon.get(url).status_code == 200                          # <img src> works without headers
    assert anon.get(f"/api/v1/media/{mid}/url").status_code == 401   # but minting a URL needs auth


def test_tampered_ciphertext_on_disk_is_never_served(client_for, world, media_env, jpeg_bytes):
    c = client_for(world["cg"])
    mid = upload(c, world["patient"], content=jpeg_bytes()).json()["id"]
    url = c.get(f"/api/v1/media/{mid}/url").json()["url"]
    (path,) = disk_files(media_env)
    raw = bytearray(path.read_bytes())
    raw[3] ^= 0xFF
    path.write_bytes(bytes(raw))
    r = c.get(url)
    assert r.status_code == 500 and "integrity" in r.json()["detail"].lower()


def test_missing_file_on_disk_is_404(client_for, world, media_env, jpeg_bytes):
    c = client_for(world["cg"])
    mid = upload(c, world["patient"], content=jpeg_bytes()).json()["id"]
    url = c.get(f"/api/v1/media/{mid}/url").json()["url"]
    disk_files(media_env)[0].unlink()
    assert c.get(url).status_code == 404


def test_unknown_media_id(client_for, world):
    c = client_for(world["cg"])
    assert c.get(f"/api/v1/media/{uuid.uuid4()}/url").status_code == 404
    ghost = uuid.uuid4()
    sig, exp = signing.make_signature(ghost)
    assert c.get(_content_url(c, ghost, sig, exp)).status_code == 404          # genuine signature, no such asset
    assert c.get(_content_url(c, uuid.uuid4(), sig, exp)).status_code == 403   # signature for a different id


# ------------------------------------------------------------ limits & validation

def test_photo_size_limit(client_for, world, media_env):
    c = client_for(world["cg"])
    too_big = b"\xff\xd8\xff" + b"0" * (10 * MB)              # 10 MB + 3 bytes
    assert upload(c, world["patient"], content=too_big).status_code == 413
    assert not disk_files(media_env) and not changelog.CALLS


def test_audio_limit_is_larger_than_photo_limit(client_for, world, media_env):
    c = client_for(world["cg"])
    too_big = b"OggS" + b"0" * (20 * MB)
    assert upload(c, world["patient"], kind="audio", content=too_big, mime="audio/ogg").status_code == 413
    ok = b"OggS" + b"0" * (11 * MB)                            # > photo limit, < audio limit
    assert upload(c, world["patient"], kind="audio", content=ok, mime="audio/ogg").status_code == 201


@pytest.mark.parametrize("kind,mime,content,expected", [
    ("photo", "image/gif", b"GIF89a....", 415),
    ("photo", "text/html", b"<html>", 415),
    ("photo", "image/jpeg", b"<html><script>x</script></html>", 415),   # spoofed content type
    ("photo", "image/jpeg", b"\xff\xd8\xff not a real jpeg", 415),
    ("audio", "image/jpeg", b"\xff\xd8\xff", 415),
    ("video", "video/mp4", b"....ftyp", 422),
    ("photo", "image/jpeg", b"", 422),
])
def test_rejected_uploads(client_for, world, media_env, kind, mime, content, expected):
    r = upload(client_for(world["cg"]), world["patient"], kind=kind, mime=mime, content=content)
    assert r.status_code == expected, r.text
    assert not disk_files(media_env) and not changelog.CALLS


def test_bad_tags_rejected(client_for, world, jpeg_bytes):
    r = upload(client_for(world["cg"]), world["patient"], content=jpeg_bytes(), tags="{not json")
    assert r.status_code == 422


# ------------------------------------------------------------ RBAC

def test_only_caregivers_and_health_workers_may_upload(client_for, world, jpeg_bytes):
    assert upload(client_for(world["patient"]), world["patient"], content=jpeg_bytes()).status_code == 403
    assert upload(client_for(world["hw"]), world["patient"], content=jpeg_bytes()).status_code == 201


def test_unlinked_caregiver_has_no_access(client_for, world, jpeg_bytes):
    owner = client_for(world["cg"])
    mid = upload(owner, world["patient"], content=jpeg_bytes()).json()["id"]
    n_calls = len(changelog.CALLS)
    intruder = client_for(world["other_cg"])
    assert upload(intruder, world["patient"], content=jpeg_bytes()).status_code == 403
    assert intruder.get(f"/api/v1/patients/{world['patient'].id}/media").status_code == 403
    assert intruder.get(f"/api/v1/media/{mid}/url").status_code == 403
    assert len(changelog.CALLS) == n_calls


def test_patient_cannot_read_another_patients_media(client_for, world, jpeg_bytes):
    mid = upload(client_for(world["cg"]), world["patient"], content=jpeg_bytes()).json()["id"]
    from app.models import User
    stranger = User(id=uuid.uuid4(), role="patient", name="S", language="en")
    c = client_for(stranger)
    assert c.get(f"/api/v1/patients/{world['patient'].id}/media").status_code == 403
    assert c.get(f"/api/v1/media/{mid}/url").status_code == 403


# ------------------------------------------------------------ failure atomicity

def test_no_orphan_ciphertext_when_change_log_fails(client_for, world, media_env, jpeg_bytes, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("changelog down")
    c = client_for(world["cg"])
    with monkeypatch.context() as m:
        m.setattr(changelog, "record_change", boom)
        with pytest.raises(RuntimeError):
            upload(c, world["patient"], content=jpeg_bytes())
    assert not disk_files(media_env)
    assert c.get(f"/api/v1/patients/{world['patient'].id}/media").json() == []


def test_missing_encryption_key_returns_clean_500(client_for, world, jpeg_bytes, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "MEDIA_KEY_B64", "", raising=False)
    r = upload(client_for(world["cg"]), world["patient"], content=jpeg_bytes())
    assert r.status_code == 500 and "not configured" in r.json()["detail"]
