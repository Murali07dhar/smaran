import type { ContentItem, Cue } from '../../types';
import type { GameContext } from '../context';
import { assignCues } from '../cues';
import { paramsFor } from '../difficulty';
import { hasImage, pickPreferCaregiver } from '../pool';

export type SelectKind = 'selected' | 'deselected' | 'swap' | 'ignored';
/** Image-grid puzzle from (caregiver) photos: tap a piece, tap another, they swap. tiles[pos] === pos when correct. */
export class GridEngine {
  readonly puzzles: { item: ContentItem; cue: Cue | null }[];
  readonly n: number;
  readonly preview: boolean;
  index = 0; tiles: number[] = []; selected: number | null = null;
  poorMoves = 0; hints = 0; solved = false; finished = false;
  private lastAt = 0; private started = false;
  constructor(content: readonly ContentItem[], difficulty: number, private ctx: GameContext, cues: readonly Cue[] = []) {
    const p = paramsFor('image_grid', difficulty);
    this.n = p.grid; this.preview = p.preview === 1;
    const items = pickPreferCaregiver(content.filter(hasImage), p.puzzles, ctx.rng);
    const m = assignCues(items.map((i, k) => ({ key: `p${k}`, item_id: i.id })), cues, ctx.rng);
    this.puzzles = items.map((item, k) => ({ item, cue: m.get(`p${k}`) ?? null }));
  }
  get ready() { return this.puzzles.length > 0; }
  get total() { return this.puzzles.length; }
  get puzzle() { return this.puzzles[this.index]; }
  cueFor(item_id: string) { const p = this.puzzle; return p && p.item.id === item_id ? p.cue : null; }
  isCorrect(pos: number) { return this.tiles[pos] === pos; }
  get correctCount() { return this.tiles.filter((t, i) => t === i).length; }
  get hintSuggested() { return this.poorMoves >= 3; }
  start() { if (this.started || !this.ready) return; this.started = true; this.show(); }
  private show() {
    const p = this.puzzle;
    if (!p) { this.finished = true; return; }
    const size = this.n * this.n;
    let t = Array.from({ length: size }, (_, i) => i);
    do {
      t = Array.from({ length: size }, (_, i) => i);
      for (let k = 0; k < Math.max(4, size); k++) { const a = this.ctx.rng.int(size), b = this.ctx.rng.int(size); [t[a], t[b]] = [t[b], t[a]]; }
    } while (t.every((v, i) => v === i));
    this.tiles = t; this.selected = null; this.solved = false; this.poorMoves = 0; this.lastAt = this.ctx.now();
    this.ctx.event('item_shown', p.item.id, { cue: p.cue });
    if (p.cue) this.ctx.event('cue_shown', p.item.id, { cue: p.cue });
  }
  select(pos: number): { kind: SelectKind; improved?: boolean; solved: boolean } {
    if (this.solved || pos < 0 || pos >= this.tiles.length) return { kind: 'ignored', solved: this.solved };
    if (this.selected === null) { this.selected = pos; return { kind: 'selected', solved: false }; }
    if (this.selected === pos) { this.selected = null; return { kind: 'deselected', solved: false }; }
    const before = this.correctCount, s = this.selected;
    [this.tiles[s], this.tiles[pos]] = [this.tiles[pos], this.tiles[s]];
    this.selected = null;
    const improved = this.correctCount > before;
    const p = this.puzzle;
    this.ctx.event('answer', p.item.id, { correct: improved, response_ms: this.ctx.now() - this.lastAt, cue: p.cue });
    this.lastAt = this.ctx.now();
    this.poorMoves = improved ? 0 : this.poorMoves + 1;
    if (this.correctCount === this.tiles.length) this.solved = true;
    return { kind: 'swap', improved, solved: this.solved };
  }
  /** [target position, current position of the tile that belongs there]. Emits hint_used. */
  hint(): number[] {
    const wrong = this.tiles.map((t, i) => (t === i ? -1 : i)).filter((i) => i >= 0);
    if (!wrong.length) return [];
    const p = this.ctx.rng.pick(wrong);
    this.hints++; this.poorMoves = 0;
    this.ctx.event('hint_used', this.puzzle.item.id, { cue: this.puzzle.cue });
    return [p, this.tiles.indexOf(p)];
  }
  externalHint(item_id: string) { this.hints++; this.ctx.event('hint_used', item_id, { cue: this.cueFor(item_id) }); }
  next(): boolean { if (!this.solved) return false; this.index++; this.show(); return this.finished; }
}
