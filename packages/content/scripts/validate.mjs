// node scripts/validate.mjs : checks packs, asset files exist, no unlicensed media. Exit 1 on problems.
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = dirname(dirname(fileURLToPath(import.meta.url)));
const CATS = ['instruments', 'textiles', 'food', 'festivals'];
let bad = 0; const fail = (m) => { console.error('FAIL', m); bad++; };
for (const f of readdirSync(join(root, 'packs'))) {
  const p = JSON.parse(readFileSync(join(root, 'packs', f), 'utf8')); const ids = new Set();
  if (p.license !== 'CC0-1.0') fail(`${f}: license`);
  for (const i of p.items) {
    if (ids.has(i.id)) fail(`${f}: dup ${i.id}`); ids.add(i.id);
    if (!i.labels?.en || !i.labels?.as) fail(`${f}:${i.id} labels`);
    if (i.image && !existsSync(join(root, i.image))) fail(`${f}:${i.id} missing ${i.image}`);
    if (i.kind === 'step' && !(i.routine_id && i.step_order)) fail(`${f}:${i.id} step fields`);
    if (i.kind === 'object' && !CATS.includes(i.category)) fail(`${f}:${i.id} category`);
  }
}
console.log(bad ? `${bad} problem(s)` : 'content OK'); process.exit(bad ? 1 : 0);
