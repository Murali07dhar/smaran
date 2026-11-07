# HANDOFF: SMARAN AI engine (Claude 2 of 6), `services/ai`, port 8001

Support tool, never a diagnosis. Wherever severity appears, show the disclaimer returned by the API.

## 1. What is built (and how far it was verified)

| Area | State | Evidence |
|---|---|---|
| 5 contract endpoints | Built, schema-checked | 85 pytest tests pass, `ruff check` clean, live uvicorn + `scripts/mock_client.py` all 200 |
| Trigger engine (Beta, decay, River half-life) | Built | Tests plus `scripts/demo_trigger_decay.py` (rises, then decays; `docs/trigger_demo.csv/.png`) |
| Difficulty adapter (River) | Built | Tests |
| Severity (rules, 1-7, band, disclaimer) | Built | Tests, plus synthetic evaluation |
| Emotion fusion + per-patient calibration | Built | Tests |
| Gemini content + template fallback | Built | Tests with Gemini mocked. **Never called against the real API** (no key) |
| Synthetic data generator | Built | `python -m ml.synthetic` |
| MLflow tracking | Wrapper built, JSON fallback used | MLflow itself not installed or exercised here |
| FER CNN training + ONNX export | Script written, **never run** (no torch, no FER-2013) | |
| Smoke ONNX for the browser | **Produced, but UNTRAINED (random weights)** | Loads in onnxruntime, output shapes tested |
| Wav2Vec2 / RAVDESS training | Script written, **never run**. No model, no ONNX | See `model_cards/emotion_speech.md` |
| DeepFace server fallback | Module written, not exposed over HTTP, never run with DeepFace installed | CCR-AI-2 |
| Docker image, CI workflow | Written, **never built or run** | |

Not tested: Python 3.11 (tests ran on 3.12), Docker build, GitHub Actions, multi-worker use, load.

## 2. How to run

```
cd services/ai
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt        # torch/transformers/deepface only for ml training
cp .env.example .env                       # then export the vars, or pass them via Docker
uvicorn app.asgi:app --port 8001           # single worker (SQLite state, see gaps)
python scripts/mock_client.py              # posts to every endpoint
python scripts/demo_trigger_decay.py       # rise-then-decay demo
python -m pytest                           # full suite
python -m ml.evaluate_synthetic            # synthetic-only evaluation
python -m ml.synthetic --out data/synthetic
python -m ml.make_smoke_onnx               # regenerate placeholder ONNX
python -m ml.train_fer --csv fer2013.csv   # real FER model (needs torch + dataset)
docker build -t smaran-ai . && docker run -p 8001:8001 -v ai_data:/data --env-file .env smaran-ai
```

Environment variables (`.env.example`):

| Var | Purpose |
|---|---|
| `AI_ENV` | `production` makes `AI_SERVICE_TOKEN` mandatory (startup fails without it) |
| `AI_SERVICE_TOKEN` | Bearer token services/api must send to `/ai/*` |
| `AI_STATE_DB` | SQLite path (default `data/ai_state.db`) |
| `AI_ALLOW_TIME_OVERRIDE` | `1` honours `X-Smaran-Now` (tests/demos only; never in production) |
| `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_TIMEOUT_S` | Optional. Model name default `gemini-2.5-flash` is unverified |
| `MLFLOW_TRACKING_URI` | Optional |

## 3. Endpoints (exactly the contract, no `/api/v1` prefix, as specified)

- `POST /ai/triggers/update`. Returns ALL known cues for the patient, recomputed at server time, sorted by confidence. Idempotent: replaying observations changes nothing. Cues with negative valence are capped at 0.05. Filter on `valence_label` for positive triggers.
- `POST /ai/difficulty/next`. Output 1-10 plus rationale. Assumes events in `recent` are at `current_difficulty`. Re-sent sliding windows are de-duplicated by overlap matching.
- `POST /ai/severity/estimate`. Needs performance data. It uses events recorded by earlier `difficulty/next` and `triggers/update` calls, plus optional `samples` (CCR-AI-1). Below 10 events it returns `stable`, indicator 1 and an `insufficient_data` driver.
- `POST /ai/emotion/fuse`. At least one of `face`/`speech` is required (422 otherwise). `confidence` below about 0.6 should be shown as "unconfirmed". Caregiver can always confirm/override.
- `POST /ai/content/generate`. `source` is `gemini` or `template`. Only en/as/bn/ne are served by templates or Gemini. Other locales return English template text, so use voice packs for those.
- `GET /healthz`. Operational extra, not in the contract.
- Errors are RFC 7807 (`application/problem+json`). Auth failures are 401 with `WWW-Authenticate: Bearer`.
- `openapi.json` is exported in this folder for the contracts package.

Emotion `baseline` shape (the contract left it open): `{valence_mean, valence_std, arousal_mean, arousal_std, n}`. **The service does not compute it.** The API must compute it from the patient's first N EmotionSamples (mean and std of calibrated valence/arousal readings) and pass it in. With no baseline, calibration is the identity.

