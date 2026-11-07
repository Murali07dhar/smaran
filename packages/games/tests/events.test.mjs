import test from 'node:test'; import assert from 'node:assert/strict';
import { L, M, mkCtx } from './helpers.mjs';
test('valid event passes, bad ones fail', () => {
  const { ctx } = mkCtx();
  const e = ctx.event('answer', 'x', { correct: true, response_ms: 1200.6, cue: M.mockCues[0] });
  assert.deepEqual(L.validateGameEvent(e), []);
  assert.equal(e.response_ms, 1201); assert.equal(e.with_cue, true); assert.equal(e.cue_id, M.mockCues[0].cue_id);
  assert.ok(L.validateGameEvent({ ...e, extra: 1 }).length);
  assert.ok(L.validateGameEvent({ ...e, with_cue: false }).length);
  assert.ok(L.validateGameEvent({ ...e, type: 'fail' }).length);
  assert.ok(L.validateGameEvent({ ...e, ts: 'yesterday' }).length);
});
test('uuidv7 shape and time order', () => {
  const a = L.uuidv7(1_700_000_000_000), b = L.uuidv7(1_700_000_100_000);
  assert.match(a, /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.ok(a.slice(0, 13) < b.slice(0, 13));
});
test('observations: first answer per arm', () => {
  const { ctx } = mkCtx();
  ctx.event('answer', 'i1', { correct: false, cue: M.mockCues[0] }); ctx.event('answer', 'i1', { correct: true, cue: M.mockCues[0] });
  ctx.event('answer', 'i1', { correct: true });
  const o = L.toObservations(ctx.events, M.mockCues);
  assert.equal(o.length, 2); assert.equal(o[0].recalled, false); assert.equal(o[0].valence_label, 'comfort'); assert.equal(o[1].with_cue, false);
});
