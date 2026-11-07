import type { ContentItem, Cue } from '../../types';
import type { GameContext } from '../context';
import { assignCues } from '../cues';
import { paramsFor } from '../difficulty';
import { objectPool } from '../pool';

export interface SpotRound { cols: number; a: ContentItem[]; b: ContentItem[]; diff: Set<number>; cue: Cue | null }
/** Spot-the-difference (attention): two identical-looking boards, some cells differ. */
export class SpotEngine {
  readonly rounds: SpotRound[] = [];
  index = 0; found = new Set<number>(); missed = new Set<number>(); wrongStreak = 0; hints = 0; solved = false; finished = false;
  private lastAt = 0; private started = false;
  constructor(content: readonly ContentItem[], difficulty: number, private ctx: GameContext, cues: readonly Cue[] = []) {
    const p = paramsFor('spot_diff', difficulty);
    const pool = objectPool(content);
    if (pool.length < 3) return;
    const { rng } = ctx;
    const cells = p.cols * p.rows, dN = Math.min(p.diffs, cells - 1);
    for (let r = 0; r < p.rounds; r++) {
      const base = rng.shuffle(pool);
      const a = Array.from({ length: cells }, (_, i) => base[i % base.length]);
      const b = a.slice();
      const diff = new Set(rng.sample(Array.from({ length: cells }, (_, i) => i), dN));
      diff.forEach((i) => { b[i] = rng.pick(pool.filter((x) => x.id !== a[i].id)); });
      this.rounds.push({ cols: p.cols, a, b, diff, cue: null });
    }
    const m = assignCues(this.rounds.map((r, i) => ({ key: `r${i}`, item_id: r.b[Array.from(r.diff)[0]].id })), cues, rng);
    this.rounds.forEach((r, i) => { r.cue = m.get(`r${i}`) ?? null; });
  }
  get ready() { return this.rounds.length > 0; }
  get total() { return this.rounds.length; }
  get round(): SpotRound | undefined { return this.rounds[this.index]; }
  get hintSuggested() { return this.wrongStreak >= 2; }
  private anchor(r: SpotRound) { return r.b[Array.from(r.diff)[0]].id; }
  cueFor(item_id: string) { const r = this.round; return r && this.anchor(r) === item_id ? r.cue : null; }
  start() { if (this.started || !this.ready) return; this.started = true; this.show(); }
  private show() {
    const r = this.round;
    if (!r) { this.finished = true; return; }
    this.found.clear(); this.missed.clear(); this.wrongStreak = 0; this.solved = false; this.lastAt = this.ctx.now();
    this.ctx.event('item_shown', this.anchor(r), { cue: r.cue });
    if (r.cue) this.ctx.event('cue_shown', this.anchor(r), { cue: r.cue });
  }
  tap(index: number): { correct: boolean; solved: boolean; ignored?: boolean } {
    const r = this.round;
    if (!r || this.solved || index < 0 || index >= r.b.length || this.found.has(index) || this.missed.has(index)) return { correct: false, solved: this.solved, ignored: true };
    const correct = r.diff.has(index);
    this.ctx.event('answer', r.b[index].id, { correct, response_ms: this.ctx.now() - this.lastAt, cue: r.cue });
    this.lastAt = this.ctx.now();
    if (correct) { this.found.add(index); this.wrongStreak = 0; if (this.found.size === r.diff.size) this.solved = true; }
    else { this.missed.add(index); this.wrongStreak++; }
    return { correct, solved: this.solved };
  }
  hint(): number | undefined {
    const r = this.round;
    if (!r) return undefined;
    const left = Array.from(r.diff).filter((i) => !this.found.has(i));
    if (!left.length) return undefined;
    this.hints++; this.wrongStreak = 0;
    this.ctx.event('hint_used', this.anchor(r), { cue: r.cue });
    return this.ctx.rng.pick(left);
  }
  next(): boolean { if (!this.solved) return false; this.index++; this.show(); return this.finished; }
}
