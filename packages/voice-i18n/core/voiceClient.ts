// VoiceAPI implementation. Tries services/voice (if reachable), else falls back to on-device adapters.
// Fully offline capable: speak -> AudioAdapter.speakText (SpeechSynthesis); listen -> optional BrowserSTT adapter.
import { parseIntent } from './intents';
import type { AnyLocale, AudioAdapter, ListenOpts, ListenResult, MicAdapter, VoiceAPI } from './types';
import type { PackLoader } from './voicepack';

export interface BrowserSTTAdapter {
  available(locale: string): boolean;
  /** Push-to-talk using the Web Speech API (or native equivalent). Resolves transcript, '' if nothing heard. */
  listenOnce(locale: string, maxMs: number): Promise<string>;
  abort(): void;
}

export interface StringTable { t(key: string, locale: AnyLocale): string | undefined }

export interface VoiceClientDeps {
  audio: AudioAdapter;
  mic?: MicAdapter;
  stt?: BrowserSTTAdapter;
  packs?: PackLoader;
  strings?: StringTable;
  /** services/voice base URL, e.g. http://localhost:8002. Omit for pure on-device mode. */
  serviceUrl?: string;
  token?: string;
  fetchImpl?: typeof fetch;
  isOnline?: () => boolean;
  serviceTimeoutMs?: number;
}

export type VoiceMode = 'service' | 'browser' | 'none';

export class VoiceClient implements VoiceAPI {
  private speaking = false;
  private listening = false;
  lastMode: { speak: VoiceMode; listen: VoiceMode } = { speak: 'none', listen: 'none' };

  constructor(private d: VoiceClientDeps) {}

  private online() { return this.d.isOnline ? this.d.isOnline() : true; }
  private f() { return this.d.fetchImpl ?? (typeof fetch !== 'undefined' ? fetch : undefined); }

  private async post(path: string, body: BodyInit, headers: Record<string, string> = {}): Promise<Response | null> {
    const f = this.f();
    if (!this.d.serviceUrl || !f || !this.online()) return null;
    const ctl = typeof AbortController !== 'undefined' ? new AbortController() : undefined;
    const to = ctl ? setTimeout(() => ctl.abort(), this.d.serviceTimeoutMs ?? 4000) : undefined;
    try {
      const res = await f(`${this.d.serviceUrl}${path}`, {
        method: 'POST', body, signal: ctl?.signal,
        headers: { ...(this.d.token ? { Authorization: `Bearer ${this.d.token}` } : {}), ...headers },
      });
      return res.ok ? res : null;
    } catch { return null; } finally { if (to) clearTimeout(to); }
  }

  /** keyOrText: if it matches a string-table key it is resolved in the locale, otherwise spoken as-is. */
  async speak(keyOrText: string, locale: AnyLocale): Promise<void> {
    const text = this.d.strings?.t(keyOrText, locale) ?? keyOrText;
    this.stop();
    this.speaking = true;
    try {
      // 1) on-device TTS if the OS has a voice for this locale (fastest, offline)
      if (this.d.audio.hasTTS(locale)) {
        this.lastMode.speak = 'browser';
        await this.d.audio.speakText(text, locale);
        return;
      }
      // 2) server TTS (Indic TTS) when online and locale has no local voice
      const res = await this.post('/voice/tts', JSON.stringify({ text, locale }), { 'Content-Type': 'application/json' });
      if (res && (res.headers.get('content-type') ?? '').startsWith('audio')) {
        this.lastMode.speak = 'service';
        await this.d.audio.playBytes(await res.arrayBuffer(), res.headers.get('content-type')!);
        return;
      }
      // 3) last resort: still attempt browser speak (may use default voice); never throw to the elder UI
      this.lastMode.speak = 'browser';
      await this.d.audio.speakText(text, locale);
    } catch {
      this.lastMode.speak = 'none'; // UI must show the text on screen: voice is an enhancement, not a requirement
    } finally {
      this.speaking = false;
    }
  }

  async listen(opts: ListenOpts): Promise<ListenResult> {
    if (this.listening) return { transcript: '', intent: 'unknown' };
    this.listening = true;
    const maxMs = opts.maxMs ?? 8000;
    try {
      // Online + mic adapter: send audio to IndicConformer
      if (this.d.mic && this.d.serviceUrl && this.online()) {
        await this.d.mic.start();
        await new Promise((r) => setTimeout(r, maxMs));
        const { bytes, mime } = await this.d.mic.stop();
        const res = await this.post(`/voice/asr?locale=${encodeURIComponent(opts.locale)}`, bytes, { 'Content-Type': mime });
        if (res) {
          const j = (await res.json()) as { transcript?: string; intent?: string };
          if (j.transcript !== undefined) {
            this.lastMode.listen = 'service';
            return { transcript: j.transcript, intent: parseIntent(j.transcript, opts.locale) };
          }
        }
      }
      // Offline / fallback: Web Speech API
      if (this.d.stt?.available(opts.locale)) {
        this.lastMode.listen = 'browser';
        const transcript = await this.d.stt.listenOnce(opts.locale, maxMs);
        return { transcript, intent: parseIntent(transcript, opts.locale) };
      }
      this.lastMode.listen = 'none';
      return { transcript: '', intent: 'unknown' }; // UI falls back to big tap buttons (Yes / No / Next ...)
    } catch {
      this.lastMode.listen = 'none';
      return { transcript: '', intent: 'unknown' };
    } finally {
      this.listening = false;
    }
  }

  /** True push-to-talk: call on button press. Caller must hold a mic ConsentRecord. Returns false if no mic. */
  async startTalk(): Promise<boolean> {
    if (!this.d.mic) return false;
    this.stop();
    try { await this.d.mic.start(); return true; } catch { return false; }
  }

  /** Call on button release. Online: ASR service. Otherwise unknown (UI shows tap buttons). */
  async endTalk(locale: AnyLocale): Promise<ListenResult> {
    if (!this.d.mic) return { transcript: '', intent: 'unknown' };
    try {
      const { bytes, mime } = await this.d.mic.stop();
      const res = await this.post(`/voice/asr?locale=${encodeURIComponent(locale)}`, bytes, { 'Content-Type': mime });
      if (res) {
        const j = (await res.json()) as { transcript?: string };
        if (j.transcript !== undefined) {
          this.lastMode.listen = 'service';
          return { transcript: j.transcript, intent: parseIntent(j.transcript, locale) };
        }
      }
    } catch { /* fall through */ }
    this.lastMode.listen = 'none';
    return { transcript: '', intent: 'unknown' };
  }

  async playPack(pack_id: string, clip_id: string): Promise<void> {
    if (!this.d.packs) return;
    this.stop();
    const clip = await this.d.packs.getClip(pack_id, clip_id);
    if (clip) await this.d.audio.playBytes(clip.bytes, clip.mime);
  }

  stop(): void {
    this.d.audio.stop();
    this.d.stt?.abort();
    this.speaking = false;
  }
}
