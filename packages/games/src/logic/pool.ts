import type { ContentItem } from '../types';
import type { Rng } from './rng';
export const isVisual = (i: ContentItem) => i.kind !== 'step' && !!(i.image || i.icon);
export const hasImage = (i: ContentItem) => i.kind !== 'step' && !!i.image;
export const objectPool = (c: readonly ContentItem[]) => c.filter(isVisual);
/** Caregiver photos first (they carry the personal memory signal), then the rest; each group shuffled. */
export function pickPreferCaregiver(pool: readonly ContentItem[], n: number, rng: Rng): ContentItem[] {
  const cg = rng.shuffle(pool.filter((i) => i.source === 'caregiver'));
  const rest = rng.shuffle(pool.filter((i) => i.source !== 'caregiver'));
  return [...cg, ...rest].slice(0, n);
}
export function groupBy<T>(xs: readonly T[], key: (x: T) => string): Record<string, T[]> {
  const o: Record<string, T[]> = {};
  for (const x of xs) (o[key(x)] ||= []).push(x);
  return o;
}
export function cycle<T>(xs: readonly T[], n: number): T[] { return Array.from({ length: n }, (_, i) => xs[i % xs.length]); }
