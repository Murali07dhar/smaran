import Dexie, { type Table } from "dexie";

// Tables map 1:1 onto the CORE ENTITIES the patient app owns locally, plus
// `syncQueue` (sync-core's QueuedOp), `files` (blob store for FileAdapter)
// and `kv` (small misc values: auth tokens, sync cursor, cached profile).
export class SmaranDB extends Dexie {
  sessions!: Table<any, string>;
  events!: Table<any, string>;
  emotionSamples!: Table<any, string>;
  reminders!: Table<any, string>;
  media!: Table<any, string>;
  consent!: Table<any, string>;
  routines!: Table<any, string>;
  memoryTriggers!: Table<any, string>;
  alerts!: Table<any, string>;
  syncQueue!: Table<any, string>;
  files!: Table<{ id: string; blob: Blob }, string>;
  kv!: Table<{ id: string; value: unknown }, string>;

  constructor() {
    super("smaran-patient-web");
    this.version(1).stores({
      sessions: "id, patient_id, game_id",
      events: "id, session_id",
      emotionSamples: "id, patient_id, session_id, ts",
      reminders: "id, patient_id, category",
      media: "id, patient_id, kind",
      consent: "id, patient_id",
      syncQueue: "op_id, status, next_attempt_at",
      files: "id",
      kv: "id"
    });
    // v2: tables for pulled entities (routines, memory_triggers, alerts)
    this.version(2).stores({
      routines: "id, patient_id",
      memoryTriggers: "id, patient_id",
      alerts: "id, patient_id"
    });
  }
}

export const db = new SmaranDB();
