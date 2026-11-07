import type { AudioAdapter, MicAdapter, NotificationAdapter } from '../../../core/types';
import type { BrowserSTTAdapter } from '../../../core/voiceClient';

const BCP47: Record<string, string> = {
  as: 'as-IN', bn: 'bn-IN', ne: 'ne-NP', en: 'en-IN', brx: 'hi-IN', mni: 'bn-IN', lus: 'en-IN', kha: 'en-IN', grt: 'en-IN',
};
export const toBcp47 = (l: string) => BCP47[l] ?? l;

export class WebAudioAdapter implements AudioAdapter {
  private el?: HTMLAudioElement;
  private url?: string;

  private synth(): SpeechSynthesis | undefined {
    return typeof speechSynthesis !== 'undefined' ? speechSynthesis : undefined;
  }

  hasTTS(locale: string): boolean {
    const s = this.synth();
    if (!s) return false;
    const want = toBcp47(locale).toLowerCase();
    const lang = want.split('-')[0];
    // brx/mni map to a different language voice, so only claim support for exact language matches
    if (locale === 'brx' || locale === 'mni') return false;
    return s.getVoices().some((v) => v.lang.toLowerCase().startsWith(lang));
  }

  speakText(text: string, locale: string): Promise<void> {
    const s = this.synth();
    if (!s) return Promise.reject(new Error('SpeechSynthesis unavailable'));
    return new Promise((resolve) => {
      const u = new SpeechSynthesisUtterance(text);
      u.lang = toBcp47(locale);
      u.rate = 0.85; // slower for elders
      u.onend = () => resolve();
      u.onerror = () => resolve();
      s.speak(u);
    });
  }

  playBytes(bytes: ArrayBuffer, mime: string): Promise<void> {
    this.stop();
    return new Promise((resolve, reject) => {
      this.url = URL.createObjectURL(new Blob([bytes], { type: mime }));
      this.el = new Audio(this.url);
      this.el.onended = () => { this.cleanup(); resolve(); };
      this.el.onerror = () => { this.cleanup(); reject(new Error('audio playback failed')); };
      this.el.play().catch((e) => { this.cleanup(); reject(e); });
    });
  }

  private cleanup() { if (this.url) URL.revokeObjectURL(this.url); this.url = undefined; this.el = undefined; }

  stop(): void {
    this.synth()?.cancel();
    if (this.el) { this.el.pause(); this.cleanup(); }
  }
}

/** Push-to-talk recorder. Caller MUST have a mic ConsentRecord before calling start(). */
export class WebMicAdapter implements MicAdapter {
  private rec?: MediaRecorder;
  private chunks: Blob[] = [];
  private stream?: MediaStream;

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : '';
    this.rec = new MediaRecorder(this.stream, mime ? { mimeType: mime } : undefined);
    this.chunks = [];
    this.rec.ondataavailable = (e) => e.data.size && this.chunks.push(e.data);
    this.rec.start();
  }

  stop(): Promise<{ bytes: ArrayBuffer; mime: string }> {
    return new Promise((resolve, reject) => {
      if (!this.rec) return reject(new Error('not recording'));
      const rec = this.rec;
      rec.onstop = async () => {
        this.stream?.getTracks().forEach((t) => t.stop());
        const blob = new Blob(this.chunks, { type: rec.mimeType || 'audio/webm' });
        resolve({ bytes: await blob.arrayBuffer(), mime: blob.type });
      };
      rec.stop();
    });
  }
}

type SR = { lang: string; interimResults: boolean; maxAlternatives: number; onresult: ((e: any) => void) | null; onerror: (() => void) | null; onend: (() => void) | null; start(): void; stop(): void; abort(): void };

/** Web Speech API recognition. NOTE: Chrome's implementation sends audio to Google, so it is NOT offline or private;
 *  treat it as online-only convenience. True offline STT needs on-device models (see docs). */
export class WebSpeechSTT implements BrowserSTTAdapter {
  private rec?: SR;
  private ctor(): (new () => SR) | undefined {
    const w = globalThis as any;
    return w.SpeechRecognition ?? w.webkitSpeechRecognition;
  }
  available(locale: string): boolean {
    return !!this.ctor() && !(locale === 'brx' || locale === 'mni');
  }
  listenOnce(locale: string, maxMs: number): Promise<string> {
    const C = this.ctor();
    if (!C) return Promise.resolve('');
    return new Promise((resolve) => {
      const r = new C();
      this.rec = r;
      r.lang = toBcp47(locale);
      r.interimResults = false;
      r.maxAlternatives = 1;
      let done = false;
      const finish = (t: string) => { if (!done) { done = true; clearTimeout(timer); resolve(t); } };
      const timer = setTimeout(() => { r.stop(); finish(''); }, maxMs);
      r.onresult = (e) => finish(e.results?.[0]?.[0]?.transcript ?? '');
      r.onerror = () => finish('');
      r.onend = () => finish('');
      r.start();
    });
  }
  abort() { try { this.rec?.abort(); } catch { /* noop */ } }
}

export class WebNotificationAdapter implements NotificationAdapter {
  async notify(title: string, body: string, tag: string): Promise<void> {
    if (typeof Notification === 'undefined') return;
    if (Notification.permission === 'default') await Notification.requestPermission();
    if (Notification.permission !== 'granted') return;
    const reg = await navigator.serviceWorker?.getRegistration();
    if (reg) await reg.showNotification(title, { body, tag, requireInteraction: true });
    else new Notification(title, { body, tag });
  }
}
