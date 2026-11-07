# Model card: trigger engine and difficulty adapter

## Trigger engine (`app/core/triggers.py`)
**What it does:** per patient and cue, `confidence = P(theta_with_cue > theta_without_cue) * exp(-ln2/half_life * days_since_last_observation)`. Both thetas are Beta posteriors starting at Beta(1,1). Evidence per Beta is capped at 40 effective trials so older evidence fades. A per-patient River logistic model learns recall vs gap and nudges each cue's half-life within 3 to 180 days (default 30). Cues with resolved valence "negative" are capped at 0.05.

**Evidence on synthetic data only:** the demo (`scripts/demo_trigger_decay.py`) shows confidence rising with recall and decaying afterwards. On simulated patients, confidence predicted next with-cue recall with AUC 0.545, which is weak. The simulation mostly varies recall by cue, and I have not tuned anything.

**Limits**
- With few "without cue" trials the prior is wide, so confidence can reach about 1.0 after a handful of recalls. Read it as relative ranking, not a calibrated probability.
- The half-life adaptation rule (exp(0.35 * weight * surprise)) is a heuristic. It is unvalidated on real patients.
- Valence labels come from the caller (emotion capture or caregiver). Wrong labels produce wrong triggers.
- Observations are deduplicated by (patient, cue, ts, with_cue, recalled). Two identical trials at the same timestamp collapse into one.

## Difficulty adapter (`app/core/difficulty.py`)
**What it does:** scores the recent window (accuracy, hint use, speed relative to the patient's own baseline) and moves the level by at most one step up, or one to two steps down. River logistic regression can veto a level-up once 12 events are seen. Page-Hinkley flags a recent accuracy drop. Rationale text avoids failure language.

**Limits**
- The contract gives only `current_difficulty`, so every event in `recent` is assumed to be at that level.
- Sliding windows are de-duplicated by overlap matching. Identical consecutive windows from different sessions can be misread as already seen.
- The thresholds (0.85, 0.55, 0.30) are not tuned on real play data.
