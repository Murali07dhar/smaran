import { VoiceClient, WebAudioAdapter, WebMicAdapter, WebSpeechSTT, initI18n, stringTable, type StringTable } from "@smaran/voice-i18n";
import { strings as gameStrings } from "@smaran/games";

// D3: ONE StringTable = games.* table + voice-i18n locale JSON, injected into VoiceClient.
const voiceI18n = initI18n("en");
const voiceTable = stringTable(voiceI18n);

export const composedStrings: StringTable = {
  t(key, locale) {
    const g = gameStrings[locale]?.[key] ?? gameStrings.en?.[key];
    return g ?? voiceTable.t(key, locale);
  }
};

export interface VoiceOpts { micAllowed: boolean; serviceUrl?: string; token?: string }

/** Mic/STT are only handed to the client after a recorded `mic` consent (non-negotiable). */
export function createVoice(opts: VoiceOpts): VoiceClient {
  return new VoiceClient({
    audio: new WebAudioAdapter(),
    mic: opts.micAllowed ? new WebMicAdapter() : undefined,
    stt: opts.micAllowed ? new WebSpeechSTT() : undefined,
    strings: composedStrings,
    serviceUrl: opts.serviceUrl,
    token: opts.token,
    isOnline: () => (typeof navigator === "undefined" ? true : navigator.onLine)
  });
}

let speaker: VoiceClient | undefined;
/** Output-only voice (no mic): safe without consent; used by reminder alerts. */
export function getSpeaker(): VoiceClient {
  return (speaker ??= createVoice({ micAllowed: false }));
}
