import type { ContentItem, Cue } from '../../types';
import type { GameContext } from '../context';
import { assignCues } from '../cues';
import { paramsFor } from '../difficulty';
import { objectPool } from '../pool';

export interface TapCell { cell_id: string; item: ContentItem }
export interface TapRound { target: ContentItem; cells: TapCell[]; targetCells: Set<string>; cue: Cue | null }
/** Target tapping (attention). No timers: response_ms is only measured, never shown or enforced. */
export class TapEngine {
  readonly rounds: TapRound[] = [];
  index = 0; found = new Set<string>(); missed = new Set<string>(); wrongStreak = 0; hints = 0; solved = false; finished = false;
  private lastAt = 0; private started = false;
  constructor(content: readonly ContentItem[], difficulty: number, private ctx: GameContext, cues: readonly Cue[] = []) {
    const p = paramsFor('target_tap', difficulty);
    const pool = objectPool(content);
    if (pool.length < 2) return;
    const { rng } = ctx;
    let bag = rng.shuffle(pool);
    for (let r = 0; r < p.rounds; r++) {
      if (!bag.length) bag = rng.shuffle(pool);
      const target = bag.pop()!;
      const cellsN = Math.max(2, p.cells), tN = Math.min(p.targets, cellsN - 1);
      const others = pool.filter((i) => i.id !== target.id);
      const same = others.filter((i) => i.category === target.category);
      const dp = p.similar_distractors && same.length ? same : others;
      const list: ContentItem[] = [...Array(tN).fill(target), ...Array.from({ length: cellsN - tN }, () => rng.pick(dp))];
      const cells = rng.shuffle(list).map((item, i) => ({ cell_id: `c${i}`, item }));
      this.rounds.push({ target, cells, targetCells: new Set(cells.filter((c) => c.item.id === target.id).map((c) => c.cell_id)), cue: null });
    }
    const m = assignCues(this.rounds.map((r, i) => ({ key: `r${i}`, item_id: r.target.id })), cues, rng);
    this.rounds.forEach((r, i) => { r.cue = m.get(`r${i}`) ?? null; });
  }
  get ready() { return this.rounds.length > 0; }
  get total() { return this.rounds.length; }
  get round(): TapRound | undefined { return this.rounds[this.index]; }
  get hintSuggested() { return this.wrongStreak >= 2; }
  cueFor(item_id: string) { const r = this.round; return r && r.target.id === item_id ? r.cue : null; }
  start() { if (this.started || !this.ready) return; this.started = true; this.show(); }
  private show() {
    const r = this.round;
    if (!r) { this.finished = true; return; }
    this.found.clear(); this.missed.clear(); this.wrongStreak = 0; this.solved = false; this.lastAt = this.ctx.now();
    this.ctx.event('item_shown', r.target.id, { cue: r.cue });
    if (r.cue) this.ctx.event('cue_shown', r.target.id, { cue: r.cue });
  }
  tap(cell_id: string): { correct: boolean; solved: boolean; ignored?: boolean } {
    const r = this.round;
    const cell = r?.cells.find((c) => c.cell_id === cell_id);
    if (!r || !cell || this.solved || this.found.has(cell_id) || this.missed.has(cell_id)) return { correct: false, solved: this.solved, ignored: true };
    const correct = r.targetCells.has(cell_id);
    this.ctx.event('answer', cell.item.id, { correct, response_ms: this.ctx.now() - this.lastAt, cue: r.cue });
    this.lastAt = this.ctx.now();
    if (correct) { this.found.add(cell_id); this.wrongStreak = 0; if (this.found.size === r.targetCells.size) this.solved = true; }
    else { this.missed.add(cell_id); this.wrongStreak++; }
    return { correct, solved: this.solved };
  }
  hint(): string | undefined {
    const r = this.round;
    if (!r) return undefined;
    const left = Array.from(r.targetCells).filter((c) => !this.found.has(c));
    if (!left.length) return undefined;
    this.hints++; this.wrongStreak = 0;
    this.ctx.event('hint_used', r.target.id, { cue: r.cue });
    return this.ctx.rng.pick(left);
  }
  next(): boolean { if (!this.solved) return false; this.index++; this.show(); return this.finished; }
}
