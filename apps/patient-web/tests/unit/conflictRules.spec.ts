import { describe, expect, it } from "vitest";
import { isAppendOnly, shouldQueueLocalMutation } from "@smaran/sync-core";

describe("append-only entity rules", () => {
  it("flags game_sessions, game_events, emotion_samples, reminder_events as append-only", () => {
    expect(isAppendOnly("game_sessions")).toBe(true);
    expect(isAppendOnly("reminder_events")).toBe(true);
    expect(isAppendOnly("game_events")).toBe(true);
    expect(isAppendOnly("emotion_samples")).toBe(true);
    expect(isAppendOnly("reminders")).toBe(false);
  });

  it("refuses a local delete on an append-only entity", () => {
    expect(shouldQueueLocalMutation("emotion_samples", "delete")).toBe(false);
    expect(shouldQueueLocalMutation("emotion_samples", "upsert")).toBe(true);
    expect(shouldQueueLocalMutation("reminders", "delete")).toBe(true);
  });
});
