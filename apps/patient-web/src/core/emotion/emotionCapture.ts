import type { EmotionSample } from "@smaran/contracts";
import { hasValidConsent, type ConsentState } from "../validation/consent";
import type { EmotionFuseResponse } from "@smaran/contracts";
import type { StorageAdapter } from "../../adapters/types";
import { uuid7, SyncQueue } from "@smaran/sync-core";

export interface EmotionInferInput {
  imageData?: unknown;
  audioChunk?: unknown;
}

export type EmotionInferFn = (input: EmotionInferInput) => Promise<EmotionFuseResponse>;

const ENABLED_KEY = "emotion_capture_enabled";

/** Emotion capture is off by default per the non-negotiables; this reads the
 * caregiver/patient-set toggle (also off until explicitly turned on). */
export async function isEmotionCaptureEnabled(storage: StorageAdapter): Promise<boolean> {
  const row = await storage.get<{ id: string; value: boolean }>("kv", ENABLED_KEY);
  return row?.value ?? false;
}

export async function setEmotionCaptureEnabled(storage: StorageAdapter, enabled: boolean): Promise<void> {
  await storage.put("kv", { id: ENABLED_KEY, value: enabled });
}

function hasCaptureConsent(consent: ConsentState | undefined): boolean {
  return hasValidConsent(consent, "camera") || hasValidConsent(consent, "mic");
}

/**
 * Captures one fused emotion reading, but only if: the feature is enabled,
 * AND a ConsentRecord grants camera or mic. Stores locally and enqueues for
 * sync immediately (EmotionSample is append-only, so this never conflicts).
 * Returns null if capture is skipped for any gating reason.
 */
export async function captureEmotionSample(params: {
  storage: StorageAdapter;
  queue: SyncQueue;
  patientId: string;
  sessionId?: string;
  consent: ConsentState | undefined;
  infer: EmotionInferFn;
  input: EmotionInferInput;
}): Promise<EmotionSample | null> {
  const enabled = await isEmotionCaptureEnabled(params.storage);
  if (!enabled || !hasCaptureConsent(params.consent)) return null;

  const result = await params.infer(params.input);
  const sample: EmotionSample = {
    id: uuid7(),
    patient_id: params.patientId,
    session_id: params.sessionId ?? null,
    caregiver_confirmed: null,
    valence: result.valence,
    arousal: result.arousal,
    label: result.label,
    confidence: result.confidence,
    ts: new Date().toISOString(),
    source: "fused"
  };
  await params.storage.put("emotionSamples", sample);
  await params.queue.enqueue({
    op_id: uuid7(),
    entity: "emotion_samples",
    entity_id: sample.id,
    action: "upsert",
    payload: { ...sample }
  });
  return sample;
}
