import type { CueArm, GameEvent, GameId, SessionSummary } from '../types';

export function summarize(events: readonly GameEvent[], meta: { session_id: string; game_id: GameId; difficulty: number; started_at: string; completed_at: string }): SessionSummary {
  const answers = events.filter((e) => e.type === 'answer');
  const first = new Map<string, boolean>();
  for (const a of answers) if (!first.has(a.item_id)) first.set(a.item_id, !!a.correct);
  const arm = (w: boolean): CueArm => {
    const xs = answers.filter((a) => a.with_cue === w);
    return { answers: xs.length, correct: xs.filter((a) => a.correct).length };
  };
  const rts = answers.map((a) => a.response_ms).filter((x): x is number => typeof x === 'number');
  return {
    ...meta,
    items_total: new Set(events.filter((e) => e.type === 'item_shown').map((e) => e.item_id)).size,
    answers: answers.length,
    correct_answers: answers.filter((a) => a.correct).length,
    first_try_correct: Array.from(first.values()).filter(Boolean).length,
    hints_used: events.filter((e) => e.type === 'hint_used').length,
    with_cue: arm(true),
    without_cue: arm(false),
    mean_response_ms: rts.length ? Math.round(rts.reduce((s, x) => s + x, 0) / rts.length) : null,
    disclaimer_key: 'games.disclaimer',
  };
}
