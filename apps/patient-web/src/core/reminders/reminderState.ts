import type { ReminderOut as Reminder } from "@smaran/contracts";
import { ReminderEngine, type Reminder as EngineReminder } from "@smaran/voice-i18n";
import type { StorageAdapter } from "../../adapters/types";
import { uuid7, SyncQueue } from "@smaran/sync-core";

export interface AckRecord {
  id: string; // reminder_id, one row per reminder tracks the latest ack
  reminder_id: string;
  status: "done" | "later";
  acked_at: string;
  miss_count: number;
}

const ACK_TABLE = "kv"; // small table; keyed as `ack:<reminder_id>`

function ackKey(reminderId: string) {
  return `ack:${reminderId}`;
}

// One shared engine per app session (pure, offline; see packages/voice-i18n/core/reminderEngine.ts).
const engine = new ReminderEngine();
const dueTsById = new Map<string, number>();
const seen = new Set<string>();
const reportedMisses = new Set<string>();
const pendingMisses: Array<{ reminder_id: string; due_ts: number; at: number }> = [];
const FIRST_LOOKBACK_MS = 90_000;

/** The single reminder (if any) that should be shown as a full-screen alert right now. */
export function getDueReminder(reminders: Reminder[], now: Date): Reminder | null {
  const ms = now.getTime();
  const live = new Set<string>();
  for (const r of reminders) {
    if (r.active === false) continue;
    live.add(r.id);
    // First sight: look back one tick interval + slack so an occurrence that just came due is not skipped.
    engine.upsert(r as unknown as EngineReminder, seen.has(r.id) ? ms : ms - FIRST_LOOKBACK_MS);
    seen.add(r.id);
  }
  for (const id of dueTsById.keys()) if (!live.has(id)) dueTsById.delete(id);
  for (const ev of engine.tick(ms)) {
    if (ev.type === "missed" && !reportedMisses.has(`${ev.reminder_id}:${ev.due_ts}`)) {
      reportedMisses.add(`${ev.reminder_id}:${ev.due_ts}`);
      pendingMisses.push({ reminder_id: ev.reminder_id, due_ts: ev.due_ts, at: ev.at });
    }
  }
  const active = engine.active();
  dueTsById.clear();
  for (const a of active) dueTsById.set(a.reminder.id, a.due_ts);
  const first = active.find((a) => live.has(a.reminder.id));
  return first ? (reminders.find((r) => r.id === first.reminder.id) ?? null) : null;
}

export async function getLastAck(storage: StorageAdapter, reminderId: string): Promise<AckRecord | undefined> {
  const row = await storage.get<{ id: string; value: AckRecord }>(ACK_TABLE, ackKey(reminderId));
  return row?.value;
}

/**
 * Records a Done/Later response locally (so the UI can dismiss instantly,
 * offline included) and queues it for sync.
 *
 * Sync: an ack is an append-only `reminder_events` op (no dedicated endpoint needed).
 */
export async function recordReminderAck(
  storage: StorageAdapter,
  queue: SyncQueue,
  reminder: Reminder,
  status: "done" | "later",
  dueAt?: string
): Promise<void> {
  const dueTs = dueTsById.get(reminder.id);
  if (dueTs !== undefined) {
    if (status === "done") engine.acknowledge(reminder.id, dueTs, Date.now());
    else engine.snooze(reminder.id, dueTs, Date.now());
    dueAt = dueAt ?? new Date(dueTs).toISOString();
  }
  const previous = await getLastAck(storage, reminder.id);
  const miss_count = status === "later" ? (previous?.miss_count ?? 0) + 1 : 0;
  const record: AckRecord = {
    id: ackKey(reminder.id),
    reminder_id: reminder.id,
    status,
    acked_at: new Date().toISOString(),
    miss_count
  };
  await storage.put(ACK_TABLE, { id: record.id, value: record });

  // Ack = append-only reminder_events row (schema: id, reminder_id, patient_id, due_at, status, ts).
  const event_id = uuid7();
  await queue.enqueue({
    op_id: uuid7(),
    entity: "reminder_events",
    entity_id: event_id,
    action: "upsert",
    payload: {
      id: event_id,
      reminder_id: reminder.id,
      patient_id: reminder.patient_id,
      due_at: dueAt ?? record.acked_at,
      status,
      ts: record.acked_at
    }
  });
}

export function shouldEscalate(reminder: Reminder, ack: AckRecord | undefined): boolean {
  return !!ack && ack.miss_count >= reminder.escalate_after_misses;
}

/** Test hook: forget engine state (the engine is a per-session singleton). */
/** Missed occurrences found by the engine since the last call (each reported once). */
export function takeMissedEvents() {
  return pendingMisses.splice(0, pendingMisses.length);
}

/** A missed occurrence is an append-only `reminder_events` row (status `missed`); drives the missed_reminders alert. */
export async function recordMissedReminders(
  _storage: StorageAdapter, queue: SyncQueue, reminders: Reminder[],
  missed: Array<{ reminder_id: string; due_ts: number; at: number }>
): Promise<void> {
  for (const m of missed) {
    const reminder = reminders.find((r) => r.id === m.reminder_id);
    if (!reminder) continue;
    const id = uuid7();
    const ts = new Date(m.at).toISOString();
    const row = { id, reminder_id: reminder.id, patient_id: reminder.patient_id, due_at: new Date(m.due_ts).toISOString(), status: "missed", ts };
    await queue.enqueue({ op_id: uuid7(), entity: "reminder_events", entity_id: id, action: "upsert", payload: row });
  }
}

export function resetReminderState(): void {
  reportedMisses.clear();
  pendingMisses.length = 0;
  for (const id of [...seen]) engine.remove(id);
  seen.clear();
  dueTsById.clear();
}
