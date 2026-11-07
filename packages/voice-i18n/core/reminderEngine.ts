// Pure reminder engine. No UI, no DOM, no timers: the host calls tick(now) (setInterval, app resume,
// background-fetch, or WorkManager later). Fully offline. State is plain JSON so any storage can persist it.
import type { Reminder } from './types';
import { occurrencesBetween, parseSchedule, type ParsedRule } from './rrule';

export type OccStatus = 'fired' | 'snoozed' | 'acked' | 'missed';

export interface Occurrence {
  due_ts: number;       // scheduled UTC ms (identity of the occurrence)
  status: OccStatus;
  fire_at: number;      // when it last (or next) fires: due_ts, or snooze target
  snoozes: number;
  acked_ts?: number;
}

export interface ReminderState {
  last_tick_ms: number;
  occurrences: Record<string, Occurrence>;
  consecutive_misses: number;
  escalated: boolean;
}

export type EngineState = Record<string, ReminderState>;

export type EngineEvent =
  | { type: 'due'; reminder_id: string; due_ts: number; snoozed: boolean; at: number }
  | { type: 'missed'; reminder_id: string; due_ts: number; consecutive_misses: number; at: number }
  | { type: 'acknowledged'; reminder_id: string; due_ts: number; at: number }
  | {
      type: 'escalation'; // alert event for the caregiver (API maps to Alert entity)
      reminder_id: string; patient_id: string; category: Reminder['category'];
      title: string; consecutive_misses: number; due_ts: number; at: number;
    };

export interface EngineConfig {
  graceMs: number;          // time after fire before an unacknowledged occurrence counts as missed
  maxSnoozes: number;
  defaultSnoozeMin: number;
  maxLookbackMs: number;    // offline catch-up window
  keepOccurrencesMs: number;
}
export const DEFAULT_CONFIG: EngineConfig = {
  graceMs: 30 * 60_000,
  maxSnoozes: 3,
  defaultSnoozeMin: 10,
  maxLookbackMs: 72 * 3600_000, // offline catch-up: up to 3 days of misses are counted
  keepOccurrencesMs: 7 * 24 * 3600_000,
};

interface Entry { reminder: Reminder; rule: ParsedRule; anchorMs: number }

export class ReminderEngine {
  private entries = new Map<string, Entry>();
  private state: EngineState;
  readonly config: EngineConfig;

  constructor(state: EngineState = {}, config: Partial<EngineConfig> = {}) {
    this.state = state;
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  /** Add or replace a reminder. anchorMs is used as DTSTART day if the schedule has none. */
  upsert(reminder: Reminder, nowMs: number, defaultTz?: string) {
    const prev = this.entries.get(reminder.id);
    const anchorMs = prev?.anchorMs ?? nowMs;
    const rule = parseSchedule(reminder.schedule, { defaultTz, anchorMs });
    this.entries.set(reminder.id, { reminder, rule, anchorMs });
    if (!this.state[reminder.id]) {
      // New reminders never back-fire: start counting from now.
      this.state[reminder.id] = { last_tick_ms: nowMs, occurrences: {}, consecutive_misses: 0, escalated: false };
    }
  }

  remove(id: string) { this.entries.delete(id); delete this.state[id]; }

  getState(): EngineState { return JSON.parse(JSON.stringify(this.state)); }

  /** Evaluate everything between last tick and now. Returns events in chronological order. */
  tick(nowMs: number): EngineEvent[] {
    const events: EngineEvent[] = [];
    for (const [id, e] of this.entries) {
      const st = this.state[id];
      if (nowMs < st.last_tick_ms) { st.last_tick_ms = nowMs; continue; } // clock moved backwards: be safe
      const from = Math.max(st.last_tick_ms + 1, nowMs - this.config.maxLookbackMs);
      for (const due of occurrencesBetween(e.rule, from, nowMs + 1)) {
        const key = String(due);
        if (st.occurrences[key]) continue;
        const overdue = nowMs >= due + this.config.graceMs;
        st.occurrences[key] = { due_ts: due, status: 'fired', fire_at: due, snoozes: 0 };
        // Occurrences already past grace (device was off/offline) are missed silently: no late voice prompt.
        if (!overdue) events.push({ type: 'due', reminder_id: id, due_ts: due, snoozed: false, at: nowMs });
      }
      // Snooze wake-ups and miss detection
      const occs = Object.values(st.occurrences).sort((a, b) => a.due_ts - b.due_ts);
      for (const o of occs) {
        if (o.status === 'snoozed' && nowMs >= o.fire_at) {
          o.status = 'fired';
          events.push({ type: 'due', reminder_id: id, due_ts: o.due_ts, snoozed: true, at: nowMs });
        }
        if (o.status === 'fired' && nowMs >= o.fire_at + this.config.graceMs) {
          o.status = 'missed';
          st.consecutive_misses++;
          events.push({ type: 'missed', reminder_id: id, due_ts: o.due_ts, consecutive_misses: st.consecutive_misses, at: nowMs });
          const thr = e.reminder.escalate_after_misses;
          if (thr > 0 && st.consecutive_misses >= thr && !st.escalated) {
            st.escalated = true;
            events.push({
              type: 'escalation', reminder_id: id, patient_id: e.reminder.patient_id,
              category: e.reminder.category, title: e.reminder.title,
              consecutive_misses: st.consecutive_misses, due_ts: o.due_ts, at: nowMs,
            });
          }
        }
      }
      st.last_tick_ms = nowMs;
      // prune
      for (const k of Object.keys(st.occurrences)) {
        if (st.occurrences[k].due_ts < nowMs - this.config.keepOccurrencesMs) delete st.occurrences[k];
      }
    }
    return events;
  }

  /** Patient (or caregiver) confirms. Resets the miss streak. Late acks of a missed item are accepted. */
  acknowledge(reminderId: string, dueTs: number, nowMs: number): EngineEvent | null {
    const st = this.state[reminderId];
    const o = st?.occurrences[String(dueTs)];
    if (!o || o.status === 'acked') return null;
    const wasMissed = o.status === 'missed';
    o.status = 'acked';
    o.acked_ts = nowMs;
    if (wasMissed && st.consecutive_misses > 0) st.consecutive_misses--;
    if (!wasMissed) st.consecutive_misses = 0;
    if (st.consecutive_misses === 0) st.escalated = false;
    return { type: 'acknowledged', reminder_id: reminderId, due_ts: dueTs, at: nowMs };
  }

  /** Snooze an active occurrence. Returns the new fire time, or null if not allowed (max snoozes reached). */
  snooze(reminderId: string, dueTs: number, nowMs: number, minutes?: number): number | null {
    const o = this.state[reminderId]?.occurrences[String(dueTs)];
    if (!o || (o.status !== 'fired' && o.status !== 'snoozed')) return null;
    if (o.snoozes >= this.config.maxSnoozes) return null;
    o.snoozes++;
    o.status = 'snoozed';
    o.fire_at = nowMs + (minutes ?? this.config.defaultSnoozeMin) * 60_000;
    return o.fire_at;
  }

  /** Currently active (fired, unacknowledged) occurrences, for the UI. */
  active(): Array<{ reminder: Reminder; due_ts: number; snoozes: number }> {
    const res: Array<{ reminder: Reminder; due_ts: number; snoozes: number }> = [];
    for (const [id, e] of this.entries) {
      for (const o of Object.values(this.state[id]?.occurrences ?? {})) {
        if (o.status === 'fired') res.push({ reminder: e.reminder, due_ts: o.due_ts, snoozes: o.snoozes });
      }
    }
    return res.sort((a, b) => a.due_ts - b.due_ts);
  }
}
