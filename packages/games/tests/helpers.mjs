import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
export const L = require('../dist-test/src/logic/index.js');
export const M = require('../dist-test/src/mocks/index.js');
export const C = require('../dist-test/src/coop/index.js');
export const I = require('../dist-test/src/i18n/strings.js');
const pack = (f) => JSON.parse(readFileSync(new URL(`../../content/packs/${f}`, import.meta.url), 'utf8')).items;
export const content = [...pack('assam.json'), ...pack('demo_photos.json'), ...pack('routines.json')];
export function mkCtx(seed = 's1') {
  let t = 1_700_000_000_000; const events = [];
  const ctx = L.createGameContext({ session_id: 'sess-1', seed, now: () => (t += 250), onEvent: (e) => events.push(e) });
  return { ctx, events };
}
