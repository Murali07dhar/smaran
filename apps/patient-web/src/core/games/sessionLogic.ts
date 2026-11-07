import type { GameSession as ServerGameSession, GameEvent as GameEventRow } from "@smaran/contracts";
import type { GameEvent, SessionSummary } from "@smaran/games";
import type { StorageAdapter } from "../../adapters/types";
import { uuid7, SyncQueue } from "@smaran/sync-core";

/** Client-side session row: server_ts is assigned by the server. */
export type GameSession = Omit<ServerGameSession, "server_ts">;

export function createSessionRecord(
  patientId: string,
  gameId: string,
  domain: GameSession["domain"],
  difficulty: number,
  deviceId: string
): GameSession {
  return {
    id: uuid7(),
    patient_id: patientId,
    game_id: gameId,
    domain,
    started_at: new Date().toISOString(),
    ended_at: null,
    score: null,
    difficulty,
    device_id: deviceId
  };
}

async function enqueueUpsert(queue: SyncQueue, entity: string, entityId: string, payload: unknown) {
  await queue.enqueue({
    op_id: uuid7(),
    entity,
    entity_id: entityId,
    action: "upsert",
    payload: payload as Record<string, unknown>
  });
}

export async function startSession(
  storage: StorageAdapter,
  queue: SyncQueue,
  session: GameSession
): Promise<void> {
  await storage.put("sessions", session);
  await enqueueUpsert(queue, "game_sessions", session.id, session);
}

/** game_events is append-only per the sync contract: always a fresh upsert, never a delete. */
export async function recordGameEvent(
  storage: StorageAdapter,
  queue: SyncQueue,
  event: GameEvent,
  patientId: string
): Promise<void> {
  // SDK GameEvent -> game_events columns 1:1 (event_id -> id; optional fields -> explicit null).
  const row: GameEventRow = {
    id: event.event_id,
    session_id: event.session_id,
    patient_id: patientId,
    type: event.type,
    item_id: event.item_id,
    correct: event.correct ?? null,
    response_ms: event.response_ms ?? null,
    cue_id: event.cue_id ?? null,
    with_cue: event.with_cue,
    ts: event.ts
  };
  await storage.put("events", row);
  await enqueueUpsert(queue, "game_events", row.id, row);
}

/** score = % correct (0-100) when the game reports totals; null otherwise. DECISION logged for Integrator A/B. */
export async function completeSession(
  storage: StorageAdapter,
  queue: SyncQueue,
  session: GameSession,
  summary?: SessionSummary
): Promise<GameSession> {
  const score =
    summary && summary.answers > 0 ? Math.round((summary.correct_answers / summary.answers) * 1000) / 10 : null;
  const ended: GameSession = { ...session, ended_at: new Date().toISOString(), score };
  await storage.put("sessions", ended);
  await enqueueUpsert(queue, "game_sessions", ended.id, ended);
  return ended;
}
