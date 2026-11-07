import { describe, expect, it } from 'vitest';
import { civilToUtc, occurrencesBetween, parseSchedule, utcToCivil } from '../core/rrule';
import { ReminderEngine } from '../core/reminderEngine';
import type { Reminder } from '../core/types';

const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

const rem = (over: Partial<Reminder> = {}): Reminder => ({
  id: 'r1', patient_id: 'p1', category: 'medicine', title: 'Metformin', locale: 'en',
  schedule: 'DTSTART;TZID=Asia/Kolkata:20260101T080000\nRRULE:FREQ=DAILY',
  escalate_after_misses: 2, ...over,
});

const ist = (y: number, m: number, d: number, h = 0, mi = 0) => civilToUtc({ y, m, d, h, mi, s: 0 }, 'Asia/Kolkata');

describe('rrule + timezones', () => {
  it('daily 08:00 IST is 02:30 UTC', () => {
    const rule = parseSchedule(rem().schedule);
    const [t] = occurrencesBetween(rule, ist(2026, 3, 1), ist(2026, 3, 2));
    expect(new Date(t).toISOString()).toBe('2026-03-01T02:30:00.000Z');
  });

  it('India has no DST: 08:00 stays 08:00 all year', () => {
    const rule = parseSchedule(rem().schedule);
    for (const m of [1, 4, 7, 10]) {
      const [t] = occurrencesBetween(rule, ist(2026, m, 15), ist(2026, m, 16));
      expect(utcToCivil(t, 'Asia/Kolkata').h).toBe(8);
    }
  });

  it('BYHOUR gives multiple times per day, sorted', () => {
    const rule = parseSchedule('DTSTART;TZID=Asia/Kolkata:20260101T000000\nRRULE:FREQ=DAILY;BYHOUR=20,8;BYMINUTE=30');
    const occ = occurrencesBetween(rule, ist(2026, 2, 1), ist(2026, 2, 2));
    expect(occ.map((t) => utcToCivil(t, 'Asia/Kolkata').h)).toEqual([8, 20]);
  });

  it('weekly BYDAY MO,TH', () => {
    const rule = parseSchedule('DTSTART;TZID=Asia/Kolkata:20260105T090000\nRRULE:FREQ=WEEKLY;BYDAY=MO,TH');
    const occ = occurrencesBetween(rule, ist(2026, 1, 5), ist(2026, 1, 12));
    expect(occ).toHaveLength(2); // Mon 5th, Thu 8th
  });

  it('COUNT is honoured from DTSTART, not from the query window', () => {
    const rule = parseSchedule('DTSTART;TZID=Asia/Kolkata:20260101T080000\nRRULE:FREQ=DAILY;COUNT=3');
    expect(occurrencesBetween(rule, ist(2026, 1, 1), ist(2026, 2, 1))).toHaveLength(3);
    expect(occurrencesBetween(rule, ist(2026, 1, 3), ist(2026, 2, 1))).toHaveLength(1);
  });

  it('UNTIL stops the series', () => {
    const rule = parseSchedule('DTSTART;TZID=Asia/Kolkata:20260101T080000\nRRULE:FREQ=DAILY;UNTIL=20260103T235959');
    expect(occurrencesBetween(rule, ist(2026, 1, 1), ist(2026, 2, 1))).toHaveLength(3);
  });

  it('monthly on the 31st skips short months (RFC 5545)', () => {
    const rule = parseSchedule('DTSTART;TZID=Asia/Kolkata:20260131T090000\nRRULE:FREQ=MONTHLY');
    const occ = occurrencesBetween(rule, ist(2026, 1, 1), ist(2026, 5, 1));
    expect(occ.map((t) => utcToCivil(t, 'Asia/Kolkata').m)).toEqual([1, 3]);
  });

  it('rejects unknown timezone and unsupported freq', () => {
    expect(() => parseSchedule('DTSTART;TZID=Mars/Base:20260101T080000\nRRULE:FREQ=DAILY')).toThrow(/timezone/i);
    expect(() => parseSchedule('FREQ=YEARLY')).toThrow(/FREQ/);
  });
});

