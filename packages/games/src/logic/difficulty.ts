import type { GameId } from '../types';
export type DifficultyParams = Record<string, number>;
export const GAME_IDS: readonly GameId[] = ['memory_pairs', 'image_grid', 'target_tap', 'spot_diff', 'routine_order', 'odd_one_out', 'naming', 'sorting', 'arrange_steps', 'routine_next'];
const lerp = (a: number, b: number, d: number) => Math.round(a + ((b - a) * (d - 1)) / 9);
const levels = (fn: (d: number) => DifficultyParams) => { const o: Record<number, DifficultyParams> = {}; for (let d = 1; d <= 10; d++) o[d] = fn(d); return o; };
/** Difficulty map 1-10 per game. Engines clamp to what the available content can support. */
export const difficultyMap: Record<GameId, Record<number, DifficultyParams>> = {
  memory_pairs: levels((d) => ({ pairs: lerp(2, 8, d), show_labels: d <= 6 ? 1 : 0, hint_after_misses: d <= 3 ? 1 : 2 })),
  image_grid: levels((d) => ({ grid: d <= 3 ? 2 : d <= 7 ? 3 : 4, puzzles: 2, preview: d <= 6 ? 1 : 0 })),
  target_tap: levels((d) => ({ cells: lerp(4, 16, d), targets: lerp(1, 5, d), rounds: 4, similar_distractors: d >= 6 ? 1 : 0 })),
  spot_diff: levels((d) => ({ cols: 3, rows: lerp(2, 4, d), diffs: lerp(1, 5, d), rounds: 2 })),
  routine_order: levels((d) => ({ steps: lerp(3, 7, d) })),
  odd_one_out: levels((d) => ({ options: lerp(3, 6, d), rounds: 6, show_labels: d <= 7 ? 1 : 0 })),
  naming: levels((d) => ({ options: lerp(2, 5, d), rounds: 6, similar_distractors: d >= 6 ? 1 : 0 })),
  sorting: levels((d) => ({ categories: lerp(2, 4, d), items: lerp(4, 12, d) })),
  arrange_steps: levels((d) => ({ steps: lerp(3, 6, d) })),
  routine_next: levels((d) => ({ options: lerp(2, 4, d), rounds: 5 })),
};
export const clampDifficulty = (d: number) => Math.min(10, Math.max(1, Math.round(d)));
export function paramsFor(id: GameId, difficulty: number): DifficultyParams { return difficultyMap[id][clampDifficulty(difficulty)]; }
