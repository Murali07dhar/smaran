// Reminder phrase templates per category and locale. DRAFTS: all non-English text needs human review.
// Warm, non-pressuring tone; no failure language. {title} and {name} are substituted.
import type { AnyLocale, Reminder, ReminderCategory } from './types';

export const PHRASES_NEED_REVIEW = true;

type Templates = Record<ReminderCategory, string[]>;

const T: Partial<Record<AnyLocale, Templates>> = {
  en: {
    medicine: ['{name}, it is time for your medicine: {title}.', 'Gentle reminder, {name}. Your medicine {title} is ready.'],
    hydration: ['{name}, a glass of water would feel nice now.', 'Time for some water, {name}.'],
    activity: ['{name}, let us do something nice: {title}.', 'Whenever you are ready, {name}: {title}.'],
    appointment: ['{name}, you have an appointment: {title}.', 'A little reminder, {name}: {title} is coming up.'],
  },
  as: {
    medicine: ['{name}, আপোনাৰ ঔষধ খোৱাৰ সময় হ’ল: {title}।', '{name}, আপোনাৰ ঔষধ {title} সাজু।'],
    hydration: ['{name}, এগিলাচ পানী খালে ভাল লাগিব।', '{name}, পানী খোৱাৰ সময়।'],
    activity: ['{name}, আহক এতিয়া {title} কৰোঁ।', '{name}, মন গ’লে {title}।'],
    appointment: ['{name}, আপোনাৰ এটা অ্যাপইণ্টমেণ্ট আছে: {title}।', '{name}, {title} ওচৰ চাপিছে।'],
  },
  bn: {
    medicine: ['{name}, আপনার ওষুধ খাওয়ার সময় হয়েছে: {title}।', '{name}, আপনার ওষুধ {title} তৈরি।'],
    hydration: ['{name}, এক গ্লাস জল খেলে ভালো লাগবে।', '{name}, জল খাওয়ার সময়।'],
    activity: ['{name}, চলুন এখন {title} করি।', '{name}, ইচ্ছে হলে {title}।'],
    appointment: ['{name}, আপনার একটি অ্যাপয়েন্টমেন্ট আছে: {title}।', '{name}, {title} আসছে।'],
  },
  ne: {
    medicine: ['{name}, तपाईंको औषधि खाने समय भयो: {title}।', '{name}, तपाईंको औषधि {title} तयार छ।'],
    hydration: ['{name}, एक गिलास पानी पिउनुभयो भने राम्रो हुन्छ।', '{name}, पानी पिउने समय भयो।'],
    activity: ['{name}, अब {title} गरौं।', '{name}, मन लाग्दा {title}।'],
    appointment: ['{name}, तपाईंको अपोइन्टमेन्ट छ: {title}।', '{name}, {title} नजिकिँदैछ।'],
  },
  // brx / mni: only the English-script-safe fallback is shipped until native review. Falls back to English text
  // or, better, to a family-recorded voice clip (voice_clip_id).
};

export interface PhraseCtx { name?: string; title: string }

/** djb2 hash for deterministic variant choice. */
function hash(s: string): number {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

export interface PhraseResult { text: string; locale_used: AnyLocale; source: 'template' | 'gemini'; needs_review: boolean }

/** Deterministic: same reminder + same day-bucket -> same phrase (no randomness, works offline). */
export function templatePhrase(r: Pick<Reminder, 'id' | 'category' | 'title' | 'locale'>, ctx: { name?: string }, seed = 0): PhraseResult {
  const locale = T[r.locale] ? r.locale : 'en';
  const list = T[locale]![r.category];
  const tpl = list[hash(r.id + ':' + seed) % list.length];
  const text = tpl.replace('{name}', ctx.name ?? '').replace('{title}', r.title).replace(/^,\s*/, '').replace(/\s+,/g, ',').trim();
  return { text, locale_used: locale, source: 'template', needs_review: locale !== 'en' };
}

export interface GeminiClientOpts {
  fetchImpl?: typeof fetch;
  baseUrl: string;      // e.g. http://localhost:8001
  token?: string;
  timeoutMs?: number;
}

/** Optional Gemini variation through /ai/content/generate. Any failure -> deterministic template. */
export async function variedPhrase(
  r: Pick<Reminder, 'id' | 'category' | 'title' | 'locale'>,
  ctx: { name?: string },
  seed: number,
  gemini?: GeminiClientOpts,
): Promise<PhraseResult> {
  const base = templatePhrase(r, ctx, seed);
  if (!gemini) return base;
  const f = gemini.fetchImpl ?? (typeof fetch !== 'undefined' ? fetch : undefined);
  if (!f) return base;
  try {
    const ctl = typeof AbortController !== 'undefined' ? new AbortController() : undefined;
    const to = ctl ? setTimeout(() => ctl.abort(), gemini.timeoutMs ?? 2500) : undefined;
    const res = await f(`${gemini.baseUrl}/ai/content/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(gemini.token ? { Authorization: `Bearer ${gemini.token}` } : {}) },
      body: JSON.stringify({ kind: 'reminder_phrase', locale: r.locale, context: { category: r.category, title: r.title, name: ctx.name, base_text: base.text } }),
      signal: ctl?.signal,
    });
    if (to) clearTimeout(to);
    if (!res.ok) return base;
    const data = (await res.json()) as { text?: string; source?: 'gemini' | 'template' };
    if (!data.text || data.text.length > 280 || !data.text.includes(r.title)) return base; // must keep the medicine/title
    return { text: data.text, locale_used: r.locale, source: data.source === 'gemini' ? 'gemini' : 'template', needs_review: true };
  } catch {
    return base;
  }
}
