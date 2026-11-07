import type { Cue, GameEvent, Observation } from '../types';
/** Derives AI-service observations (POST /ai/triggers/update) from raw events: first answer per (item, with_cue) arm. */
export function toObservations(events: readonly GameEvent[], cues: readonly Cue[]): Observation[] {
  const byId = new Map(cues.map((c) => [c.cue_id, c]));
  const seen = new Set<string>();
  const out: Observation[] = [];
  for (const e of events) {
    if (e.type !== 'answer') continue;
    const key = `${e.item_id}|${e.with_cue}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const cue = e.cue_id ? byId.get(e.cue_id) : cues.find((c) => c.item_id === e.item_id);
    out.push({ cue_id: cue?.cue_id ?? null, cue_type: cue?.cue_type ?? null, valence_label: cue?.valence_label ?? 'neutral', recalled: !!e.correct, with_cue: e.with_cue, ts: e.ts });
  }
  return out;
}