describe('DST (America/New_York as a stand-in: India itself has none)', () => {
  const tz = 'America/New_York';
  const sched = (h: number, mi = 0) => `DTSTART;TZID=${tz}:20260301T${String(h).padStart(2, '0')}${String(mi).padStart(2, '0')}00\nRRULE:FREQ=DAILY`;

  it('spring forward: 02:30 does not exist on 2026-03-08, fires shifted forward (03:30 EDT)', () => {
    const rule = parseSchedule(sched(2, 30));
    const from = civilToUtc({ y: 2026, m: 3, d: 8, h: 0, mi: 0, s: 0 }, tz);
    const [t] = occurrencesBetween(rule, from, from + DAY);
    expect(new Date(t).toISOString()).toBe('2026-03-08T07:30:00.000Z'); // 03:30 EDT
  });

  it('fall back: 01:30 occurs twice on 2026-11-01, fires exactly once (first occurrence)', () => {
    const rule = parseSchedule(sched(1, 30).replace('20260301', '20261001'));
    const from = civilToUtc({ y: 2026, m: 11, d: 1, h: 0, mi: 0, s: 0 }, tz);
    const occ = occurrencesBetween(rule, from, from + 26 * HOUR);
    expect(occ.filter((t) => utcToCivil(t, tz).d === 1 && utcToCivil(t, tz).h === 1)).toHaveLength(1);
    expect(new Date(occ[0]).toISOString()).toBe('2026-11-01T05:30:00.000Z'); // 01:30 EDT
  });

  it('wall-clock time is stable across the DST change (08:00 local before and after)', () => {
    const rule = parseSchedule(sched(8));
    const occ = occurrencesBetween(rule, civilToUtc({ y: 2026, m: 3, d: 6, h: 0, mi: 0, s: 0 }, tz), civilToUtc({ y: 2026, m: 3, d: 11, h: 0, mi: 0, s: 0 }, tz));
    expect(occ.every((t) => utcToCivil(t, tz).h === 8)).toBe(true);
    expect(occ[1] - occ[0]).toBe(DAY); // 6th->7th
    expect(occ[2] - occ[1]).toBe(DAY - HOUR); // 7th->8th crosses spring-forward: only 23h apart
  });
});

describe('engine: due, snooze, ack', () => {
  const t0 = ist(2026, 1, 1, 7, 0);
  const due = ist(2026, 1, 1, 8, 0);

  it('fires due at the scheduled time, once', () => {
    const e = new ReminderEngine();
    e.upsert(rem(), t0);
    expect(e.tick(due - MIN)).toHaveLength(0);
    const ev = e.tick(due + 1000);
    expect(ev.map((x) => x.type)).toEqual(['due']);
    expect(e.tick(due + 2000)).toHaveLength(0);
  });

  it('snooze delays and re-fires; max snoozes enforced', () => {
    const e = new ReminderEngine();
    e.upsert(rem(), t0);
    e.tick(due);
    const at = e.snooze('r1', due, due + MIN, 10)!;
    expect(at).toBe(due + 11 * MIN);
    expect(e.tick(due + 5 * MIN)).toHaveLength(0);
    const ev = e.tick(at);
    expect(ev[0]).toMatchObject({ type: 'due', snoozed: true });
    e.snooze('r1', due, at, 10); e.tick(at + 10 * MIN);
    e.snooze('r1', due, at + 10 * MIN, 10); e.tick(at + 20 * MIN);
    expect(e.snooze('r1', due, at + 20 * MIN, 10)).toBeNull(); // 3 used
  });

  it('acknowledge stops the miss and resets streak', () => {
    const e = new ReminderEngine();
    e.upsert(rem(), t0);
    e.tick(due);
    expect(e.acknowledge('r1', due, due + 5 * MIN)?.type).toBe('acknowledged');
    expect(e.tick(due + 2 * HOUR).some((x) => x.type === 'missed')).toBe(false);
    expect(e.acknowledge('r1', due, due + 6 * MIN)).toBeNull(); // idempotent
  });

  it('snoozing within grace does not count as a miss until the snooze also lapses', () => {
    const e = new ReminderEngine({}, { graceMs: 20 * MIN });
    e.upsert(rem(), t0);
    e.tick(due);
    e.snooze('r1', due, due + 15 * MIN, 10); // wakes at +25
    expect(e.tick(due + 21 * MIN).some((x) => x.type === 'missed')).toBe(false);
    e.tick(due + 25 * MIN);
    expect(e.tick(due + 46 * MIN).some((x) => x.type === 'missed')).toBe(true);
  });
});

