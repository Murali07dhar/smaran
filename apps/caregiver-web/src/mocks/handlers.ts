// MSW mock of services/api for the caregiver dashboard. Paths/shapes follow ROUTES (BINDING). snake_case, ISO-8601 UTC.
import { http, HttpResponse } from 'msw';
const B = (import.meta as any).env?.VITE_API_BASE_URL || '/api/v1';
const now = Date.now(), day = 864e5, iso = (t: number) => new Date(t).toISOString();
const id = () => crypto.randomUUID();
const problem = (status: number, title: string) => HttpResponse.json({ type: 'about:blank', title, status }, { status, headers: { 'Content-Type': 'application/problem+json' } });
const DISC = 'Support tool only, not a diagnosis.';
const patients: any[] = [
  { id: 'p1', name: 'Bhaben Das', age: 74, language: 'as', estimated_stage: 'moderate', last_active_at: iso(now - day), open_alerts: 1, severity_band: 'alert' },
  { id: 'p2', name: 'Maya Gurung', age: 70, language: 'ne', estimated_stage: 'mild', last_active_at: iso(now - 2 * day), open_alerts: 0, severity_band: 'watch' },
  { id: 'p3', name: 'Ranjan Boro', age: 68, language: 'brx', estimated_stage: 'mild', last_active_at: iso(now - 3 * day), open_alerts: 0, severity_band: 'stable' }
];
const alerts: any[] = [{ id: 'a1', patient_id: 'p1', kind: 'score_drop', severity: 'alert', message: 'Score dropped 3 days running', created_at: iso(now - day), acknowledged_by: null, acknowledged_at: null, note: null }];
const consents: any[] = [];
const reminders: any[] = [{ id: 'r0', patient_id: 'p1', category: 'medicine', title: 'Morning tablet', schedule: 'FREQ=DAILY;BYHOUR=8;BYMINUTE=0', locale: 'as', voice_clip_id: null, escalate_after_misses: 2, active: true, server_version: 1 }];
const routines: any[] = [];
const media: any[] = [];
const trendDays = Array.from({ length: 30 }, (_, k) => { const i = 29 - k; return { date: iso(now - i * day).slice(0, 10), sessions: 1 + (k % 3), avg_score: +(70 - k * 0.5 + Math.sin(i) * 4).toFixed(1), avg_response_ms: 2400 + k * 40, engagement_minutes: 12 + Math.round(Math.cos(i) * 5) }; });
export const handlers = [
  http.post(B + '/auth/login', async ({ request }) => {
    const b: any = await request.json(); const who = b.email || b.phone || '';
    if (!who || !b.password) return problem(401, 'Invalid credentials');
    return HttpResponse.json({ access_token: 'mock', refresh_token: 'mock-refresh', token_type: 'bearer', user: { id: 'u1', role: who.startsWith('hw') ? 'health_worker' : 'caregiver', name: 'Demo User', language: 'en' } });
  }),
  http.get(B + '/patients', () => HttpResponse.json(patients)),
  http.post(B + '/patients', async ({ request }) => { const b: any = await request.json(); const p = { id: id(), name: b.name, age: b.age, language: b.language, estimated_stage: null, last_active_at: null, open_alerts: 0, severity_band: null }; patients.push(p); return HttpResponse.json(p, { status: 201 }); }),
  http.post(B + '/patients/:pid/pin', () => HttpResponse.json({ pin: '4821', qr_token: id(), expires_at: iso(now + day) })),
  http.get(B + '/alerts', ({ request }) => { const q = new URL(request.url).searchParams; const pid = q.get('patient_id'); return HttpResponse.json(alerts.filter(a => (!pid || a.patient_id === pid) && (q.get('status') === 'all' || !a.acknowledged_at))); }),
  http.post(B + '/alerts/:aid/ack', async ({ params, request }) => { const a = alerts.find(x => x.id === params.aid); if (!a) return problem(404, 'Not found'); const b: any = await request.json().catch(() => ({})); a.acknowledged_at = iso(Date.now()); a.acknowledged_by = 'u1'; a.note = b.note ?? null; return HttpResponse.json(a); }),
  http.get(B + '/patients/:pid/dashboard/trends', ({ params }) => HttpResponse.json({ days: params.pid === 'p1' ? trendDays : [] })),
  http.get(B + '/patients/:pid/dashboard/cue-comparison', () => HttpResponse.json({ with_cue: { n: 120, accuracy: 0.74, avg_response_ms: 2300 }, without_cue: { n: 110, accuracy: 0.52, avg_response_ms: 3100 }, by_domain: [{ domain: 'memory', with_cue_accuracy: 0.78, without_cue_accuracy: 0.5 }, { domain: 'attention', with_cue_accuracy: 0.7, without_cue_accuracy: 0.55 }] })),
  http.get(B + '/patients/:pid/dashboard/triggers', () => HttpResponse.json([{ cue_id: 'c1', cue_type: 'audio', valence_label: 'joy', confidence: 0.86, last_validated_at: iso(now - 10 * day), half_life_days: 30 }, { cue_id: 'c2', cue_type: 'photo', valence_label: 'comfort', confidence: 0.71, last_validated_at: iso(now - 22 * day), half_life_days: 21 }])),
  http.get(B + '/patients/:pid/dashboard/severity', () => HttpResponse.json({ band: 'alert', gds_style_indicator: 4, drivers: ['Score decline 30d', 'Slower responses'], disclaimer: DISC, computed_at: iso(now) })),
  http.get(B + '/patients/:pid/report.csv', () => new HttpResponse('date,sessions,avg_score\n' + trendDays.map(d => `${d.date},${d.sessions},${d.avg_score}`).join('\n'), { headers: { 'Content-Type': 'text/csv' } })),
  http.get(B + '/patients/:pid/consents', ({ params }) => HttpResponse.json(consents.filter(c => c.patient_id === params.pid))),
  http.post(B + '/patients/:pid/consents', async ({ params, request }) => { const b: any = await request.json(); if (!['camera', 'mic', 'data_sharing'].includes(b.kind) || typeof b.granted !== 'boolean') return problem(422, 'Invalid consent'); const c = { id: id(), patient_id: params.pid, kind: b.kind, granted: b.granted, granted_by: 'u1', ts: iso(Date.now()) }; consents.push(c); return HttpResponse.json(c, { status: 201 }); }),
  http.get(B + '/patients/:pid/reminders', ({ params }) => HttpResponse.json(reminders.filter(r => r.patient_id === params.pid))),
  http.post(B + '/patients/:pid/reminders', async ({ params, request }) => { const b: any = await request.json(); const r = { ...b, id: b.id || id(), patient_id: params.pid, server_version: 1 }; reminders.push(r); return HttpResponse.json(r, { status: 201 }); }),
  http.get(B + '/patients/:pid/routines', ({ params }) => HttpResponse.json(routines.filter(r => r.patient_id === params.pid))),
  http.post(B + '/patients/:pid/routines', async ({ params, request }) => { const b: any = await request.json(); const r = { ...b, id: b.id || id(), patient_id: params.pid, created_by: 'u1', server_version: 1, updated_at: iso(Date.now()) }; routines.push(r); return HttpResponse.json(r, { status: 201 }); }),
  http.get(B + '/patients/:pid/media', ({ params }) => HttpResponse.json(media.filter(m => m.patient_id === params.pid))),
  http.post(B + '/media', async ({ request }) => { const f = await request.formData(); const file = f.get('file') as File; const m = { id: id(), patient_id: f.get('patient_id'), uploader_id: 'u1', kind: f.get('kind'), mime: file?.type || 'application/octet-stream', size_bytes: file?.size ?? 0, tags: JSON.parse(String(f.get('tags') || '[]')), created_at: iso(Date.now()) }; media.push(m); return HttpResponse.json(m, { status: 201 }); }),
  http.post(B + '/coop/rooms', () => HttpResponse.json({ room_id: id(), join_code: 'K7M2QX', expires_at: iso(now + 3600e3) }, { status: 201 }))
];
