import test from 'node:test'; import assert from 'node:assert/strict';
import { L, M, content, mkCtx } from './helpers.mjs';
const { PairsEngine, ChoiceEngine, GridEngine, TapEngine, SpotEngine, OrderEngine } = L;

function play(id, d, cues) {
  const { ctx, events } = mkCtx(`${id}-${d}`);
  if (id === 'memory_pairs') {
    const e = new PairsEngine(content, d, ctx, cues); assert.ok(e.ready);
    const [a, b] = [e.cards[0], e.cards.find((c) => c.item.id !== e.cards[0].item.id)];
    e.flip(a.card_id); assert.equal(e.flip(b.card_id).kind, 'mismatch'); assert.ok(e.hint().length);
    for (const it of new Set(e.cards.map((c) => c.item.id))) { const [x, y] = e.cards.filter((c) => c.item.id === it); e.flip(x.card_id); e.flip(y.card_id); }
    assert.ok(e.finished);
  } else if (id === 'image_grid') {
    const e = new GridEngine(content, d, ctx, cues); e.start();
    while (!e.finished) { let g = 0; while (!e.solved && g++ < 200) { const p = e.tiles.findIndex((t, i) => t !== i); if (g === 1) e.hint(); e.select(p); e.select(e.tiles.indexOf(p)); } assert.ok(e.solved); e.next(); }
  } else if (id === 'target_tap') {
    const e = new TapEngine(content, d, ctx, cues); e.start();
    while (!e.finished) { const r = e.round; const w = r.cells.find((c) => !r.targetCells.has(c.cell_id)); e.tap(w.cell_id); for (const c of r.targetCells) e.tap(c); assert.ok(e.solved); e.next(); }
  } else if (id === 'spot_diff') {
    const e = new SpotEngine(content, d, ctx, cues); e.start();
    while (!e.finished) { const r = e.round; const w = r.a.findIndex((_, i) => !r.diff.has(i)); e.tap(w); for (const i of r.diff) e.tap(i); assert.ok(e.solved); e.next(); }
  } else if (id === 'routine_order' || id === 'arrange_steps') {
    const rid = id === 'routine_order' ? 'morning' : 'make_tea';
    const e = new OrderEngine(content, rid, id, d, ctx, cues); e.start();
    for (const s of e.order) { const wrong = e.presented.find((p) => !e.isPlaced(p.id) && p.id !== s.id); if (wrong) e.tap(wrong.id); assert.equal(e.tap(s.id).correct, true); }
    assert.ok(e.finished);
  } else {
    const kind = { odd_one_out: 'odd', naming: 'name', sorting: 'sort', routine_next: 'next' }[id];
    const e = new ChoiceEngine(kind, content, d, ctx, cues); assert.ok(e.ready, id); e.start();
    while (!e.finished) { const r = e.round; const w = r.options.find((o) => o.id !== r.correct_id); const res = e.answer(w.id); assert.equal(res.correct, false); assert.equal(e.answer(r.correct_id).correct, true); e.next(); }
  }
  return { ctx, events };
}
for (const id of L.GAME_IDS) for (const d of [1, 5, 9]) {
  test(`${id} @${d}: perfect+recovering play emits valid, cue-consistent events`, () => {
    const { ctx, events } = play(id, d, M.mockCues);
    assert.ok(events.length > 3);
    for (const e of events) assert.deepEqual(L.validateGameEvent(e), [], JSON.stringify(e));
    assert.ok(events.some((e) => e.type === 'hint_used' || e.type === 'answer'));
    const s = ctx.summary(id, d);
    assert.ok(s.with_cue.answers > 0 && s.without_cue.answers > 0, `both cue arms present ${JSON.stringify(s)}`);
    assert.equal(s.disclaimer_key, 'games.disclaimer');
  });
}
test('no cues => with_cue always false', () => {
  const { events } = play('memory_pairs', 5, []);
  assert.ok(events.every((e) => e.with_cue === false && e.cue_id === undefined));
});
test('same seed => same game', () => {
  const a = new PairsEngine(content, 5, mkCtx('z').ctx, M.mockCues), b = new PairsEngine(content, 5, mkCtx('z').ctx, M.mockCues);
  assert.deepEqual(a.cards.map((c) => c.card_id), b.cards.map((c) => c.card_id));
});
test('difficulty map: all games 1..10, harder is not easier', () => {
  for (const id of L.GAME_IDS) for (let d = 1; d <= 10; d++) assert.ok(L.difficultyMap[id][d]);
  assert.ok(L.paramsFor('memory_pairs', 10).pairs > L.paramsFor('memory_pairs', 1).pairs);
  assert.ok(L.paramsFor('image_grid', 10).grid > L.paramsFor('image_grid', 1).grid);
});
test('caregiver photos are prioritised in pairs', () => {
  const cg = { id: 'cg1', kind: 'photo', category: 'my_photos', labels: { en: 'Mum' }, image: 'x.jpg', source: 'caregiver' };
  const e = new PairsEngine([...content, cg], 1, mkCtx('q').ctx, []);
  assert.ok(e.cards.some((c) => c.item.id === 'cg1'));
});
test('too little content => not ready, no crash', () => {
  const { ctx } = mkCtx();
  assert.equal(new PairsEngine([], 5, ctx, []).ready, false);
  assert.equal(new ChoiceEngine('odd', [], 5, ctx, []).ready, false);
  assert.equal(new GridEngine([], 5, ctx, []).ready, false);
});
