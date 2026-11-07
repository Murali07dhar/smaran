// Simple keyword intent grammar. Word lists are DRAFTS (needs_human_review): native speakers must verify.
// Matching is on normalised whole words / phrases; unknown -> 'unknown'. Pure TS.
import type { AnyLocale, Intent } from './types';

type Grammar = Record<Exclude<Intent, 'unknown'>, string[]>;

export const INTENT_GRAMMAR_NEEDS_REVIEW = true;

const en: Grammar = {
  yes: ['yes', 'yeah', 'yep', 'ok', 'okay', 'sure', 'i did'],
  no: ['no', 'nope', 'not yet', "don't", 'later'],
  next: ['next', 'continue', 'go on', 'forward'],
  repeat: ['repeat', 'again', 'say again', 'once more'],
  help: ['help', 'hint', 'i need help', 'confused'],
  done: ['done', 'finish', 'finished', 'stop', 'that is all', 'quit'],
};
const as: Grammar = {
  yes: ['হয়', 'হ্যাঁ', 'ঠিক আছে', 'হয় হয়'],
  no: ['নহয়', 'নাই', 'নাহয়', 'পিছত'],
  next: ['পিছৰটো', 'আগবাঢ়ক', 'পৰৱৰ্তী'],
  repeat: ['আকৌ', 'পুনৰ কওক', 'আকৌ কওক'],
  help: ['সহায়', 'সহায় লাগে', 'বুজা নাই'],
  done: ['শেষ', 'হ’ল', 'হল', 'বন্ধ'],
};
const bn: Grammar = {
  yes: ['হ্যাঁ', 'হ্যা', 'ঠিক আছে', 'জি'],
  no: ['না', 'নয়', 'পরে'],
  next: ['পরের', 'পরবর্তী', 'এগিয়ে যাও'],
  repeat: ['আবার', 'আবার বলো', 'আরেকবার'],
  help: ['সাহায্য', 'সাহায্য করো', 'বুঝতে পারছি না'],
  done: ['শেষ', 'হয়ে গেছে', 'বন্ধ'],
};
const ne: Grammar = {
  yes: ['हो', 'हुन्छ', 'ठीक छ', 'खाएँ'],
  no: ['होइन', 'हुँदैन', 'पछि'],
  next: ['अर्को', 'अगाडि', 'अगाडि बढ'],
  repeat: ['फेरि', 'फेरि भन', 'दोहोर्याउ'],
  help: ['मद्दत', 'सहयोग', 'बुझिन'],
  done: ['सकियो', 'भयो', 'बन्द'],
};
// Bodo (Devanagari) and Meitei (Meetei Mayek / Latin transliteration): minimal drafts, low confidence.
const brx: Grammar = {
  yes: ['aon', 'अं', 'आं', 'हां'],
  no: ['nai', 'नांगौ', 'नङा', 'नङै'],
  next: ['जोबोद', 'अख्रां', 'next'],
  repeat: ['फिन', 'फिनजा', 'again'],
  help: ['मदद', 'help', 'हेल्प'],
  done: ['जोबोद गोख्रै', 'सोलोंनाय', 'done'],
};
const mni: Grammar = {
  yes: ['ꯍꯌ', 'haan', 'hoi', 'ꯍꯣꯢ', 'hoi'],
  no: ['ꯅꯠꯇ', 'natte', 'ꯅꯠꯇꯦ', 'nattaba'],
  next: ['ꯃꯇꯧ', 'matamda', 'next'],
  repeat: ['ꯑꯃꯨꯛ', 'amuk', 'again'],
  help: ['ꯃꯇꯦꯡ', 'mateng', 'help'],
  done: ['ꯂꯣꯏꯈꯤ', 'loikhi', 'done'],
};

const GRAMMARS: Partial<Record<AnyLocale, Grammar>> = { en, as, bn, ne, brx, mni };

export function normalise(s: string): string {
  return s.toLowerCase().normalize('NFC').replace(/[.,!?।'"’]/g, ' ').replace(/\s+/g, ' ').trim();
}

function contains(haystack: string, phrase: string): boolean {
  const p = normalise(phrase);
  if (!p) return false;
  return (' ' + haystack + ' ').includes(' ' + p + ' ');
}

/** Order matters: more specific/safety-relevant intents first (help before yes/no). English always checked as fallback. */
const ORDER: Array<Exclude<Intent, 'unknown'>> = ['help', 'done', 'repeat', 'next', 'no', 'yes'];

export function parseIntent(transcript: string, locale: AnyLocale): Intent {
  const t = normalise(transcript);
  if (!t) return 'unknown';
  const grammars = [GRAMMARS[locale], locale === 'en' ? undefined : en].filter(Boolean) as Grammar[];
  for (const intent of ORDER) {
    for (const g of grammars) if (g[intent].some((p) => contains(t, p))) return intent;
  }
  return 'unknown';
}

export function grammarFor(locale: AnyLocale): Grammar | undefined { return GRAMMARS[locale]; }
