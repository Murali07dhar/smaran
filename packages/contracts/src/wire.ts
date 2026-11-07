/** Request/response shapes that the shared briefing declares BINDING (hand-written until every module
 *  publishes full OpenAPI schemas; then prefer the generated `paths`/`components` from ./schema). */
import type {
  AlertKind, AlertSeverity, ConsentKind, EmotionLabel, GameDomain, ISODateTime, MediaKind, ReminderCategory,
  Role, SyncAction, UUID,
} from "./domain";

/** RFC 7807 problem details (all errors, `application/problem+json`). */
export interface ProblemDetails {
  type: string; title: string; status: number; detail?: string; instance?: string;
  errors?: Array<{ loc: Array<string | number>; msg: string; type: string }>;
}

// ---- auth ----
export interface LoginRequest { email?: string; phone?: string; password: string }
export interface PinLoginRequest { pin?: string; qr_token?: string }
export interface RefreshRequest { refresh_token: string }
export interface AuthUser { id: UUID; role: Role; name: string; language: string }
export interface TokenResponse { access_token: string; refresh_token: string; token_type: "bearer"; user: AuthUser }

// ---- patients ----
export interface PatientCreate { name: string; age: number; language: string }
export interface PatientSummary {
  id: UUID; name: string; age: number; language: string; estimated_stage: string | null;
  last_active_at: ISODateTime | null; open_alerts: number; severity_band: string | null;
}
export interface PatientPinResponse { pin: string; qr_token: string; expires_at: ISODateTime }
export interface CaregiverLinkCreate { caregiver_id: UUID; patient_id: UUID; relation: string }
export interface ConsentCreate { kind: ConsentKind; granted: boolean }

// ---- sync ----
export interface SyncOpIn {
  op_id: UUID; entity: string; entity_id: UUID; action: SyncAction; payload: Record<string, unknown>; client_ts: ISODateTime;
}
export interface SyncPushRequest { device_id: string; ops: SyncOpIn[] }
export interface SyncPushResponse { accepted: UUID[]; rejected: Array<{ op_id: UUID; reason: string }>; server_cursor: number }
export interface SyncPullResponse {
  changes: Array<{ cursor: number; entity: string; entity_id: UUID; action: SyncAction; payload: Record<string, unknown>; server_ts: ISODateTime }>;
  server_cursor: number;
}

// ---- co-op ----
export interface CoopRoomCreate { patient_id: UUID; game_id: string }
export interface CoopRoom { room_id: UUID; join_code: string; expires_at: ISODateTime }
export interface CoopJoinRequest { join_code: string; role: "patient" | "family" }
export interface CoopJoinResponse { room_id: UUID; ws_token: string }
export interface CoopMessage {
  type: "join" | "leave" | "state_patch" | "hint" | "encourage"; seq: number; payload: Record<string, unknown>;
}

// ---- media ----
export interface MediaUrlResponse { url: string; expires_at: ISODateTime }
export type MediaUploadFields = { patient_id: UUID; kind: MediaKind; tags?: string };

// ---- insights ----
export interface AlertOut {
  id: UUID; patient_id: UUID; kind: AlertKind; severity: AlertSeverity; message: string; created_at: ISODateTime;
  acknowledged_at: ISODateTime | null;
}
export interface AlertAckRequest { note?: string }
export interface TrendDay { date: string; sessions: number; avg_score: number | null; avg_response_ms: number | null; engagement_minutes: number }
export interface TrendsResponse { days: TrendDay[] }
export interface CueArm { n: number; accuracy: number | null; avg_response_ms: number | null }
export interface CueComparisonResponse {
  with_cue: CueArm; without_cue: CueArm;
  by_domain: Array<{ domain: GameDomain; with_cue_accuracy: number | null; without_cue_accuracy: number | null }>;
}
export interface TriggerOut {
  cue_id: string; cue_type: string; valence_label: EmotionLabel; confidence: number; last_validated_at: ISODateTime; half_life_days: number;
}
export interface SeverityResponse {
  band: string; gds_style_indicator: number; drivers: unknown[]; disclaimer: string; computed_at: ISODateTime;
}

// ---- reminders (REMINDER contract + server_version) ----
export interface ReminderIn {
  id?: UUID; category: ReminderCategory; title: string; schedule: string /* RRULE */; locale: string;
  voice_clip_id?: string | null; escalate_after_misses: number;
}
