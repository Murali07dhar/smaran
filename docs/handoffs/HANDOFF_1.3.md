# HANDOFF: Claude 1.3 (Media, Reminders, Routines)

## Test status (read this first)
The sandbox had no network, so FastAPI, SQLAlchemy and pytest could not be installed.
- **Executed and passing: 66 tests** (crypto, URL signing, MIME/magic-byte/size limits, EXIF GPS stripping, tags/steps, RRULE validation, Range parsing, storage, UUIDv7). They ran through a small pytest stand-in, not real pytest; they use only plain pytest features.
- **Written but NOT executed: the API tests** (`test_media_api.py`, `test_media_reminders_routines_api.py`: upload/decrypt round trip, forged/expired URLs, RBAC, server_version bumps, `record_change` per write, rollback on failure). All route code compiles, and I reviewed it by hand. The Integrator should run `pytest services/api/tests/media` first and expect possible small fixes there.

## What is built
- `services/api/app/core/crypto.py`: `encrypt_bytes(data) -> (ciphertext, nonce)` and `decrypt_bytes(ciphertext, nonce) -> bytes`, AES-256-GCM, key from `settings.MEDIA_KEY_B64` (32 bytes, base64). Tamper, wrong key or wrong nonce raises `CryptoError`. Also `derive_subkey(label)` (separate HMAC key for URL signing) and `generate_key_b64()`.
- `services/api/app/modules/media/`
  - `router.py` exposes `router` (media + reminders + routines). Wire with `app.include_router(router, prefix="/api/v1")`.
  - `media_routes.py`, `reminders_routes.py`, `routines_routes.py`, `schemas.py`, `validation.py`, `signing.py`, `storage.py`, `http_range.py`, `ids.py` (UUIDv7), `common.py`.
- `mocks/core_stub/`: stand-ins for `app.core.{config,db,security}`, `app.models` (User, CaregiverLink, MediaAsset, Reminder, Routine) and a fake `app.modules.sync.changelog.record_change` that appends to `CALLS`. The Integrator deletes this folder; the tests then pick up the real modules.
- `services/api/tests/media/`: tests plus conftest. `requirements.media.txt`, `.env.media.example`.

## How to run
```
cd services/api
pip install -r requirements.media.txt fastapi "sqlalchemy>=2" "pydantic>=2"
export MEDIA_KEY_B64=$(python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())")
export MEDIA_DIR=/data/media            # must be a mounted volume in Docker
pytest tests/media -q                   # tests generate their own temporary key and directory
```
Env vars: `MEDIA_KEY_B64` (required), `MEDIA_DIR` (default `./media_data`), `MEDIA_URL_TTL_SECONDS` (default 600).

## Endpoints (all under /api/v1)
| Route | Who | Notes |
|---|---|---|
| `POST /media` multipart `patient_id, kind, file, tags` | caregiver, health_worker with patient access | 201 media JSON `{id, patient_id, uploader_id, kind, mime, size_bytes, tags, created_at}`. Never returns `enc_path` or `nonce`. |
| `GET /patients/{id}/media` | anyone with patient access | newest first |
| `GET /media/{id}/url` | anyone with patient access | `{url, expires_at}`, 10 min. `url` is **relative** (`/api/v1/media/{id}/content?sig=..&exp=..`). Prefix your API base. |
| `GET /media/{id}/content?sig=&exp=` | holder of a valid signed URL (no bearer) | decrypts and streams, supports `Range` (needed by Safari/iOS audio), `Cache-Control: private, no-store` |
| `GET/POST /patients/{id}/reminders`, `PUT/DELETE /patients/{id}/reminders/{item_id}` | read: access; write: caregiver, health_worker | |
| `GET/POST /patients/{id}/routines`, `PUT/DELETE /patients/{id}/routines/{item_id}` | same | |

Behaviour:
- Limits: photo 10 MB (jpeg, png, webp), audio 20 MB (mpeg, mp4, x-m4a, aac, wav, x-wav, wave, ogg, webm). The declared MIME must be allowed **and** the magic bytes must match, otherwise 415. Too large is 413. Empty is 422.
- Photos: all EXIF/XMP is removed (GPS included) except the Orientation tag and ICC profile. Files with no metadata are stored untouched. No-op if Pillow is missing.
- Signed URL: `HMAC-SHA256(derived_key, "<media_id>.<exp>")`, checked in constant time before any DB or disk access. Forged or expired is 403.
- Reminders: `schedule` is validated with python-dateutil. It must contain `FREQ`, `SECONDLY`/`MINUTELY` are rejected, and a rule that never fires is rejected. `server_version` starts at 1 and bumps on every PUT. Rows are locked with `SELECT ... FOR UPDATE` during edits.
- Every create, update and delete of reminders, routines and media_assets calls `changelog.record_change(...)` in the same transaction as the write. If it raises, the write is rolled back (and the ciphertext file deleted for uploads).
- POST accepts an optional client-generated `id`; a duplicate id returns 409. Without an id the server generates a UUIDv7.

