export interface Rng {
  next(): number; int(n: number): number; chance(p: number): boolean;
  pick<T>(a: readonly T[]): T; shuffle<T>(a: readonly T[]): T[]; sample<T>(a: readonly T[], k: number): T[];
}
export function hashSeed(s: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; }
  return h >>> 0;
}
export function createRng(seed: number | string = Date.now()): Rng {
  let a = (typeof seed === 'string' ? hashSeed(seed) : seed) >>> 0;
  const next = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const int = (n: number) => Math.floor(next() * n);
  const shuffle = <T>(arr: readonly T[]): T[] => {
    const o = arr.slice();
    for (let i = o.length - 1; i > 0; i--) { const j = int(i + 1); [o[i], o[j]] = [o[j], o[i]]; }
    return o;
  };
  return {
    next, int, chance: (p) => next() < p,
    pick: (arr) => arr[int(arr.length)],
    shuffle,
    sample: (arr, k) => shuffle(arr).slice(0, k),
  };
}
