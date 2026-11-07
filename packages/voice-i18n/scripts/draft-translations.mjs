#!/usr/bin/env node
// Drafts missing/stale translations from en.json via a running IndicTrans2 endpoint, and ALWAYS marks output
// needs_human_review: true. Machine translations are NEVER verified; a native speaker must review before release.
//
// Usage:
//   INDICTRANS2_URL=http://localhost:8003/translate node scripts/draft-translations.mjs [as bn ne brx mni] [--force]
//
// Expected endpoint contract (see docs/MODELS.md for a ready-made FastAPI wrapper snippet):
//   POST {url} {"sentences":[...], "src_lang":"eng_Latn", "tgt_lang":"asm_Beng"} -> {"translations":[...]}
// Does nothing destructive: existing human-reviewed files (needs_human_review:false) are skipped unless --force.
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'locales');
const URL_ = process.env.INDICTRANS2_URL;
const TGT = { as: 'asm_Beng', bn: 'ben_Beng', ne: 'npi_Deva', brx: 'brx_Deva', mni: 'mni_Mtei' };
const args = process.argv.slice(2);
const force = args.includes('--force');
const targets = args.filter((a) => !a.startsWith('--'));
const locales = targets.length ? targets : Object.keys(TGT);

if (!URL_) {
  console.error('Set INDICTRANS2_URL to a running IndicTrans2 endpoint. See docs/MODELS.md.');
  process.exit(2);
}

const flatten = (o, p = '') => Object.entries(o).flatMap(([k, v]) =>
  k === '_meta' ? [] : typeof v === 'object' ? flatten(v, p + k + '.') : [[p + k, v]]);
const setPath = (o, path, val) => {
  const ks = path.split('.');
  ks.slice(0, -1).reduce((a, k) => (a[k] ??= {}), o)[ks.at(-1)] = val;
};

// Protect {{placeholders}} from being translated.
const protect = (s) => s.replace(/\{\{(\w+)\}\}/g, (_, n) => `__PH_${n}__`);
const restore = (s) => s.replace(/__PH_(\w+)__/g, (_, n) => `{{${n}}}`);

const en = JSON.parse(readFileSync(join(dir, 'en.json'), 'utf8'));
const entries = flatten(en);

for (const loc of locales) {
  if (!TGT[loc]) { console.error(`skip unknown locale ${loc}`); continue; }
  const file = join(dir, `${loc}.json`);
  const cur = JSON.parse(readFileSync(file, 'utf8'));
  if (cur._meta?.needs_human_review === false && !force) { console.log(`${loc}: human-reviewed, skipping (use --force)`); continue; }
  const have = new Map(flatten(cur));
  const todo = entries.filter(([k]) => force || !have.has(k) || cur._meta?.status === 'untranslated_fallback_to_en');
  if (!todo.length) { console.log(`${loc}: nothing to translate`); continue; }
  const res = await fetch(URL_, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ sentences: todo.map(([, v]) => protect(v)), src_lang: 'eng_Latn', tgt_lang: TGT[loc] }),
  });
  if (!res.ok) { console.error(`${loc}: endpoint error ${res.status}`); continue; }
  const { translations } = await res.json();
  if (translations.length !== todo.length) { console.error(`${loc}: length mismatch, not writing`); continue; }
  todo.forEach(([k], i) => setPath(cur, k, restore(translations[i])));
  cur._meta = { locale: loc, needs_human_review: true, source: 'IndicTrans2 machine draft, NOT verified', drafted_at: new Date().toISOString() };
  writeFileSync(file, JSON.stringify(cur, null, 2) + '\n');
  console.log(`${loc}: drafted ${todo.length} strings, needs_human_review=true`);
}
