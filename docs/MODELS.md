# Indic model setup (services/voice)

The service runs **without any model** (`VOICE_MODELS_MODE=off`, also the CI default). Every model route then answers `503 application/problem+json` with a `fallback` field, and the client switches to on-device speech. Nothing below is required for the golden path.

| Capability | Model | Size / hardware | Status in this repo |
|---|---|---|---|
| ASR | AI4Bharat IndicConformer (`ai4bharat/indic-conformer-600m-multilingual`) | ~2.4 GB download; CPU works but slow (seconds/utterance); GPU recommended | Integration point written in `app/models.py`, **not tested here** (no network/GPU in build environment). Model-card API may differ: verify. |
| Language ID | IndicLID (fastText + BERT cascade) | ~1.5 GB; CPU OK | **Not wired**; script heuristic used (cannot separate as/bn or ne/brx; reports `ambiguous_with`). |
| TTS | Indic TTS (FastPitch + HiFi-GAN per language) or `indic-parler-tts` | 100s of MB per language; Parler needs a GPU for usable latency | **Not wired**; raises `ModelUnavailable`, client uses SpeechSynthesis or server returns 503. |
| Translation | IndicTrans2 (1B distilled for en->indic) | ~2-4 GB; GPU strongly recommended; CPU feasible for the few hundred UI strings | Used only by `pnpm translate` via an HTTP endpoint you host. |

## Install
```bash
cd services/voice
pip install -r requirements.txt            # light: fastapi only
pip install -r requirements-models.txt     # heavy: torch, transformers, TTS
export VOICE_MODEL_DIR=/models VOICE_DEVICE=cuda VOICE_MODELS_MODE=auto
uvicorn app.main:app --port 8002
```
Some AI4Bharat checkpoints are gated or need `trust_remote_code`; accept licences on Hugging Face first and review the code you execute.

## IndicTrans2 endpoint for `pnpm translate`
Host any server returning `{"translations":[...]}` for `{"sentences","src_lang","tgt_lang"}` (codes: `asm_Beng`, `ben_Beng`, `npi_Deva`, `brx_Deva`, `mni_Mtei`). Check that your checkpoint supports brx and mni; if not, those files stay as English fallbacks.

## Honest limits
- Machine translations are drafts. Every non-English locale file carries `needs_human_review: true` until a native speaker flips it.
- ASR accuracy on elderly, dialectal speech is unmeasured; always keep tap buttons as the primary path.
- Chrome's Web Speech API **sends audio to Google**: it is not offline and not private. True offline STT needs an on-device model (e.g. a quantised Conformer exported to ONNX), not done here.
- Bodo (brx) and Meitei (mni) have no browser TTS voice; `hasTTS` returns false for them, so use server TTS, voice packs or family recordings.
- lus, kha, grt: recordings only.
