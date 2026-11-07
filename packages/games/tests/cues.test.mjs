import test from 'node:test'; import assert from 'node:assert/strict';
import { L, M } from './helpers.mjs';
const slots = (n) => Array.from({ length: n }, (_, i) => ({ key: `k${i}` }));
test('even n is exactly balanced', () => {
  for (let s = 0; s < 20; s++) { const m = L.assignCues(slots(6), M.mockCues, L.createRng(s)); assert.equal([...m.values()].filter(Boolean).length, 3); }
});
test('n=1 sees both arms across seeds; no cues => none', () => {
  const arms = new Set(); for (let s = 0; s < 30; s++) arms.add(!!L.assignCues(slots(1), M.mockCues, L.createRng(s)).get('k0'));
  assert.equal(arms.size, 2);
  assert.ok([...L.assignCues(slots(4), [], L.createRng(1)).values()].every((v) => v === null));
});
test('item-linked cue preferred', () => {
  const cues = [...M.mockCues, { cue_id: 'linked', cue_type: 'photo', uri: 'x', item_id: 'a' }];
  let hit = 0; for (let s = 0; s < 20; s++) { const m = L.assignCues([{ key: 'a', item_id: 'a' }, { key: 'b', item_id: 'b' }], cues, L.createRng(s)); if (m.get('a')) { assert.equal(m.get('a').cue_id, 'linked'); hit++; } }
  assert.ok(hit > 0);
});
