import { APPEND_ONLY_ENTITIES } from "@smaran/contracts";

export function isAppendOnly(entity: string): boolean {
  return (APPEND_ONLY_ENTITIES as readonly string[]).includes(entity);
}

/**
 * Per the sync contract: GameSession/GameEvent/EmotionSample are append-only
 * (never overwritten, never deleted locally after sync). Everything else is
 * last-write-wins by server_version, which the server arbitrates — the
 * client's job is just to never resubmit an op that was already accepted
 * (idempotency by op_id) and to accept whatever the server returns on pull.
 */
export function shouldQueueLocalMutation(entity: string, action: "upsert" | "delete"): boolean {
  if (isAppendOnly(entity) && action === "delete") {
    // Append-only entities are never locally deleted; guard against bugs
    // upstream from ever producing such an op.
    return false;
  }
  return true;
}
