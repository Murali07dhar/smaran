export interface BackoffOptions {
  baseMs?: number; // default 2000
  maxMs?: number; // default 5 * 60_000
  factor?: number; // default 2
}

/** Pure exponential backoff with full jitter. attempts starts at 1. */
export function computeBackoffMs(attempts: number, opts: BackoffOptions = {}): number {
  const base = opts.baseMs ?? 2000;
  const max = opts.maxMs ?? 5 * 60_000;
  const factor = opts.factor ?? 2;
  const raw = Math.min(max, base * Math.pow(factor, Math.max(0, attempts - 1)));
  return Math.floor(Math.random() * raw);
}

export function nextAttemptIso(attempts: number, now: () => Date = () => new Date(), opts?: BackoffOptions): string {
  const ms = computeBackoffMs(attempts, opts);
  return new Date(now().getTime() + ms).toISOString();
}
