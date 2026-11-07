import test from 'node:test'; import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { I, L } from './helpers.mjs';
const walk = (d) => readdirSync(d).flatMap((f) => { const p = join(d, f); return statSync(p).isDirectory() ? walk(p) : [p]; });
test('as and en define exactly the same keys', () => {
  assert.deepEqual(Object.keys(I.strings.as).sort(), Object.keys(I.strings.en).sort());
});
test('every literal games.* key used in src exists', () => {
  const src = walk(new URL('../src', import.meta.url).pathname).filter((f) => /\.(ts|tsx)$/.test(f) && !f.includes('strings.ts')).map((f) => readFileSync(f, 'utf8')).join('\n');
  const used = new Set([...src.matchAll(/'(games\.[a-z_.0-9]+)'/g)].map((m) => m[1]));
  for (const k of used) assert.ok(I.strings.en[k], `missing key ${k}`);
  for (const id of L.GAME_IDS) assert.ok(I.strings.en[`games.title.${id}`] && I.strings.as[`games.title.${id}`], id);
  for (const c of ['instruments', 'textiles', 'food', 'festivals']) assert.ok(I.strings.as[`games.cat.${c}`]);
});
test('t() falls back to en then key, and fills params', () => {
  assert.equal(I.t('bn', 'games.btn.next'), 'Next');
  assert.equal(I.t('en', 'nope.key'), 'nope.key');
  assert.equal(I.t('en', 'games.prompt.tap', { name: 'Dhol' }), 'Tap every Dhol.');
});
