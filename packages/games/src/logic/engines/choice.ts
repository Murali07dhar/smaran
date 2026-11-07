import type { ContentItem, Cue, GameId } from '../../types';
import type { GameContext } from '../context';
import { assignCues } from '../cues';
import { paramsFor } from '../difficulty';
import { groupBy, objectPool } from '../pool';

export type ChoiceKind = 'odd' | 'name' | 'sort' | 'next';
export interface ChoiceOption { id: string; item?: ContentItem; category?: string }
export interface ChoiceRound { kind: ChoiceKind; item: ContentItem; options: ChoiceOption[]; correct_id: string; cue: Cue | null; prompt_key: string; context?: ContentItem }
export interface AnswerResult { correct: boolean; solved: boolean; eliminated?: string }
const GAME: Record<ChoiceKind, GameId> = { odd: 'odd_one_out', name: 'naming', sort: 'sorting', next: 'routine_next' };
const PROMPT: Record<ChoiceKind, string> = { odd: 'games.prompt.odd', name: 'games.prompt.name', sort: 'games.prompt.sort', next: 'games.prompt.next' };

function build(kind: ChoiceKind, pool: ContentItem[], difficulty: number, ctx: GameContext): ChoiceRound[] {
  const p = paramsFor(GAME[kind], difficulty);
  const { rng } = ctx;
  const byCat = groupBy(pool, (i) => i.category);
  const cats = Object.keys(byCat);
  const mk = (item: ContentItem, options: ChoiceOption[], correct_id: string): ChoiceRound => ({ kind, item, options, correct_id, cue: null, prompt_key: PROMPT[kind] });
  const rounds: ChoiceRound[] = [];
  if (kind === 'odd') {
    if (cats.length < 2) return [];
    const maxSame = Math.max(...cats.map((c) => byCat[c].length));
    const n = Math.max(3, Math.min(p.options, maxSame + 1));
    const used = new Set<string>();
    for (let r = 0; r < p.rounds; r++) {
      const ok = cats.filter((c) => byCat[c].length >= n - 1);
      if (!ok.length) break;
      const cat = rng.pick(ok);
      const others = pool.filter((i) => i.category !== cat);
      const fresh = others.filter((i) => !used.has(i.id));
      const odd = rng.pick(fresh.length ? fresh : others);
      used.add(odd.id);
      const opts = rng.shuffle([...rng.sample(byCat[cat], n - 1), odd]).map((item) => ({ id: item.id, item }));
      rounds.push(mk(odd, opts, odd.id));
    }
  } else if (kind === 'name') {
    const n = Math.min(p.options, pool.length);
    if (n < 2) return [];
    const targets: ContentItem[] = [];
    let bag = rng.shuffle(pool);
    for (let r = 0; r < p.rounds; r++) { if (!bag.length) bag = rng.shuffle(pool); targets.push(bag.pop()!); }
    for (const t of targets) {
      const same = rng.shuffle(pool.filter((i) => i.category === t.category && i.id !== t.id));
      const diff = rng.shuffle(pool.filter((i) => i.category !== t.category));
      const distract = (p.similar_distractors ? [...same, ...diff] : [...diff, ...same]).slice(0, n - 1);
      rounds.push(mk(t, rng.shuffle([t, ...distract]).map((item) => ({ id: item.id, item })), t.id));
    }
  } else if (kind === 'next') {
    const steps = pool.slice().sort((a, b) => (a.step_order ?? 0) - (b.step_order ?? 0));
    if (steps.length < 3) return [];
    const n = Math.min(p.options, steps.length - 1);
    const used = new Set<number>();
    for (let r = 0; r < p.rounds; r++) {
      const free = Array.from({ length: steps.length - 1 }, (_, k) => k + 1).filter((k) => !used.has(k));
      const i = rng.pick(free.length ? free : [1 + rng.int(steps.length - 1)]);
      used.add(i);
      const correct = steps[i], prev = steps[i - 1];
      const distract = rng.sample(steps.filter((s) => s.id !== correct.id && s.id !== prev.id), n - 1);
      rounds.push({ ...mk(correct, rng.shuffle([correct, ...distract]).map((item) => ({ id: item.id, item })), correct.id), context: prev });
    }
  } else {
    const k = Math.min(p.categories, cats.length);
    if (k < 2) return [];
    const chosen = rng.sample(cats, k);
    const bags = chosen.map((c) => rng.shuffle(byCat[c]));
    const items: ContentItem[] = [];
    for (let i = 0; i < p.items; i++) {
      const b = bags[i % k];
      if (!b.length) b.push(...rng.shuffle(byCat[chosen[i % k]]));
      items.push(b.pop()!);
    }
    const options = chosen.map((c) => ({ id: c, category: c }));
    for (const item of rng.shuffle(items)) rounds.push(mk(item, options, item.category));
  }
  const cueMap = assignCues(rounds.map((r, i) => ({ key: `r${i}`, item_id: r.item.id })), ctxCues.get(ctx) ?? [], rng);
  rounds.forEach((r, i) => { r.cue = cueMap.get(`r${i}`) ?? null; });
  return rounds;
}
const ctxCues = new WeakMap<GameContext, readonly Cue[]>();

