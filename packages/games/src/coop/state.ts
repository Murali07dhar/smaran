import type { CoopMessage, Role } from '../types';
import { fromOf, type Progress } from './protocol';

/** Shared co-op view state. Both UIs render from this; the server (or mock bus) is authoritative on seq. */
export interface CoopViewState {
  seq: number;
  peers: { patient: boolean; family: boolean };
  progress: Progress | null;
  hint: { item_id: string; n: number } | null;
  encourage: { text_key: string; n: number } | null;
  picked_item_ids: string[] | null;
}
export const initialCoopState: CoopViewState = { seq: 0, peers: { patient: false, family: false }, progress: null, hint: null, encourage: null, picked_item_ids: null };

export function applyMessage(s: CoopViewState, m: CoopMessage, self: Role): CoopViewState {
  if (m.seq <= s.seq) return s; // duplicate or out-of-order: ignore
  const base = { ...s, seq: m.seq };
  const from = fromOf(m);
  const p = m.payload;
  switch (m.type) {
    case 'join': return from ? { ...base, peers: { ...s.peers, [from]: true } } : base;
    case 'leave': return from ? { ...base, peers: { ...s.peers, [from]: false } } : base;
    case 'state_patch':
      if (from === self) return base;
      if (p.kind === 'progress') return { ...base, progress: p.progress as Progress };
      if (p.kind === 'picks') return { ...base, picked_item_ids: p.item_ids as string[] };
      return base;
    case 'hint': return from === self ? base : { ...base, hint: { item_id: String(p.item_id), n: (s.hint?.n ?? 0) + 1 } };
    case 'encourage': return from === self ? base : { ...base, encourage: { text_key: String(p.text_key), n: (s.encourage?.n ?? 0) + 1 } };
    default: return base;
  }
}
