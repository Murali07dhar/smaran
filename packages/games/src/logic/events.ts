import type { Cue, GameEvent, GameEventType } from '../types';
import { uuidv7 } from './uuid7';

export const EVENT_TYPES: readonly GameEventType[] = ['item_shown', 'answer', 'hint_used', 'cue_shown', 'timeout', 'reaction'];
const ALLOWED = new Set(['event_id', 'session_id', 'type', 'item_id', 'correct', 'response_ms', 'cue_id', 'with_cue', 'ts']);
const UUID7 = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const ISO_Z = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/;

/** Returns a list of problems; empty list means the event is a valid GameEvent. */
export function validateGameEvent(e: unknown): string[] {
  if (typeof e !== 'object' || e === null || Array.isArray(e)) return ['event must be an object'];
  const o = e as Record<string, unknown>;
  const errs: string[] = [];
  for (const k of Object.keys(o)) if (!ALLOWED.has(k)) errs.push(`unknown field: ${k}`);
  for (const k of ['event_id', 'session_id', 'item_id']) if (typeof o[k] !== 'string' || !(o[k] as string).length) errs.push(`${k} must be a non-empty string`);
  if (typeof o.event_id === 'string' && !UUID7.test(o.event_id)) errs.push('event_id must be a UUIDv7');
  if (!(EVENT_TYPES as readonly string[]).includes(o.type as string)) errs.push('type is not a valid GameEventType');
  if (typeof o.with_cue !== 'boolean') errs.push('with_cue must be boolean');
  if (o.correct !== undefined && typeof o.correct !== 'boolean') errs.push('correct must be boolean');
  if (o.response_ms !== undefined && (!Number.isInteger(o.response_ms) || (o.response_ms as number) < 0)) errs.push('response_ms must be an integer >= 0');
  if (o.cue_id !== undefined && (typeof o.cue_id !== 'string' || !o.cue_id)) errs.push('cue_id must be a non-empty string');
  if (typeof o.with_cue === 'boolean' && o.with_cue !== (o.cue_id !== undefined)) errs.push('with_cue must be true exactly when cue_id is present');
  if (typeof o.ts !== 'string' || !ISO_Z.test(o.ts) || Number.isNaN(Date.parse(o.ts))) errs.push('ts must be ISO-8601 UTC');
  return errs;
}

export interface EventExtras { correct?: boolean; response_ms?: number; cue?: Cue | null }
export interface EventFactory { make(type: GameEventType, item_id: string, x?: EventExtras): GameEvent }
export function createEventFactory(o: { session_id: string; now?: () => number; id?: () => string }): EventFactory {
  const now = o.now ?? Date.now;
  return {
    make(type, item_id, x = {}) {
      const t = now();
      const e: GameEvent = { event_id: o.id ? o.id() : uuidv7(t), session_id: o.session_id, type, item_id, with_cue: !!x.cue, ts: new Date(t).toISOString() };
      if (x.correct !== undefined) e.correct = x.correct;
      if (x.response_ms !== undefined) e.response_ms = Math.max(0, Math.round(x.response_ms));
      if (x.cue) e.cue_id = x.cue.cue_id;
      return e;
    },
  };
}
