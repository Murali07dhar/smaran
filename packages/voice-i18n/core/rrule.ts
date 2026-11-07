// Minimal, dependency-free RRULE implementation with IANA timezone + DST handling.
// Supports FREQ=DAILY|WEEKLY|MONTHLY, INTERVAL, BYDAY (no ordinals), BYMONTHDAY, BYHOUR, BYMINUTE, COUNT, UNTIL.
// Uses Intl.DateTimeFormat for zone math (Node, browsers, Hermes with Intl). No react/DOM imports.

export const DEFAULT_TZ = 'Asia/Kolkata';

const dtfCache = new Map<string, Intl.DateTimeFormat>();
function dtf(tz: string): Intl.DateTimeFormat {
  let f = dtfCache.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat('en-US', {
      timeZone: tz, hourCycle: 'h23', year: 'numeric', month: 'numeric', day: 'numeric',
      hour: 'numeric', minute: 'numeric', second: 'numeric',
    });
    dtfCache.set(tz, f);
  }
  return f;
}

export interface Civil { y: number; m: number; d: number; h: number; mi: number; s: number }

/** Wall-clock fields of a UTC instant in a zone. */
export function utcToCivil(ms: number, tz: string): Civil {
  const parts = dtf(tz).formatToParts(new Date(ms));
  const o: Record<string, number> = {};
  for (const p of parts) if (p.type !== 'literal') o[p.type] = parseInt(p.value, 10);
  return { y: o.year, m: o.month, d: o.day, h: o.hour % 24, mi: o.minute, s: o.second };
}

function civilAsUtcMs(c: Civil): number {
  return Date.UTC(c.y, c.m - 1, c.d, c.h, c.mi, c.s);
}

/** Offset (ms) of zone at a UTC instant: local - utc. */
export function tzOffsetMs(ms: number, tz: string): number {
  const flooredMs = Math.floor(ms / 1000) * 1000;
  return civilAsUtcMs(utcToCivil(flooredMs, tz)) - flooredMs;
}

/**
 * Convert wall-clock time in tz to a UTC instant.
 * Gap (spring forward, time does not exist): shifted forward by the gap length.
 * Overlap (fall back, time occurs twice): first occurrence is used.
 */
export function civilToUtc(c: Civil, tz: string): number {
  const guess = civilAsUtcMs(c);
  const t1 = guess - tzOffsetMs(guess, tz);
  const t2 = guess - tzOffsetMs(t1, tz);
  if (t1 === t2) return t1;
  const matches = (t: number) => civilAsUtcMs(utcToCivil(t, tz)) === guess;
  const m1 = matches(t1), m2 = matches(t2);
  if (m1 && m2) return Math.min(t1, t2);
  if (m1) return t1;
  if (m2) return t2;
  return Math.max(t1, t2); // gap
}

export type Freq = 'DAILY' | 'WEEKLY' | 'MONTHLY';
const DAY_CODES = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'];

export interface ParsedRule {
  freq: Freq;
  interval: number;
  byday?: number[]; // 0=Sun
  bymonthday?: number[];
  byhour?: number[];
  byminute?: number[];
  count?: number;
  untilMs?: number;
  tz: string;
  dtstart: Civil; // wall-clock start in tz
}

function parseCivil(s: string): Civil {
  const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z?$/.exec(s.trim());
  if (!m) throw new Error(`Bad date-time: ${s}`);
  return { y: +m[1], m: +m[2], d: +m[3], h: +m[4], mi: +m[5], s: +m[6] };
}

export interface ParseOpts { defaultTz?: string; anchorMs?: number }

/**
 * schedule may be:
 *   "DTSTART;TZID=Asia/Kolkata:20260101T080000\nRRULE:FREQ=DAILY;BYHOUR=8,20"
 *   "FREQ=DAILY;BYHOUR=8"   (dtstart taken from opts.anchorMs in default tz, midnight of that day)
 */
