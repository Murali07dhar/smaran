# Model card: face emotion (on-device FER CNN + DeepFace fallback)

**Status:** only an UNTRAINED placeholder exists (`ml/models/fer_cnn_smoke.onnx`, random weights). The trained model needs `ml/train_fer.py` and the FER-2013 CSV, which I did not have or run. `ml/train_fer.py` itself has never been executed.

**Intended use:** an optional, consent-gated signal of positive vs negative affect while a patient views a cue. Off by default. A caregiver can confirm or override every result.

**Not for:** diagnosis, scoring the patient, or any decision without caregiver review.

**Interface:** input `[N,1,48,48]` float32 (grayscale, pixel/255) -> `logits`, `probs` `[N,7]`, FER-2013 class order. Probabilities map to a valence-arousal reading with the table in `ml/models/*.meta.json` (mirrors `app/core/va_mapping.py`), then go to `POST /ai/emotion/fuse`.

**Training data:** FER-2013 (48x48 web images, 7 classes, noisy labels, human accuracy about 65%). Typical CNNs reach roughly 60 to 70% on its test split. No result for this repo yet.

**Known limits and bias**
- Not trained on elderly faces. Wrinkles, dentures, reduced facial mobility and flat affect common in dementia are underrepresented, so expect lower accuracy and a bias toward "neutral" or "sad".
- Not representative of North-East India (skin tones, lighting, headwear, camera quality).
- The valence-arousal coordinates are hand-set, not learned. "Familiarity" and "amusement" cannot be read reliably from a face.
- DeepFace has the same dataset caveats and is heavier (TensorFlow). It is not exposed over HTTP (see CCR-AI-2).

**Mitigations:** optional capture, per-patient baseline z-scoring, confidence penalties for single-modality or ambiguous points, caregiver confirm/override, and subgroup accuracy reporting before any real use (not done).
