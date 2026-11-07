import type { SyncQueueStorage, QueuedOp, QueueStatus } from "@smaran/sync-core";
import { isAppendOnly } from "@smaran/sync-core";
import type { SyncPullResponse } from "@smaran/contracts";
import type { StorageAdapter } from "../../adapters/types";

const QUEUE_TABLE = "syncQueue";
const CURSOR_KEY = "sync_cursor";

// Entity name (as used in SyncOp.entity, per the shared contract) -> local
// Dexie table name. Keep in sync with the CORE ENTITIES this app owns.
// PULLED entity (sync_changes.entity, per SYNC CONTRACT) -> local Dexie table. Pushed entities are written
// by core/games, core/emotion and core/reminders directly; they are never pulled.
const ENTITY_TABLE: Record<string, string> = {
  reminders: "reminders",
  routines: "routines",
  media_assets: "media",
  memory_triggers: "memoryTriggers",
  alerts: "alerts"
};

function tableFor(entity: string): string | undefined {
  return ENTITY_TABLE[entity];
}

export function createQueueStorage(storage: StorageAdapter): SyncQueueStorage {
  return {
    async enqueue(op: QueuedOp) {
      await storage.put(QUEUE_TABLE, op);
    },
    async listPending() {
      return storage.query<QueuedOp>(QUEUE_TABLE, (op) => op.status === "pending" || op.status === "sending");
    },
    async markStatus(op_id: string, status: QueueStatus, error?: string) {
      const op = await storage.get<QueuedOp>(QUEUE_TABLE, op_id);
      if (!op) return;
      await storage.put(QUEUE_TABLE, { ...op, status, last_error: error });
    },
    async scheduleRetry(op_id: string, next_attempt_at: string, error: string) {
      const op = await storage.get<QueuedOp>(QUEUE_TABLE, op_id);
      if (!op) return;
      await storage.put(QUEUE_TABLE, {
        ...op,
        status: "pending",
        attempts: op.attempts + 1,
        next_attempt_at,
        last_error: error
      });
    },
    async removeSent(op_ids: string[]) {
      for (const id of op_ids) await storage.delete(QUEUE_TABLE, id);
    },
    async getCursor() {
      const row = await storage.get<{ id: string; value: string }>("kv", CURSOR_KEY);
      return row?.value ?? null;
    },
    async setCursor(cursor: string) {
      await storage.put("kv", { id: CURSOR_KEY, value: cursor });
    },
    async applyRemoteChanges(changes: SyncPullResponse["changes"]) {
      for (const op of changes) {
        const table = tableFor(op.entity);
        if (!table) continue; // unknown/non-pulled entity: skip rather than abort the whole pull
        if (op.action === "delete") {
          if (isAppendOnly(op.entity)) continue; // append-only entities are never deleted
          await storage.delete(table, op.entity_id);
        } else {
          const row: Record<string, unknown> = { id: op.entity_id, ...op.payload };
          // Tolerate the DB column name on reminders (wire field is `schedule`).
          if (op.entity === "reminders" && row.schedule === undefined && row.schedule_rrule !== undefined) {
            row.schedule = row.schedule_rrule;
            delete row.schedule_rrule;
          }
          await storage.put(table, row);
        }
      }
    }
  };
}
