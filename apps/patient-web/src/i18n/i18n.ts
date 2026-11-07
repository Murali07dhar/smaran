import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import as from "./locales/as.json";

// UI copy only. Voice packs / ASR-TTS locale coverage (as, bn, ne, brx, mni,
// en full; lus, kha, grt voice-only) live in @smaran/voice-i18n (Claude 6).
void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    as: { translation: as }
  },
  lng: "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false }
});

export default i18n;
