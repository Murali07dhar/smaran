import test from 'node:test'; import assert from 'node:assert/strict';
import { M, C } from './helpers.mjs';
const tick = () => new Promise((r) => setTimeout(r, 0));
test('bus: authoritative seq, fan-out, leave', async () => {
  const bus = M.createCoopBus(), p = bus.transport(), f = bus.transport();
  const gotP = [], gotF = [];
  p.onMessage((m) => gotP.push(m)); f.onMessage((m) => gotF.push(m));
  p.join('r'); f.join('r');
  p.send(C.joinMsg('patient')); f.send(C.hintMsg('family', 'i1')); await tick();
  assert.deepEqual(gotP.map((m) => m.seq), [1, 2]); assert.deepEqual(gotF.map((m) => m.seq), [1, 2]);
  f.leave(); p.send(C.encourageMsg('patient', 'k')); await tick();
  assert.equal(gotF.length, 2);
});
test('reducer: ignores own + stale, applies peer messages', () => {
  let s = C.initialCoopState;
  const prog = { round_index: 1, rounds_total: 4, prompt_key: 'k', hints_used: 0 };
  s = C.applyMessage(s, { type: 'state_patch', seq: 1, payload: { from: 'patient', kind: 'progress', progress: prog } }, 'patient');
  assert.equal(s.progress, null);
  s = C.applyMessage(s, { type: 'state_patch', seq: 2, payload: { from: 'patient', kind: 'progress', progress: prog } }, 'family');
  assert.equal(s.progress.rounds_total, 4);
  const stale = C.applyMessage(s, { type: 'hint', seq: 2, payload: { from: 'family', item_id: 'x' } }, 'patient');
  assert.equal(stale.hint, null);
  s = C.applyMessage(s, { type: 'hint', seq: 3, payload: { from: 'family', item_id: 'x' } }, 'patient');
  assert.deepEqual(s.hint, { item_id: 'x', n: 1 });
  s = C.applyMessage(s, { type: 'state_patch', seq: 4, payload: { from: 'family', kind: 'picks', item_ids: ['a', 'b'] } }, 'patient');
  assert.deepEqual(s.picked_item_ids, ['a', 'b']);
});
test('mock voice resolves keys and records', async () => {
  const v = M.createMockVoice(); await v.speak('games.btn.next', 'as'); await v.speak('hello', 'en');
  assert.equal(v.log[0].text, 'পিছলৈ'); assert.equal(v.log[1].text, 'hello');
});
