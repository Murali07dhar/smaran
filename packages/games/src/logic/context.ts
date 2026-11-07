import type { GameEvent, GameEventType, GameId, SessionSummary } from '../types';
import { createRng, type Rng } from './rng';
import { createEventFactory, type EventExtras } from './events';
import { summarize } from './summary';

export interface GameContext {
  session_id: string; rng: Rng; now: () => number; startedAt: number; events: GameEvent[];
  event(type: GameEventType, item_id: string, x?: EventExtras): GameEvent;
  summary(game_id: GameId, difficulty: number): SessionSummary;
}
export interface ContextOptions { session_id: string; seed?: number | string; now?: () => number; onEvent?: (e: GameEvent) => void; id?: () => string }

export function createGameContext(o: ContextOptions): GameContext {
  const now = o.now ?? Date.now;
  const factory = createEventFactory({ session_id: o.session_id, now, id: o.id });
  const events: GameEvent[] = [];
  const startedAt = now();
  return {
    session_id: o.session_id, rng: createRng(o.seed ?? o.session_id), now, startedAt, events,
    event(type, item_id, x) { const e = factory.make(type, item_id, x); events.push(e); o.onEvent?.(e); return e; },
    summary(game_id, difficulty) {
      return summarize(events, { session_id: o.session_id, game_id, difficulty, started_at: new Date(startedAt).toISOString(), completed_at: new Date(now()).toISOString() });
    },
  };
}
