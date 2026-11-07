// Framework-agnostic: no react/DOM imports (fetch/FormData only). REST client for ROUTES (all under /api/v1).
import { uuid7 as _uuid7 } from '@smaran/sync-core';
export const uuid7 = _uuid7;
export const BASE = (import.meta as any).env?.VITE_API_BASE_URL || '/api/v1';
export type Store = { get(k: string): string | null; set(k: string, v: string): void };
let store: Store = { get: () => null, set: () => {} };
export const setStorage = (s: Store) => { store = s; };
let token = '';
export type Role = 'caregiver' | 'health_worker' | 'admin';
export type Patient = { id: string; name: string; age: number; language: string; estimated_stage: string | null; last_active_at: string | null; open_alerts: number; severity_band: string | null };
export type Alert = { id: string; patient_id: string; kind: string; severity: 'info' | 'watch' | 'alert'; message: string; created_at: string; acknowledged_at: string | null; note?: string | null };
export type TrendDay = { date: string; sessions: number; avg_score: number | null; avg_response_ms: number | null; engagement_minutes: number };
export type CueStats = { n: number; accuracy: number; avg_response_ms: number };
export type CueComparison = { with_cue: CueStats; without_cue: CueStats; by_domain: { domain: string; with_cue_accuracy: number; without_cue_accuracy: number }[] };
export type Trigger = { cue_id: string; cue_type: string; valence_label: string; confidence: number; last_validated_at: string; half_life_days: number };
export type Severity = { band: string; gds_style_indicator: number; drivers: unknown; disclaimer: string; computed_at: string };
export type Reminder = { id: string; patient_id: string; category: string; title: string; schedule: string; locale: string; voice_clip_id?: string | null; escalate_after_misses: number; active: boolean; server_version?: number };
export type RoutineStep = { order: number; title: string; media_id?: string };
export type Routine = { id: string; patient_id: string; title: string; steps: RoutineStep[] };
export type Media = { id: string; patient_id: string; kind: 'photo' | 'audio'; mime: string; size_bytes: number; tags: unknown; created_at: string };
export type ConsentKind = 'camera' | 'mic' | 'data_sharing';
export type Consent = { id: string; patient_id: string; kind: ConsentKind; granted: boolean; granted_by: string; ts: string };

const hdr = (extra: Record<string, string> = {}) => ({ ...(token ? { Authorization: `Bearer ${token}` } : {}), ...extra });
const fail = async (res: Response) => { throw new Error((await res.json().catch(() => ({}))).title || res.statusText); };
const send = async (p: string, method: string, body?: unknown) => {
  const res = await fetch(BASE + p, { method, headers: hdr(body === undefined ? {} : { 'Content-Type': 'application/json' }), body: body === undefined ? undefined : JSON.stringify(body) });
  if (!res.ok) await fail(res);
  return res.status === 204 ? null : res.json();
};
/** GET with last-good-response cache (offline read-only fallback). `stale` is set when served from cache. */
export let lastStale = false;
export const get = async <T>(p: string): Promise<T> => {
  try { const d = await send(p, 'GET'); store.set('smaran_c:' + p, JSON.stringify(d)); lastStale = false; return d as T; }
  catch (e) { const c = store.get('smaran_c:' + p); if (c) { lastStale = true; return JSON.parse(c) as T; } throw e; }
};

export const login = async (identifier: string, password: string) => {
  const r = await fetch(BASE + '/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(identifier.includes('@') ? { email: identifier, password } : { phone: identifier, password }) });
  if (!r.ok) throw new Error('login_failed');
  const d = await r.json(); token = d.access_token;
  return { role: d.user.role as Role, user_id: d.user.id as string, name: d.user.name as string, refresh_token: d.refresh_token as string };
};
export const listPatients = () => get<Patient[]>('/patients');
export const createPatient = (b: { name: string; age: number; language: string }) => send('/patients', 'POST', b) as Promise<Patient>;
export const issuePin = (id: string) => send(`/patients/${id}/pin`, 'POST') as Promise<{ pin: string; qr_token: string; expires_at: string }>;
export const listAlerts = (patient_id: string) => get<Alert[]>(`/alerts?patient_id=${patient_id}&status=all`);
export const ackAlert = (id: string, note?: string) => send(`/alerts/${id}/ack`, 'POST', note ? { note } : {});
export const trends = (id: string, days = 30) => get<{ days: TrendDay[] }>(`/patients/${id}/dashboard/trends?days=${days}`);
export const cueComparison = (id: string) => get<CueComparison>(`/patients/${id}/dashboard/cue-comparison`);
export const triggers = (id: string) => get<Trigger[]>(`/patients/${id}/dashboard/triggers`);
export const severity = (id: string) => get<Severity>(`/patients/${id}/dashboard/severity`);
export const reportCsv = async (id: string) => { const r = await fetch(BASE + `/patients/${id}/report.csv`, { headers: hdr() }); if (!r.ok) await fail(r); return r.text(); };
/** API returns {latest:{kind:record}, history:[...]}; the dashboard needs the current record per kind. */
export const consents = (id: string) =>
  get<Consent[] | { latest: Record<string, Consent>; history: Consent[] }>(`/patients/${id}/consents`).then((r) => (Array.isArray(r) ? r : Object.values(r.latest)));
export const setConsent = (id: string, kind: ConsentKind, granted: boolean) => send(`/patients/${id}/consents`, 'POST', { kind, granted }) as Promise<Consent>;
export const listReminders = (id: string) => get<Reminder[]>(`/patients/${id}/reminders`);
export const createReminder = (id: string, r: Omit<Reminder, 'id' | 'patient_id' | 'server_version'>) => send(`/patients/${id}/reminders`, 'POST', { id: uuid7(), ...r }) as Promise<Reminder>;
export const listRoutines = (id: string) => get<Routine[]>(`/patients/${id}/routines`);
export const createRoutine = (id: string, title: string, steps: string[]) => send(`/patients/${id}/routines`, 'POST', { id: uuid7(), title, steps: steps.map((t, i) => ({ order: i + 1, title: t })) }) as Promise<Routine>;
export const listMedia = (id: string) => get<Media[]>(`/patients/${id}/media`);
/** POST /media multipart {patient_id, kind, file, tags}; server encrypts (AES-256-GCM). */
export const uploadMedia = async (patient_id: string, kind: 'photo' | 'audio', file: Blob, name: string, tags: string[] = []) => {
  const f = new FormData(); f.append('patient_id', patient_id); f.append('kind', kind); f.append('file', file, name); f.append('tags', JSON.stringify(tags));
  const r = await fetch(BASE + '/media', { method: 'POST', headers: hdr(), body: f });
  if (!r.ok) await fail(r); return r.json() as Promise<Media>;
};
export const createRoom = (patient_id: string, game_id: string) => send('/coop/rooms', 'POST', { patient_id, game_id }) as Promise<{ room_id: string; join_code: string; expires_at: string }>;
