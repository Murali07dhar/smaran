# Model card: speech emotion (Wav2Vec2 on RAVDESS)

**Status:** training script only (`ml/train_speech.py`). No model trained or ONNX exported, because torch and the RAVDESS audio were not available here, and the script has never been run.

**Intended use:** optional second modality for `POST /ai/emotion/fuse`, server side. Off by default, consent-gated, caregiver can override.

**Training data:** RAVDESS, 24 actors, acted North-American English, 8 emotions. Licence is CC BY-NC-SA 4.0 (non-commercial). Check it fits the deployment. The script splits by actor so validation uses unseen speakers.

**ONNX feasibility:** `--export-onnx` is supported, but wav2vec2-base has about 95M parameters (roughly 380 MB fp32). That is not feasible in-browser on entry-level Android. Treat it as server-side. A distilled or quantised model is future work.

**Known limits and bias**
- Acted speech differs from natural speech. Dementia speech (pauses, slowed rate, word-finding gaps) is out of distribution.
- No Assamese, Bengali, Nepali, Bodo, Meitei or other NER speakers. Prosody and emotion expression differ across languages.
- Accuracy on elderly voices is unknown.

**Mitigations:** low base weight (0.4) in fusion, confidence penalties, per-patient calibration, caregiver confirmation. Collect consented local data with clinical partners before relying on it.
