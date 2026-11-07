import { PUSH_ENTITIES } from "@smaran/contracts";
import type { SyncOp } from "./types";
import type { SyncClientConfig, QueuedOp } from "./types";
import { shouldQueueLocalMutation } from "./conflictRules";
import { nextAttemptIso } from "./backoff";

/**
 * Framework-agnostic sync queue. Speaks the SYNC CONTRACT from the shared
 * briefing: POST /sync/push, GET /sync/pull?since=cursor, idempotent by
 * op_id, append-only entities for GameSession/GameEvent/EmotionSample.
 *
 * No DOM/window/react imports — the web app wires this to Dexie storage and
 * a fetch-based push/pull; a future native app wires it to SQLite + its own
 * transport, unchanged.
 */
export class SyncQueue {
  private cfg: Required<Pick<SyncClientConfig, "maxBatchSize">> & SyncClientConfig;
  private syncing = false;

  constructor(config: SyncClientConfig) {
    this.cfg = { maxBatchSize: 50, ...config };
  }

  async enqueue(op: Omit<SyncOp, "client_ts"> & { client_ts?: string }): Promise<void> {
    if (!shouldQueueLocalMutation(op.entity, op.action)) {
      throw new Error(`Illegal local delete on append-only entity: ${op.entity}`);
    }
    if (!(PUSH_ENTITIES as readonly string[]).includes(op.entity)) {
      throw new Error(`Entity not pushable by devices per SYNC CONTRACT: ${op.entity}`);
    }
    const queued: QueuedOp = {
      ...op,
      client_ts: op.client_ts ?? new Date().toISOString(),
      status: "pending",
      attempts: 0
    };
    await this.cfg.storage.enqueue(queued);
  }

  /** Push all pending ops in batches; safe to call repeatedly (e.g. on reconnect). */
  async pushPending(now: () => Date = () => new Date()): Promise<{ pushed: number; rejected: number }> {
    const { storage, push, maxBatchSize } = this.cfg;
    let pushed = 0;
    let rejected = 0;
    const pending = (await storage.listPending()).filter(
      (op) => !op.next_attempt_at || new Date(op.next_attempt_at) <= now()
    );
    if (pending.length === 0) return { pushed, rejected };

    for (let i = 0; i < pending.length; i += maxBatchSize) {
      const batch = pending.slice(i, i + maxBatchSize);
      for (const op of batch) await storage.markStatus(op.op_id, "sending");
      try {
        const res = await push({ device_id: this.cfg.device_id, ops: batch });
        if (res.accepted.length) await storage.removeSent(res.accepted);
        pushed += res.accepted.length;
        for (const r of res.rejected) {
          rejected += 1;
          await storage.markStatus(r.op_id, "rejected", r.reason);
        }
      } catch (err) {
        // Network/server failure: schedule exponential backoff per-op.
        for (const op of batch) {
          const attempts = op.attempts + 1;
          await storage.scheduleRetry(
            op.op_id,
            nextAttemptIso(attempts, now),
            err instanceof Error ? err.message : "unknown error"
          );
        }
      }
    }
    return { pushed, rejected };
  }

  async pull(): Promise<{ applied: number; cursor: string }> {
    const { storage, pull } = this.cfg;
    const since = await storage.getCursor();
    const res = await pull(since);
    if (res.changes.length) await storage.applyRemoteChanges(res.changes);
    const cursor = String(res.server_cursor); // server cursor is BIGSERIAL: number or string on the wire
    await storage.setCursor(cursor);
    return { applied: res.changes.length, cursor };
  }

  /** Full sync cycle: push local changes, then pull remote changes. */
  async syncOnce(): Promise<void> {
    if (this.syncing) return;
    this.syncing = true;
    this.cfg.onStatusChange?.("syncing");
    try {
      await this.pushPending();
      await this.pull();
      this.cfg.onStatusChange?.("idle");
    } catch (err) {
      this.cfg.onStatusChange?.("error");
      throw err;
    } finally {
      this.syncing = false;
    }
  }
}