export function parseSchedule(schedule: string, opts: ParseOpts = {}): ParsedRule {
  let tz = opts.defaultTz ?? DEFAULT_TZ;
  let dtstart: Civil | undefined;
  let ruleStr = '';
  for (const raw of schedule.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith('DTSTART')) {
      const m = /^DTSTART(?:;TZID=([^:]+))?:(.+)$/.exec(line);
      if (!m) throw new Error(`Bad DTSTART: ${line}`);
      if (m[1]) tz = m[1];
      dtstart = parseCivil(m[2]);
      if (m[2].endsWith('Z') && !m[1]) tz = 'UTC';
    } else if (line.startsWith('RRULE:')) ruleStr = line.slice(6);
    else if (line.startsWith('FREQ=')) ruleStr = line;
  }
  if (!ruleStr) throw new Error('No RRULE found');
  try { dtf(tz); } catch { throw new Error(`Unknown timezone: ${tz}`); }
  if (!dtstart) {
    const c = utcToCivil(opts.anchorMs ?? 0, tz);
    dtstart = { ...c, h: 0, mi: 0, s: 0 };
  }
  const kv: Record<string, string> = {};
  for (const part of ruleStr.split(';')) {
    const [k, v] = part.split('=');
    if (k && v !== undefined) kv[k.toUpperCase()] = v;
  }
  const freq = kv.FREQ as Freq;
  if (!['DAILY', 'WEEKLY', 'MONTHLY'].includes(freq)) throw new Error(`Unsupported FREQ: ${kv.FREQ}`);
  const nums = (s?: string) => (s ? s.split(',').map((x) => parseInt(x, 10)) : undefined);
  const rule: ParsedRule = {
    freq, tz, dtstart,
    interval: Math.max(1, parseInt(kv.INTERVAL ?? '1', 10)),
    byhour: nums(kv.BYHOUR), byminute: nums(kv.BYMINUTE), bymonthday: nums(kv.BYMONTHDAY),
    count: kv.COUNT ? parseInt(kv.COUNT, 10) : undefined,
  };
  if (kv.BYDAY) {
    rule.byday = kv.BYDAY.split(',').map((c) => {
      const i = DAY_CODES.indexOf(c.trim().toUpperCase());
      if (i < 0) throw new Error(`Unsupported BYDAY: ${c}`);
      return i;
    });
  }
  if (kv.UNTIL) {
    const u = kv.UNTIL.includes('T') ? kv.UNTIL : kv.UNTIL + 'T235959';
    rule.untilMs = u.endsWith('Z') ? civilToUtc(parseCivil(u), 'UTC') : civilToUtc(parseCivil(u), tz);
  }
  for (const h of rule.byhour ?? []) if (!(h >= 0 && h <= 23)) throw new Error('BYHOUR out of range');
  for (const m of rule.byminute ?? []) if (!(m >= 0 && m <= 59)) throw new Error('BYMINUTE out of range');
  return rule;
}

const addDays = (y: number, m: number, d: number, n: number) => {
  const dt = new Date(Date.UTC(y, m - 1, d + n));
  return { y: dt.getUTCFullYear(), m: dt.getUTCMonth() + 1, d: dt.getUTCDate() };
};
const dow = (y: number, m: number, d: number) => new Date(Date.UTC(y, m - 1, d)).getUTCDay();
const daysInMonth = (y: number, m: number) => new Date(Date.UTC(y, m, 0)).getUTCDate();

const MAX_PERIODS = 60000;

/** All occurrences (UTC ms) with fromMs <= t < toMs, in order. COUNT is honoured from DTSTART. */
export function occurrencesBetween(rule: ParsedRule, fromMs: number, toMs: number): number[] {
  const out: number[] = [];
  const hours = rule.byhour ?? [rule.dtstart.h];
  const minutes = rule.byminute ?? [rule.dtstart.mi];
  const times: Array<[number, number]> = [];
  for (const h of [...hours].sort((a, b) => a - b)) for (const mi of [...minutes].sort((a, b) => a - b)) times.push([h, mi]);

  const startUtc = civilToUtc(rule.dtstart, rule.tz);
  let emitted = 0;
  const { y: sy, m: sm, d: sd } = rule.dtstart;

  const emitDay = (y: number, m: number, d: number): boolean => {
    for (const [h, mi] of times) {
      const t = civilToUtc({ y, m, d, h, mi, s: 0 }, rule.tz);
      if (t < startUtc) continue;
      if (rule.untilMs !== undefined && t > rule.untilMs) return false;
      emitted++;
      if (rule.count !== undefined && emitted > rule.count) return false;
      if (t >= toMs) return false;
      if (t >= fromMs) out.push(t);
    }
    return true;
  };

  for (let i = 0; i < MAX_PERIODS; i++) {
    if (rule.freq === 'DAILY') {
      const { y, m, d } = addDays(sy, sm, sd, i * rule.interval);
      if (rule.byday && !rule.byday.includes(dow(y, m, d))) continue;
      if (!emitDay(y, m, d)) break;
    } else if (rule.freq === 'WEEKLY') {
      const startDow = dow(sy, sm, sd);
      const mondayOffset = (startDow + 6) % 7; // week starts Monday
      const base = addDays(sy, sm, sd, -mondayOffset + i * 7 * rule.interval);
      const days = (rule.byday ?? [startDow]).map((x) => (x + 6) % 7).sort((a, b) => a - b);
      let stop = false;
      for (const off of days) {
        const { y, m, d } = addDays(base.y, base.m, base.d, off);
        if (!emitDay(y, m, d)) { stop = true; break; }
      }
      if (stop) break;
    } else {
      const total = sy * 12 + (sm - 1) + i * rule.interval;
      const y = Math.floor(total / 12), m = (total % 12) + 1;
      const mdays = (rule.bymonthday ?? [sd]).slice().sort((a, b) => a - b);
      let stop = false;
      for (const md of mdays) {
        if (md < 1 || md > daysInMonth(y, m)) continue; // RFC 5545: invalid dates skipped
        if (!emitDay(y, m, md)) { stop = true; break; }
      }
      if (stop) break;
    }
  }
  return out;
}

export function nextOccurrence(rule: ParsedRule, afterMs: number, horizonDays = 800): number | undefined {
  return occurrencesBetween(rule, afterMs + 1, afterMs + horizonDays * 86400000)[0];
}
