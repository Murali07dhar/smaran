import type {
  PatientView,
  ReminderOut as Reminder,
  ConsentRecord,
  ConsentKind,
  Role,
  Locale,
  MediaAsset,
  SyncPushRequest,
  SyncPushResponse,
  SyncPullResponse
} from "@smaran/contracts";
import type { ApiClient } from "./client";

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  user: { id: string; role: Role; name: string; language: Locale };
}

export function login(client: ApiClient, credentials: { pin?: string; qr_token?: string }) {
  return client.request<LoginResponse>("/auth/patient-pin-login", {
    method: "POST",
    body: credentials,
    auth: false
  });
}

export function getPatientProfile(client: ApiClient, patientId: string) {
  return client.request<PatientView>(`/patients/${patientId}`);
}

/** API returns {latest:{kind:record}, history:[...]}; consentFromRecords picks the newest record per kind. */
export async function getConsents(client: ApiClient, patientId: string): Promise<ConsentRecord[]> {
  const r = await client.request<ConsentRecord[] | { latest: Record<string, ConsentRecord>; history: ConsentRecord[] }>(
    `/patients/${patientId}/consents`
  );
  return Array.isArray(r) ? r : r.history;
}

export function postConsent(client: ApiClient, patientId: string, body: { kind: ConsentKind; granted: boolean }) {
  return client.request<ConsentRecord>(`/patients/${patientId}/consents`, { method: "POST", body });
}

export function getReminders(client: ApiClient, patientId: string) {
  return client.request<Reminder[]>(`/patients/${patientId}/reminders`);
}

export function getMedia(client: ApiClient, patientId: string) {
  return client.request<MediaAsset[]>(`/patients/${patientId}/media`);
}

/** Relative signed URL (`/api/v1/media/{id}/content?sig&exp`); callers prefix the API origin if needed. */
export function getMediaUrl(client: ApiClient, mediaId: string) {
  return client.request<{ url: string; expires_at: string }>(`/media/${mediaId}/url`);
}

export function syncPush(client: ApiClient, body: SyncPushRequest) {
  return client.request<SyncPushResponse>("/sync/push", { method: "POST", body });
}

export function syncPull(client: ApiClient, since: string | number | null) {
  const qs = since !== null && since !== undefined && since !== "" ? `?since=${encodeURIComponent(since)}` : "";
  return client.request<SyncPullResponse>(`/sync/pull${qs}`);
}

export function joinCoopRoom(client: ApiClient, body: { join_code: string; role: "patient" | "family" }) {
  return client.request<{ room_id: string; ws_token: string }>("/coop/rooms/join", { method: "POST", body });
}
