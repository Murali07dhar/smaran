# Model card: severity indicator and Gemini content

## Severity indicator (`app/core/severity.py`)
**SUPPORT SIGNAL, NOT A DIAGNOSIS.** Every response carries the disclaimer.

**Rules (all visible in `drivers`):** metrics over the window (accuracy, hint use, cue recall, average difficulty level) are converted to percentiles against `app/data/reference_norms.json`, averaged into a composite, and mapped to a 1 to 7 indicator (75+:1, 60+:2, 45+:3, 30+:4, 20+:5, 10+:6, else 7). Band is `alert` if indicator is 5 or more or the composite fell 25 points vs the patient's own first 30 events; `watch` if indicator is 4 or more, it fell 12 points, or responses are 1.6x slower than baseline; otherwise `stable`. Fewer than 10 events returns `stable`, indicator 1 and an `insufficient_data` driver.

**Limits**
- The reference norms are SYNTHETIC PLACEHOLDERS, not from any clinical cohort. The indicator is not a Reisberg GDS score. It only borrows the 1 to 7 scale.
- Difficulty level is included because adaptive difficulty keeps accuracy near a target and would otherwise hide decline.
- Baseline needs at least 15 early events that end before the window starts. Without it there is no trend, and only the absolute indicator applies.
- Indicator 1 for "no data" can be misread as "no decline". Dashboards should check for the `insufficient_data` driver (CCR-AI-3 asks for an explicit field).
- On simulated patients the bands separated stable from declining. That says nothing about real accuracy, and no validation against clinical assessment has been done.

## Gemini content (`app/core/content.py`)
**What it does:** one calm spoken sentence for reminders or game prompts, with a safety system prompt and a deterministic template fallback (offline, no key, unsafe output, or unsupported locale).

**Safeguards:** nothing identifying is sent to Gemini. Name and title are substituted locally into placeholders. Output is rejected if it has digits, banned medical or pressure words, no `{title}` for reminders, or is too long.

**Limits**
- Gemini is called only for en, as, bn, ne. Bodo, Meitei, Mizo, Khasi and Garo fall back to English templates.
- Assamese, Bengali and Nepali templates and Gemini output are not verified by native speakers.
- The banned-word filter is English only, so non-English Gemini output has weaker screening. Digits are blocked in all scripts.
- The Gemini model name is configurable and unverified against the live API (no key was available to test).
