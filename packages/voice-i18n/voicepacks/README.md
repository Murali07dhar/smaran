# Voice packs (lus = Mizo, kha = Khasi, grt = Garo)

No usable ASR/TTS exists for these in our stack, so we use **real recordings by native speakers** (no synthetic voice presented as human).

Format: `manifest.json` + `clips/*.opus` (mono, 24 kbps, 16 kHz is plenty; ~1.5 KB/s).
1. Copy `example/manifest.template.json`, set `pack_id` (e.g. `lus-v1`), fill transcripts and durations.
2. Record every id in `REQUIRED_CLIP_IDS` (see `core/voicepack.ts`). Add `sha256` per clip for integrity.
3. `speaker.consent_recorded` must be `true` (the validator rejects the pack otherwise). Only CC0 / caregiver-owned / CC-BY content.
4. Install on-device with `VoicePackStore.installPack(manifest, readClip)`; works offline afterwards.

The template is NOT a usable pack: it has no audio and `consent_recorded: false`, so validation fails by design.