/** Odd-one-out, naming and category sorting. A wrong answer dims that option plus one more distractor (hint). */
export class ChoiceEngine {
  readonly rounds: ChoiceRound[];
  index = 0; solved = false; finished = false; hints = 0;
  wrong = new Set<string>();
  private started = false;
  private shownAt = 0;
  readonly showLabels: boolean;
  constructor(readonly kind: ChoiceKind, content: readonly ContentItem[], readonly difficulty: number, private ctx: GameContext, cues: readonly Cue[] = []) {
    ctxCues.set(ctx, cues);
    this.rounds = build(kind, kind === 'next' ? content.filter((i) => i.kind === 'step' && i.routine_id === 'morning') : objectPool(content).filter((i) => i.kind === 'object'), difficulty, ctx);
    this.showLabels = kind !== 'odd' || paramsFor('odd_one_out', difficulty).show_labels === 1;
  }
  get ready() { return this.rounds.length > 0; }
  get total() { return this.rounds.length; }
  get round(): ChoiceRound | undefined { return this.rounds[this.index]; }
  cueFor(item_id: string) { const r = this.round; return r && r.item.id === item_id ? r.cue : null; }
  start() { if (this.started || !this.ready) return; this.started = true; this.show(); }
  private show() {
    const r = this.round;
    if (!r) { this.finished = true; return; }
    this.solved = false; this.wrong.clear(); this.shownAt = this.ctx.now();
    this.ctx.event('item_shown', r.item.id, { cue: r.cue });
    if (r.cue) this.ctx.event('cue_shown', r.item.id, { cue: r.cue });
  }
  answer(option_id: string): AnswerResult {
    const r = this.round;
    if (!r || this.solved || this.wrong.has(option_id)) return { correct: false, solved: this.solved };
    const correct = option_id === r.correct_id;
    this.ctx.event('answer', r.item.id, { correct, response_ms: this.ctx.now() - this.shownAt, cue: r.cue });
    if (correct) { this.solved = true; return { correct: true, solved: true }; }
    this.wrong.add(option_id);
    return { correct: false, solved: false, eliminated: this.hint() };
  }
  /** Dims one remaining wrong option. Emits hint_used. */
  hint(): string | undefined {
    const r = this.round;
    if (!r) return undefined;
    const left = r.options.filter((o) => o.id !== r.correct_id && !this.wrong.has(o.id));
    if (!left.length) return undefined;
    const pick = this.ctx.rng.pick(left);
    this.wrong.add(pick.id); this.hints++;
    this.ctx.event('hint_used', r.item.id, { cue: r.cue });
    return pick.id;
  }
  externalHint(item_id: string) { const id = this.round?.item.id ?? item_id; this.hints++; this.ctx.event('hint_used', id, { cue: this.cueFor(id) }); }
  /** Advance after a solved round. Returns true when the game is finished. */
  next(): boolean {
    if (!this.solved) return false;
    this.index++;
    this.show();
    return this.finished;
  }
}
