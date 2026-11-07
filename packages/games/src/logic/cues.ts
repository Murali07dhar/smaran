import type { Cue } from '../types';
import type { Rng } from './rng';

export interface CueSlot { key: string; item_id?: string }
/**
 * Randomises with-cue vs without-cue. Exactly floor(n/2) slots (+1 by coin flip when n is odd) get a cue,
 * so the two arms stay balanced for the functional-impact comparison. No cues supplied => all null.
 * Cues linked to an item (cue.item_id) are preferred for that item; otherwise generic cues are used round-robin.
 */
export function assignCues(slots: readonly CueSlot[], cues: readonly Cue[], rng: Rng): Map<string, Cue | null> {
  const out = new Map<string, Cue | null>();
  slots.forEach((s) => out.set(s.key, null));
  if (!cues.length || !slots.length) return out;
  const n = slots.length;
  let nWith = Math.floor(n / 2);
  if (n % 2 === 1 && rng.chance(0.5)) nWith += 1;
  const chosen = rng.shuffle(slots).slice(0, nWith);
  const shuffled = rng.shuffle(cues);
  const generic = shuffled.filter((c) => !c.item_id);
  const rr = generic.length ? generic : shuffled;
  const used = new Set<string>();
  let k = 0;
  for (const s of chosen) {
    let cue = s.item_id ? shuffled.find((c) => c.item_id === s.item_id && !used.has(c.cue_id)) : undefined;
    if (!cue) cue = rr[k++ % rr.length];
    used.add(cue.cue_id);
    out.set(s.key, cue);
  }
  return out;
}
