import i18next, { type i18n } from 'i18next';
import { initReactI18next } from 'react-i18next';
import as from './locales/as.json';
import bn from './locales/bn.json';
import brx from './locales/brx.json';
import en from './locales/en.json';
import mni from './locales/mni.json';
import ne from './locales/ne.json';
import { LOCALES, type AnyLocale, type Locale } from '../core/types';

export const resources = {
  as: { translation: as }, bn: { translation: bn }, ne: { translation: ne },
  brx: { translation: brx }, mni: { translation: mni }, en: { translation: en },
} as const;

/** Locales whose strings are machine/AI drafts and NOT verified by a native speaker. */
export function needsHumanReview(locale: Locale): boolean {
  return (resources[locale].translation as { _meta?: { needs_human_review?: boolean } })._meta?.needs_human_review !== false;
}

export const FONT_STACKS: Record<Locale, string> = {
  as: "'Noto Sans Bengali', 'Noto Sans', system-ui, sans-serif",
  bn: "'Noto Sans Bengali', 'Noto Sans', system-ui, sans-serif",
  ne: "'Noto Sans Devanagari', 'Noto Sans', system-ui, sans-serif",
  brx: "'Noto Sans Devanagari', 'Noto Sans', system-ui, sans-serif",
  mni: "'Noto Sans Meetei Mayek', 'Noto Sans Bengali', 'Noto Sans', system-ui, sans-serif",
  en: "'Noto Sans', system-ui, sans-serif",
};

export function initI18n(initial: Locale = 'as', instance: i18n = i18next.createInstance()): i18n {
  void instance.use(initReactI18next).init({
    resources,
    lng: initial,
    fallbackLng: 'en',
    supportedLngs: [...LOCALES],
    interpolation: { escapeValue: false },
    returnNull: false,
    initImmediate: false,
  });
  return instance;
}

/** StringTable for VoiceClient: resolves "voice.good" style keys, returns undefined for free text. */
export function stringTable(instance: i18n) {
  return {
    t(key: string, locale: AnyLocale): string | undefined {
      if (!/^[a-z_]+(\.[a-z_]+)+$/.test(key)) return undefined;
      const lng = (LOCALES as string[]).includes(locale) ? locale : 'en';
      return instance.exists(key, { lng }) ? (instance.t(key, { lng }) as string) : undefined;
    },
  };
}
