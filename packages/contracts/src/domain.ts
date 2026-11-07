/**
 * SMARAN domain types = the DATABASE SCHEMA in wire format (JSON, snake_case).
 * UUIDs are strings, timestamps are ISO-8601 UTC strings, nullable columns are `T | null`.
 * Secrets never appear here: User omits password_hash/pin_hash, MediaAsset omits enc_path/nonce.
 * Kept in lock-step with services/api/app/models.py by services/api/tests/test_contracts.py.
 * Pure types + constants: no DOM / React imports (reusable in React Native).
 */
export type UUID = string;
export type ISODateTime = string;

export const ROLES = ["patient", "caregiver", "health_worker", "admin"] as const;
export const LOCALES = ["as", "bn", "ne", "brx", "mni", "en"] as const; // 'as' first
export const VOICE_PACK_LOCALES = ["lus", "kha", "grt"] as const;
export const CONSENT_KINDS = ["camera", "mic", "data_sharing"] as const;
export const MEDIA_KINDS = ["photo", "audio"] as const;
export const REMINDER_CATEGORIES = ["medicine", "hydration", "activity", "appointment"] as const;
export const REMINDER_EVENT_STATUSES = ["done", "later", "missed"] as const;
export const GAME_DOMAINS = ["memory", "attention", "routine", "pattern_object", "executive"] as const;
export const EMOTION_LABELS = ["joy", "comfort", "excitement", "amusement", "familiarity", "neutral", "negative"] as const;
export const EMOTION_SOURCES = ["face", "speech", "fused"] as const;
export const ALERT_KINDS = ["score_drop", "activity_drop", "missed_reminders", "severity"] as const;
export const ALERT_SEVERITIES = ["info", "watch", "alert"] as const;
export const SYNC_ACTIONS = ["upsert", "delete"] as const;
/** Positive-valence labels the cue-discovery engine looks for. */
export const POSITIVE_EMOTION_LABELS = ["joy", "comfort", "excitement", "amusement", "familiarity"] as const;

export type Role = (typeof ROLES)[number];
export type Locale = (typeof LOCALES)[number];
export type VoicePackLocale = (typeof VOICE_PACK_LOCALES)[number];
export type ConsentKind = (typeof CONSENT_KINDS)[number];
export type MediaKind = (typeof MEDIA_KINDS)[number];
export type ReminderCategory = (typeof REMINDER_CATEGORIES)[number];
export type ReminderEventStatus = (typeof REMINDER_EVENT_STATUSES)[number];
export type GameDomain = (typeof GAME_DOMAINS)[number];
export type EmotionLabel = (typeof EMOTION_LABELS)[number];
export type EmotionSource = (typeof EMOTION_SOURCES)[number];
export type AlertKind = (typeof ALERT_KINDS)[number];
export type AlertSeverity = (typeof ALERT_SEVERITIES)[number];
export type SyncAction = (typeof SYNC_ACTIONS)[number];
/** AI service bands. */
export type SeverityBand = "stable" | "watch" | "alert";

/** Placeholder shapes for JSON columns (owners may tighten them; keep backwards compatible). */
export interface RoutineStep { order: number; title: string; [extra: string]: unknown }
export interface SeverityDriver { feature: string; direction?: "up" | "down" | "flat"; detail?: string; [extra: string]: unknown }

export interface User {
  id: UUID;
  role: Role;
  name: string;
  email: string | null;
  phone: string | null;
  language: string;
  created_at: ISODateTime;
}
export interface PatientProfile {
  patient_id: UUID;
  age: number;
  language: string;
  estimated_stage: string | null;
  notes: string | null;
}
export interface CaregiverLink {
  id: UUID;
  caregiver_id: UUID;
  patient_id: UUID;
  relation: string;
  created_at: ISODateTime;
}
export interface ConsentRecord {
  id: UUID;
  patient_id: UUID;
  kind: ConsentKind;
  granted: boolean;
  granted_by: UUID;
  ts: ISODateTime;
}
export interface MediaAsset {
  id: UUID;
  patient_id: UUID;
  uploader_id: UUID;
  kind: MediaKind;
  mime: string;
  size_bytes: number;
  tags: string[];
  created_at: ISODateTime;
}
export interface Routine {
  id: UUID;
  patient_id: UUID;
  title: string;
  steps: RoutineStep[];
  created_by: UUID;
  server_version: number;
  updated_at: ISODateTime;
}
export interface Reminder {
  id: UUID;
  patient_id: UUID;
  category: ReminderCategory;
  title: string;
  schedule_rrule: string;
  locale: string;
  voice_clip_id: string | null;
  escalate_after_misses: number;
  active: boolean;
  server_version: number;
  updated_at: ISODateTime;
}
export interface ReminderEvent {
  id: UUID;
  reminder_id: UUID;
  patient_id: UUID;
  due_at: ISODateTime;
  status: ReminderEventStatus;
  ts: ISODateTime;
}
export interface GameSession {
  id: UUID;
  patient_id: UUID;
  game_id: string;
  domain: GameDomain;
  started_at: ISODateTime;
  ended_at: ISODateTime | null;
  difficulty: number;
  score: number | null;
  device_id: string;
  server_ts: ISODateTime;
}
export interface GameEvent {
  id: UUID;
  session_id: UUID;
  patient_id: UUID;
  type: string;
  item_id: string;
  correct: boolean | null;
  response_ms: number | null;
  cue_id: string | null;
  with_cue: boolean;
  ts: ISODateTime;
}
export interface EmotionSample {
  id: UUID;
  session_id: UUID | null;
  patient_id: UUID;
  valence: number;
  arousal: number;
  label: EmotionLabel;
  confidence: number;
  source: EmotionSource;
  caregiver_confirmed: boolean | null;
  ts: ISODateTime;
}
export interface MemoryTrigger {
  id: UUID;
  patient_id: UUID;
  cue_id: string;
  cue_type: string;
  valence_label: EmotionLabel;
  confidence: number;
  last_validated_at: ISODateTime;
  half_life_days: number;
  updated_at: ISODateTime;
}
export interface Alert {
  id: UUID;
  patient_id: UUID;
  kind: AlertKind;
  severity: AlertSeverity;
  message: string;
  created_at: ISODateTime;
  acknowledged_by: UUID | null;
  acknowledged_at: ISODateTime | null;
  note: string | null;
}
export interface SeverityIndicator {
  id: UUID;
  patient_id: UUID;
  band: string;
  gds_style_indicator: number;
  drivers: SeverityDriver[];
  computed_at: ISODateTime;
}
export interface SyncChange {
  cursor: number;
  entity: string;
  entity_id: UUID;
  action: SyncAction;
  payload: Record<string, unknown>;
  patient_id: UUID;
  server_ts: ISODateTime;
}
export interface SyncOp {
  op_id: UUID;
  device_id: string;
  applied_at: ISODateTime;
}

/** Shown wherever scores or severity appear: SMARAN is a support tool, never a diagnosis. */
export const SUPPORT_DISCLAIMER =
  "SMARAN is a support tool to help caregivers notice changes. It is not a medical diagnosis.";
