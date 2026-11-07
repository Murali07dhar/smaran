// AI service contract, copied from the SMARAN shared briefing "AI SERVICE" section.
// Owner: Claude 2 (services/ai). apps/patient-web only calls /ai/emotion/fuse
// (on-device via ONNX) directly; the rest go through services/api.
import type { EmotionLabel } from "./domain";

export interface TriggerObservation {
  cue_id: string;
  cue_type: string;
  valence_label: EmotionLabel;
  recalled: boolean;
  with_cue: boolean;
  ts: string;
}

export interface TriggersUpdateRequest {
  patient_id: string;
  observations: TriggerObservation[];
}

export interface TriggersUpdateResponse {
  triggers: {
    cue_id: string;
    confidence: number;
    valence_label: EmotionLabel;
    last_validated_at: string;
    half_life_days: number;
  }[];
}

export interface DifficultyNextRequest {
  patient_id: string;
  game_id: string;
  recent: { correct: boolean; response_ms: number; hints: number }[];
  current_difficulty: number;
}

export interface DifficultyNextResponse {
  difficulty: number;
  rationale: string;
}

export interface SeverityEstimateRequest {
  patient_id: string;
  window_days: number;
}

export interface SeverityEstimateResponse {
  band: "stable" | "watch" | "alert";
  gds_style_indicator: number;
  drivers: string[];
  disclaimer: string;
}

export interface EmotionFuseRequest {
  face?: { valence: number; arousal: number; conf: number };
  speech?: { valence: number; arousal: number; conf: number };
  baseline?: { valence: number; arousal: number };
}

export interface EmotionFuseResponse {
  valence: number;
  arousal: number;
  label: EmotionLabel;
  confidence: number;
}

export interface ContentGenerateRequest {
  kind: "reminder_phrase" | "game_prompt";
  locale: string;
  context: Record<string, unknown>;
}

export interface ContentGenerateResponse {
  text: string;
  source: "gemini" | "template";
}
