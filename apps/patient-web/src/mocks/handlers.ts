// MOCK for services/api (Claude 1) and the relevant services/ai (Claude 2)
// routes. Covers every network call apps/patient-web makes so the app can be
// developed and demoed standalone before the real backend exists. Replace by
// pointing VITE_API_BASE_URL at the real service — these handlers are only
// installed when VITE_USE_MOCKS=true (see src/mocks/browser.ts).
import { http, HttpResponse } from "msw";

const API = "/api/v1";

const demoPatient = {
  id: "0199f000-0000-7000-8000-000000000001",
  name: "Demo Patient",
  age: 72,
  language: "as",
  estimated_stage: "mild"
};

const demoReminders = [
  {
    id: "0199f000-0000-7000-8000-000000000010",
    patient_id: demoPatient.id,
    category: "medicine",
    title: "Morning tablet",
    schedule: "FREQ=DAILY;BYHOUR=9;BYMINUTE=0",
    locale: "as",
    voice_clip_id: null,
    escalate_after_misses: 2,
    active: true,
    server_version: 1
  }
];

const demoContent = Array.from({ length: 8 }).map((_, i) => ({
  item_id: `content-${i}`,
  kind: "text" as const,
  text: `Family photo #${i + 1}`,
  tags: ["family"]
}));

// In-memory stand-in for sync_changes (BIGSERIAL cursor) and sync_ops (op_id idempotency).
let cursor = 0;
const appliedOps = new Set<string>();
const consents: Record<string, unknown>[] = [];
const problem = (status: number, title: string) =>
  HttpResponse.json({ type: "about:blank", title, status }, { status, headers: { "Content-Type": "application/problem+json" } });

export const handlers = [
  // POST /auth/patient-pin-login {pin | qr_token} -> tokens + user{}
  http.post(`${API}/auth/patient-pin-login`, async ({ request }: { request: Request }) => {
    const body = (await request.json()) as { pin?: string; qr_token?: string };
    if (!body?.pin && !body?.qr_token) return problem(401, "Invalid credentials");
    return HttpResponse.json({
      access_token: "mock-access-token",
      refresh_token: "mock-refresh-token",
      token_type: "bearer",
      user: { id: demoPatient.id, role: "patient", name: demoPatient.name, language: demoPatient.language }
    });
  }),

  http.get(`${API}/patients/:id`, ({ params }) => HttpResponse.json({ ...demoPatient, id: params.id })),

  http.get(`${API}/patients/:id/consents`, () => HttpResponse.json(consents)),

  // POST /patients/{id}/consents {kind, granted}
  http.post(`${API}/patients/:id/consents`, async ({ request, params }) => {
    const body = (await request.json()) as { kind?: string; granted?: boolean };
    if (!["camera", "mic", "data_sharing"].includes(body?.kind ?? "") || typeof body.granted !== "boolean") {
      return problem(422, "Invalid consent");
    }
    const rec = {
      id: crypto.randomUUID(),
      patient_id: params.id,
      kind: body.kind,
      granted: body.granted,
      granted_by: demoPatient.id,
      ts: new Date().toISOString()
    };
    consents.push(rec);
    return HttpResponse.json(rec, { status: 201 });
  }),

  // GET /patients/{id}/reminders -> list
  http.get(`${API}/patients/:id/reminders`, () => HttpResponse.json(demoReminders)),

  // NOT IN ROUTES: content is packages/content (Claude 4). Mock-only until Integrator B wires it.
  http.get(`${API}/content`, () =>
    HttpResponse.json({
      content: demoContent,
      cues: [{ cue_id: "cue-1", cue_type: "photo", valence_label: "familiarity" }]
    })
  ),

  // POST /sync/push {device_id, ops[]} -> {accepted[], rejected[{op_id,reason}], server_cursor}
  http.post(`${API}/sync/push`, async ({ request }: { request: Request }) => {
    const body = (await request.json()) as { device_id?: string; ops?: { op_id: string; entity: string }[] };
    const PUSHABLE = ["game_sessions", "game_events", "emotion_samples", "reminder_events"];
    const accepted: string[] = [];
    const rejected: { op_id: string; reason: string }[] = [];
    for (const op of body.ops ?? []) {
      if (!PUSHABLE.includes(op.entity)) rejected.push({ op_id: op.op_id, reason: `entity not pushable: ${op.entity}` });
      else {
        if (!appliedOps.has(op.op_id)) {
          appliedOps.add(op.op_id);
          cursor += 1;
        }
        accepted.push(op.op_id); // idempotent: replays are accepted, not re-applied
      }
    }
    return HttpResponse.json({ accepted, rejected, server_cursor: cursor });
  }),

  // GET /sync/pull?since= -> {changes[], server_cursor}. Pull entities: reminders, routines, media_assets, memory_triggers, alerts
  http.get(`${API}/sync/pull`, () => HttpResponse.json({ changes: [], server_cursor: cursor }))
];
