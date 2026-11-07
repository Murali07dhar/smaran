import type { ContentItem, Cue, GameId } from '../../types';
import type { GameContext } from '../context';
import { assignCues } from '../cues';
import { paramsFor } from '../difficulty';

/**
 * Step ordering (routine recall and "make tea"). Patient taps steps in order; the slot being asked for is the
 * item for every event of that slot, so with_cue/cue_id stay consistent per slot. Cue is attached per step.
 */
export class OrderEngine {
  readonly order: ContentItem[]; // correct order (subset)
  readonly presented: ContentItem[]; // shuffled
  placed: string[] = []; wrongTaps = new Set<string>(); slotWrong = 0; hints = 0; finished = false;
  private cues: Map<string, Cue | null>;
  private lastAt = 0; private started = false;
  constructor(content: readonly ContentItem[], readonly routine_id: string, readonly gameId: Extract<GameId, 'routine_order' | 'arrange_steps'>, difficulty: number, private ctx: GameContext, cues: readonly Cue[] = []) {
    const steps = content.filter((i) => i.kind === 'step' && i.routine_id === routine_id).sort((a, b) => (a.step_order ?? 0) - (b.step_order ?? 0));
    const n = Math.min(paramsFor(gameId, difficulty).steps, steps.length);
    const idx = n <= 1 ? [0] : Array.from(new Set(Array.from({ length: n }, (_, i) => Math.round((i * (steps.length - 1)) / (n - 1)))));
    this.order = steps.length ? idx.map((i) => steps[i]) : [];
    let sh = ctx.rng.shuffle(this.order);
    if (this.order.length > 1 && sh.every((s, i) => s.id === this.order[i].id)) sh = [...sh.slice(1), sh[0]];
    this.presented = sh;
    this.cues = assignCues(this.order.map((s) => ({ key: s.id, item_id: s.id })), cues, ctx.rng);
  }
  get ready() { return this.order.length >= 2; }
  get total() { return this.order.length; }
  get next(): ContentItem | undefined { return this.order[this.placed.length]; }
  get hintSuggested() { return this.slotWrong >= 2; }
  cueFor(item_id: string) { return this.cues.get(item_id) ?? null; }
  isPlaced(id: string) { return this.placed.includes(id); }
  start() { if (this.started || !this.ready) return; this.started = true; this.show(); }
  private show() {
    const n = this.next;
    if (!n) { this.finished = true; return; }
    this.wrongTaps.clear(); this.slotWrong = 0; this.lastAt = this.ctx.now();
    const cue = this.cueFor(n.id);
    this.ctx.event('item_shown', n.id, { cue });
    if (cue) this.ctx.event('cue_shown', n.id, { cue });
  }
  tap(step_id: string): { correct: boolean; complete: boolean; ignored?: boolean } {
    const target = this.next;
    if (!target || this.finished || this.isPlaced(step_id) || this.wrongTaps.has(step_id)) return { correct: false, complete: this.finished, ignored: true };
    const correct = step_id === target.id;
    this.ctx.event('answer', target.id, { correct, response_ms: this.ctx.now() - this.lastAt, cue: this.cueFor(target.id) });
    if (!correct) { this.wrongTaps.add(step_id); this.slotWrong++; return { correct: false, complete: false }; }
    this.placed.push(step_id);
    this.show();
    return { correct: true, complete: this.finished };
  }
  hint(): string | undefined {
    const t = this.next;
    if (!t) return undefined;
    this.hints++; this.slotWrong = 0;
    this.ctx.event('hint_used', t.id, { cue: this.cueFor(t.id) });
    return t.id;
  }
  externalHint(item_id: string) { this.hints++; this.ctx.event('hint_used', item_id, { cue: this.cueFor(item_id) }); }
}