## Mocks used and what replaces them
| Mock | Replaced by |
|---|---|
| `core_stub/app/core/config.py`, `db.py`, `security.py`, `models.py` | 1.1's real files |
| `core_stub/app/modules/sync/changelog.py` | 1.4's real `record_change` |

## CONTRACT CHANGE REQUESTS / assumptions (labelled, nothing in the contract was edited)
1. **Settings**: add `MEDIA_DIR` (and optionally `MEDIA_URL_TTL_SECONDS`) to `app.core.config.Settings` and to `.env.example`. Until then I read them with `getattr(settings, ...)` falling back to `os.environ`, so the module works either way. **1.5 (infra)**: mount a persistent volume at `MEDIA_DIR` and set the reverse proxy body limit to about 21 MB. Starlette buffers the whole upload before my handler runs, so the 10/20 MB check cannot stop a huge upload by itself.
2. **Column types**: `media_assets.nonce` = `LargeBinary` (12 raw bytes; the code also tolerates a base64 string), `media_assets.enc_path` = `String` holding a path **relative** to `MEDIA_DIR`, `tags` = `JSON` (list of strings or flat object).
3. **Reminder JSON** uses the REMINDER contract name `schedule`; the DB column is `schedule_rrule`. Input also accepts `schedule_rrule`. Output adds `active` and `updated_at` beyond the contract. `escalate_after_misses` defaults to 3, with 0 meaning never escalate.
4. **sync entity names** are `reminders`, `routines`, `media_assets` (constants in `common.py`). Delete payload: `{id, patient_id, server_version}`. Media payload is metadata only. I assume `record_change` adds to the session and does **not** commit.
5. **Errors**: I raise `HTTPException`; I rely on 1.1's global handler to emit RFC 7807.
6. **RBAC**: `get_current_user` + `assert_can_access_patient` are used, but the writer check is a local role test (`caregiver`/`health_worker`), not `require_roles`, because its return type was not specified. `admin` cannot write (per the assignment text).
7. `voice_clip_id`: if it matches a media asset it must be an **audio** asset of the same patient (else 422); an id that matches no asset is accepted and assumed to be a voice-pack clip from services/voice.
8. `routines.steps` shape is free-form: a list (1 to 50) of strings or objects. Suggested item: `{order, title, media_id?}`. Claude 4/5/3 should agree on one shape.
9. **Missing endpoint**: there is no `DELETE /media/{id}` in ROUTES and `media_assets` has no `updated_at`/`server_version`, so a caregiver cannot remove or retag an uploaded photo. Request: add `DELETE /media/{id}` (delete file + row + `record_change(..., 'delete', ...)`).

## Known gaps and honest limits
- API tests unexecuted (see top). Postgres-specific behaviour (`FOR UPDATE`, timezone-aware columns) is untested; tests use SQLite.
- **No key rotation**: ciphertext does not store a key id. Changing `MEDIA_KEY_B64` makes existing media unreadable; losing it is unrecoverable. Back the key up in a secret manager. Rotation needs a `key_id` column plus a re-encrypt job.
- The signed content URL is a bearer capability valid for 10 minutes; anyone who gets it can fetch the file. The proxy should not log query strings for `/media/*/content`.
- Decryption is whole-file in memory (max 20 MB per request); AES-GCM was chosen over streaming for simplicity.
- Only EXIF/XMP is stripped from photos. Audio metadata (ID3 etc.) is not touched. There is no malware or content scanning. HEIC is not accepted. WebP photos with metadata are re-encoded at quality 95 (small quality loss).
- No consent check: uploads do not verify a `data_sharing` consent record. Deleting a patient does not remove their files (DPDP erasure needs a cleanup job).
- No rate limiting on uploads.
- Offline: patient devices receive media **metadata** via sync. The content must be fetched via `/url` while online and cached by the app (IndexedDB / file system).
- Voice and translated text are not handled here (services/voice).

## PORTABILITY NOTES
- **Reusable as-is for the React Native app**: the whole module is backend/API-first, bearer-token based, versioned `/api/v1`, JSON only. Signed relative URLs work with RN `Image`/audio players (`Range` is supported, which ExoPlayer/AVPlayer require). Reminder JSON equals the REMINDER contract, so the client reminder engine (`packages/voice-i18n/core`) can consume it unchanged.
- **Needs rewriting for React Native**: nothing in this workstream.
- **Adapters defined**: none (backend only). Clients should fetch media through their `FileAdapter` (cache signed-URL downloads) and `AudioAdapter` (play from a cached file or signed URL).