On-device emotion: `ml/models/fer_cnn_smoke.onnx` + `.meta.json` give input `[N,1,48,48]` float32 (grayscale, /255), outputs `logits` and `probs` `[N,7]`, the class order, and the valence-arousal table. apps/patient-web must reimplement `probs_to_va` (sum of p*v, sum of p*a, conf = max p) in TypeScript, using the table in the meta file. **Do not ship the smoke model as a real detector.**

## 4. Mocks

Wrote: `scripts/mock_client.py` (stands in for services/api calling the AI service). Depends on no other workstream, so nothing needed mocking. Replaced by the real services/api once it calls `/ai/*` with the bearer token.

## 5. Contract deviations and CONTRACT CHANGE REQUESTS (proceeding with my labelled assumptions)

- **CCR-AI-1:** `severity/estimate` has no performance input. I added an optional `samples` array (`ts, source, correct, response_ms, hints, difficulty, with_cue, game_id`). Better long-term: the API sends session summaries or the AI service reads GameEvents.
- **CCR-AI-2:** add `POST /ai/emotion/analyze` (consent-gated image or audio upload) to enable the DeepFace/Wav2Vec2 server fallback. Not mounted.
- **CCR-AI-3:** add `data_sufficient: boolean` to the severity response, and optionally structured `drivers` (objects). Today drivers are plain strings and "no data" is indicator 1.
- **CCR-AI-4:** add `session_id` and per-item `difficulty` and `ts` to `recent` in `difficulty/next`, so de-duplication and level tracking are exact instead of heuristic.
- **CCR-AI-5:** define `baseline` in the contract (shape above) and name who computes it.
- **Assumption A:** `/ai/*` requires `Authorization: Bearer <AI_SERVICE_TOKEN>` when set (RBAC for service-to-service). Claude 1 must send it.
- **Assumption B:** `drivers` are strings; `cue_type` is a free string up to 32 chars; patient_id and cue_id are opaque strings up to 64 chars.
- **Assumption C:** extra request fields are ignored, not rejected.

## 6. Honest limits

- **Emotion bias.** FER-2013 and RAVDESS were not collected from elderly people or Assamese and other NER speakers (acted English emotion, web faces). Expect lower accuracy, especially for dementia-related flat affect and slowed speech. No trained model exists yet in this repo. Mitigations built in: optional off-by-default capture (enforced by callers, not by this service), per-patient calibration, confidence penalties, caregiver confirm/override. Subgroup evaluation is not done.
- **Severity norms are synthetic placeholders.** The 1-7 indicator is not a clinical GDS. No clinical validation.
- **Synthetic evaluation only.** No real patient data exists. Trigger confidence predicted next recall with AUC 0.545 on simulated data (weak). Severity separated simulated stable from declining patients, which only shows the rules behave as designed.
- **Translations unverified.** Assamese, Bengali and Nepali templates were written by me and not checked by native speakers. Bodo, Meitei, Mizo, Khasi and Garo have no text templates.
- **Gemini** untested against the live API. English-only banned-word filter. Digits blocked in all scripts.
- **State storage.** SQLite file, **not encrypted at rest** (AES-256 requirement not met in-service). Use an encrypted volume or move state to Postgres. It stores pseudonymous IDs and aggregates only. Run one worker. Model blobs are Python pickles written and read only by this service; do not expose the DB to untrusted writers.
- **TLS 1.3** is not handled here. Terminate at the gateway or proxy.
- **Perf events from `difficulty/next`** are timestamped at server receive time, so offline-synced games land on sync day.
- Consent checks (camera, mic) are the caller's job. This service never receives images or audio.
- ONNX: the browser model is an untrained placeholder. Wav2Vec2 is about 380 MB and is not suitable in-browser.

## 7. PORTABILITY NOTES

- **Reusable as-is:** the whole service (plain HTTP/JSON, bearer auth, no cookies or web-only formats), so a native app can call it unchanged. `ml/models/*.onnx` + meta work with onnxruntime-react-native.
- **Needs reimplementing in client TypeScript:** `probs_to_va` and the optional calibration (`calibrate` in `app/core/emotion.py`) if emotion is computed on-device. Both are small pure functions.
- **Rewrite for React Native:** nothing in this folder is web-specific. Camera capture and ONNX session loading belong to Claude 3's `CameraAdapter` and a model-loader adapter.
- **Adapters defined here:** none (backend only). Replaceable seams: `Store` (SQLite, swap for Postgres), `content._call_gemini` (swap provider).

## 8. Next steps for whoever continues

1. Train `ml/train_fer.py` on real data and replace the smoke ONNX. Report subgroup accuracy.
2. Decide the CCRs above, especially 1, 3 and 4.
3. Get native-speaker review of as/bn/ne text, plus real Bodo and Meitei content.
4. Replace the synthetic norms with clinically validated ones and validate the indicator with clinicians.
5. Move state to encrypted Postgres, then allow multiple workers.
6. Build the Docker image and run the CI workflow once (`ci/ai-ci.yml` to `.github/workflows/`).
