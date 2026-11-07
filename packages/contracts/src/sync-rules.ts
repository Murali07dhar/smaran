// Sync rules shared by clients (hand-written; the server enforces the same lists).
// Entities a device may PUSH (all append-only).
export const PUSH_ENTITIES = ["game_sessions", "game_events", "emotion_samples", "reminder_events"] as const;
// Entities a device PULLs (server-authored, last-write-wins by server_version).
export const PULL_ENTITIES = ["reminders", "routines", "media_assets", "memory_triggers", "alerts"] as const;
export const APPEND_ONLY_ENTITIES = ["game_sessions", "game_events", "emotion_samples", "reminder_events"] as const;
