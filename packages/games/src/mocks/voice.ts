import type { VoiceAPI } from '../types';
import { strings, t } from '../i18n/strings';

export interface MockVoice extends VoiceAPI { log: { kind: 'speak' | 'pack' | 'stop'; arg: string; locale?: string; text?: string }[] }
/** Mock VoiceAPI (replace with packages/voice-i18n at merge). Resolves games.* keys locally; records every call. */
export function createMockVoice(o: { onSpeak?: (text: string, locale: string) => void } = {}): MockVoice {
  const log: MockVoice['log'] = [];
  return {
    log,
    async speak(keyOrText, locale) {
      const text = strings.en[keyOrText] !== undefined ? t(locale, keyOrText) : keyOrText;
      log.push({ kind: 'speak', arg: keyOrText, locale, text });
      o.onSpeak?.(text, locale);
    },
    async listen(_opts) { return { transcript: '', intent: 'unknown' as const }; },
    async playPack(pack_id, clip_id) { log.push({ kind: 'pack', arg: `${pack_id}/${clip_id}` }); },
    stop() { log.push({ kind: 'stop', arg: '' }); },
  };
}
