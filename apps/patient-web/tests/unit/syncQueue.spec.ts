import { describe, expect, it } from "vitest";
import { SyncQueue, type QueuedOp, type SyncQueueStorage } from "@smaran/sync-core";

function memStorage(): SyncQueueStorage & { ops: Map<string, QueuedOp> } {
  const ops = new Map<string, QueuedOp>();
  let cursor: string | null = null;
  return {
    ops,
    async enqueue(op) { ops.set(op.op_id, op); },
    async listPending() { return [...ops.values()].filter((o) => o.status === "pending" || o.status === "sending"); },
    async markStatus(id, status, error) { const o = ops.get(id); if (o) ops.set(id, { ...o, status, last_error: error }); },
    async scheduleRetry(id, next, error) { const o = ops.get(id)!; ops.set(id, { ...o, status: "pending", attempts: o.attempts + 1, next_attempt_at: next, last_error: error }); },
    async removeSent(ids) { ids.forEach((i) => ops.delete(i)); },
    async getCursor() { return cursor; },
    async setCursor(c) { cursor = c; },
    async applyRemoteChanges() {}
  };
}

const op = (id: string, entity = "game_sessions") => ({ op_id: id, entity, entity_id: id, action: "upsert" as const, payload: {} });

describe("SyncQueue (SYNC CONTRACT)", () => {
  it("only lets devices push the four contract entities", async () => {
    const q = new SyncQueue({ device_id: "d", storage: memStorage(), push: async () => ({ accepted: [], rejected: [], server_cursor: 1 }), pull: async () => ({ changes: [], server_cursor: 1 }) });
    await expect(q.enqueue(op("a", "reminders"))).rejects.toThrow();
    await expect(q.enqueue(op("b", "reminder_events"))).resolves.toBeUndefined();
  });
  it("refuses delete on append-only entities", async () => {
    const q = new SyncQueue({ device_id: "d", storage: memStorage(), push: async () => ({ accepted: [], rejected: [], server_cursor: 1 }), pull: async () => ({ changes: [], server_cursor: 1 }) });
    await expect(q.enqueue({ ...op("a"), action: "delete" })).rejects.toThrow();
  });
  it("keeps ops on network failure (backoff) and replays them with the SAME op_id", async () => {
    const storage = memStorage();
    let online = false; const seen: string[] = [];
    const q = new SyncQueue({ device_id: "d", storage, push: async (r) => { if (!online) throw new Error("offline"); r.ops.forEach((o) => seen.push(o.op_id)); return { accepted: r.ops.map((o) => o.op_id), rejected: [], server_cursor: 7 }; }, pull: async () => ({ changes: [], server_cursor: 7 }) });
    await q.enqueue(op("x1")); await q.enqueue(op("x2"));
    await q.pushPending();
    expect(storage.ops.size).toBe(2);
    expect(storage.ops.get("x1")!.attempts).toBe(1);
    online = true;
    await q.pushPending(() => new Date(Date.now() + 10 * 60_000)); // past any backoff window
    expect(seen).toEqual(["x1", "x2"]);
    expect(storage.ops.size).toBe(0);
  });
  it("stores a numeric server cursor as a string", async () => {
    const storage = memStorage();
    const q = new SyncQueue({ device_id: "d", storage, push: async () => ({ accepted: [], rejected: [], server_cursor: 1 }), pull: async () => ({ changes: [], server_cursor: 42 }) });
    await q.pull();
    expect(await storage.getCursor()).toBe("42");
  });
});