describe('engine: miss escalation (caregiver alert)', () => {
  const t0 = ist(2026, 1, 1, 7, 0);
  const d = (day: number) => ist(2026, 1, day, 8, 0);

  it('emits one escalation after N consecutive misses, not before, not repeatedly', () => {
    const e = new ReminderEngine();
    e.upsert(rem({ escalate_after_misses: 2 }), t0);
    const all = [...e.tick(d(1)), ...e.tick(d(1) + HOUR), ...e.tick(d(2)), ...e.tick(d(2) + HOUR), ...e.tick(d(3)), ...e.tick(d(3) + HOUR)];
    const esc = all.filter((x) => x.type === 'escalation');
    expect(esc).toHaveLength(1);
    expect(esc[0]).toMatchObject({ patient_id: 'p1', category: 'medicine', consecutive_misses: 2 });
    expect(all.filter((x) => x.type === 'missed')).toHaveLength(3);
  });

  it('an acknowledgement in between breaks the streak', () => {
    const e = new ReminderEngine();
    e.upsert(rem({ escalate_after_misses: 2 }), t0);
    e.tick(d(1)); e.tick(d(1) + HOUR); // miss 1
    e.tick(d(2)); e.acknowledge('r1', d(2), d(2) + MIN); // ack
    const ev = [...e.tick(d(3)), ...e.tick(d(3) + HOUR)]; // miss again, streak = 1
    expect(ev.some((x) => x.type === 'escalation')).toBe(false);
  });

  it('threshold 0 disables escalation', () => {
    const e = new ReminderEngine();
    e.upsert(rem({ escalate_after_misses: 0 }), t0);
    const ev = [1, 2, 3, 4].flatMap((n) => [...e.tick(d(n)), ...e.tick(d(n) + HOUR)]);
    expect(ev.some((x) => x.type === 'escalation')).toBe(false);
  });

  it('offline catch-up: device off for 2 days -> missed silently (no late voice prompt), escalation still raised', () => {
    const e = new ReminderEngine();
    e.upsert(rem({ escalate_after_misses: 2 }), t0);
    const ev = e.tick(d(3) + 2 * HOUR);
    expect(ev.filter((x) => x.type === 'due')).toHaveLength(0);
    expect(ev.filter((x) => x.type === 'missed').length).toBeGreaterThanOrEqual(2);
    expect(ev.filter((x) => x.type === 'escalation')).toHaveLength(1);
  });

  it('state survives serialisation (app restart) without double-firing', () => {
    const e1 = new ReminderEngine();
    e1.upsert(rem(), t0);
    e1.tick(d(1));
    const e2 = new ReminderEngine(JSON.parse(JSON.stringify(e1.getState())));
    e2.upsert(rem(), d(1) + MIN);
    expect(e2.tick(d(1) + 2 * MIN)).toHaveLength(0);
  });

  it('clock moving backwards does not fire or crash', () => {
    const e = new ReminderEngine();
    e.upsert(rem(), t0);
    e.tick(d(1) + HOUR);
    expect(() => e.tick(d(1) - HOUR)).not.toThrow();
    expect(e.tick(d(1) - HOUR + MIN)).toHaveLength(0);
  });
});
