// Framework-agnostic types for the sync queue. No react/DOM/window/document
// imports here per the PORTABILITY RULES — this file must compile unchanged
// for a future React Native build.
import type { SyncOpIn as SyncOp, SyncPushResponse, SyncPullResponse } from "@smaran/contracts";
export type { SyncOp };

export type QueueStatus = "pending" | "sending" | "sent" | "rejected";

export interface QueuedOp extends SyncOp {
  status: QueueStatus;
  attempts: number;
  last_error?: string;
  next_attempt_at?: string; // ISO-8601, used for backoff scheduling
}

/**
 * Implemented per-platform: Dexie/IndexedDB on web (see
 * apps/patient-web/src/adapters/web/StorageAdapter.ts), SQLite later on
 * native. sync-core only ever talks to this interface.
 */
export interface SyncQueueStorage {
  enqueue(op: QueuedOp): Promise<void>;
  listPending(): Promise<QueuedOp[]>;
  markStatus(op_id: string, status: QueueStatus, error?: string): Promise<void>;
  scheduleRetry(op_id: string, next_attempt_at: string, error: string): Promise<void>;
  removeSent(op_ids: string[]): Promise<void>;
  getCursor(): Promise<string | null>;
  setCursor(cursor: string): Promise<void>;
  /** Apply a batch of pulled remote ops to local stores (caller-supplied, per entity). */
  applyRemoteChanges(changes: SyncPullResponse["changes"]): Promise<void>;
}

export type PushFn = (req: {
  device_id: string;
  ops: SyncOp[];
}) => Promise<SyncPushResponse>;

export type PullFn = (since: string | null) => Promise<SyncPullResponse>;

export interface SyncClientConfig {
  device_id: string;
  storage: SyncQueueStorage;
  push: PushFn;
  pull: PullFn;
  maxBatchSize?: number; // default 50
  onStatusChange?: (status: "idle" | "syncing" | "offline" | "error") => void;
}
