import type { ContentItem, Cue } from '../../types';
import type { GameContext } from '../context';
import { assignCues } from '../cues';
import { paramsFor } from '../difficulty';
import { objectPool, pickPreferCaregiver } from '../pool';

export interface PairCard { card_id: string; item: ContentItem }
export type FlipKind = 'ignored' | 'up' | 'match' | 'mismatch';
export interface FlipResult { kind: FlipKind; complete: boolean }

/** Photo pair-matching (memory). Mismatched cards stay face-up until the next tap: no timers. */
export class PairsEngine {
  readonly cards: PairCard[];
  readonly total: number;
  faceUp: string[] = [];
  matched = new Set<string>();
  misses = 0; streak = 0; hints = 0; finished = false;
  private cues: Map<string, Cue | null>;
  private attemptStart = 0;
  private hintAfter: number;
  readonly showLabels: boolean;

  constructor(content: readonly ContentItem[], difficulty: number, private ctx: GameContext, cues: readonly Cue[] = []) {
    const p = paramsFor('memory_pairs', difficulty);
    const items = pickPreferCaregiver(objectPool(content), p.pairs, ctx.rng);
    this.total = items.length;
    this.hintAfter = p.hint_after_misses;
    this.showLabels = p.show_labels === 1;
    this.cues = assignCues(items.map((i) => ({ key: i.id, item_id: i.id })), cues, ctx.rng);
    this.cards = ctx.rng.shuffle(items.flatMap((item) => [{ card_id: `${item.id}#a`, item }, { card_id: `${item.id}#b`, item }]));
  }
  get ready() { return this.total >= 2; }
  cueFor(item_id: string) { return this.cues.get(item_id) ?? null; }
  isUp(card_id: string) { return this.faceUp.includes(card_id); }
  isMatched(item_id: string) { return this.matched.has(item_id); }
  get hintSuggested() { return this.streak >= this.hintAfter; }
  private find(id: string) { return this.cards.find((c) => c.card_id === id); }

  flip(card_id: string): FlipResult {
    const card = this.find(card_id);
    if (!card || this.finished || this.matched.has(card.item.id)) return { kind: 'ignored', complete: false };
    if (this.faceUp.length >= 2) this.faceUp = []; // turn the mismatched pair back, then treat this tap as a fresh flip
    if (this.faceUp.includes(card_id)) return { kind: 'ignored', complete: false };
    if (this.faceUp.length === 0) this.attemptStart = this.ctx.now();
    this.faceUp.push(card_id);
    const cue = this.cueFor(card.item.id);
    this.ctx.event('item_shown', card.item.id, { cue });
    if (cue) this.ctx.event('cue_shown', card.item.id, { cue });
    if (this.faceUp.length < 2) return { kind: 'up', complete: false };
    const a = this.find(this.faceUp[0])!;
    const ok = a.item.id === card.item.id;
    this.ctx.event('answer', card.item.id, { correct: ok, response_ms: this.ctx.now() - this.attemptStart, cue });
    if (ok) {
      this.matched.add(card.item.id); this.faceUp = []; this.streak = 0;
      this.finished = this.matched.size === this.total;
      return { kind: 'match', complete: this.finished };
    }
    this.misses++; this.streak++;
    return { kind: 'mismatch', complete: false };
  }

  /** Card ids to highlight. Emits hint_used. */
  hint(): string[] {
    let base: PairCard | undefined = this.faceUp.length ? this.find(this.faceUp[0]) : undefined;
    let ids: string[];
    if (base) ids = this.cards.filter((c) => c.item.id === base!.item.id && c.card_id !== base!.card_id).map((c) => c.card_id);
    else {
      const rest = this.cards.filter((c) => !this.matched.has(c.item.id));
      if (!rest.length) return [];
      base = this.ctx.rng.pick(rest);
      ids = this.cards.filter((c) => c.item.id === base!.item.id).map((c) => c.card_id);
    }
    this.hints++; this.streak = 0;
    this.ctx.event('hint_used', base.item.id, { cue: this.cueFor(base.item.id) });
    return ids;
  }
  /** Family hint received over co-op for a given item. */
  externalHint(item_id: string) { this.hints++; this.ctx.event('hint_used', item_id, { cue: this.cueFor(item_id) }); }
}
