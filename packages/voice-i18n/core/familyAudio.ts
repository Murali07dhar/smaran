// Family voice playback: real recordings only, encrypted at rest on-device.
// Cipher is an adapter (WebCrypto AES-GCM on web, native keystore later). Per-device key lives in KeyStoreAdapter.
import type { AudioAdapter, FileAdapter, KeyValueAdapter, MicAdapter } from './types';

export interface CipherAdapter {
  /** Returns iv(12) || ciphertext+tag. */
  encrypt(plain: ArrayBuffer, aad: string): Promise<ArrayBuffer>;
  decrypt(blob: ArrayBuffer, aad: string): Promise<ArrayBuffer>;
}

export interface ClipMeta {
  clip_id: string;
  patient_id: string;
  label: string;          // e.g. "Daughter: take your medicine"
  recorded_by: string;    // caregiver user id
  recorded_at: string;    // ISO-8601 UTC
  mime: string;
  duration_ms?: number;
  consent_confirmed: true; // recorder confirms this is their real voice and the family agrees
}

const META_KEY = 'familyaudio/meta';

export class FamilyAudioStore {
  constructor(
    private files: FileAdapter,
    private meta: KeyValueAdapter,
    private cipher: CipherAdapter,
    private audio: AudioAdapter,
    private mic?: MicAdapter,
    private now: () => Date = () => new Date(),
    private newId: () => string = () => crypto.randomUUID(),
  ) {}

  private path(id: string) { return `familyaudio/${id}.enc`; }

  async list(patient_id?: string): Promise<ClipMeta[]> {
    const all = (await this.meta.get<ClipMeta[]>(META_KEY)) ?? [];
    return patient_id ? all.filter((c) => c.patient_id === patient_id) : all;
  }

  /** Store an existing recording (bytes) encrypted. */
  async save(bytes: ArrayBuffer, info: Omit<ClipMeta, 'clip_id' | 'recorded_at' | 'consent_confirmed'> & { consent_confirmed: boolean }): Promise<ClipMeta> {
    if (!info.consent_confirmed) throw new Error('Recorder must confirm this is their own real voice recording (consent).');
    const clip_id = this.newId();
    const meta: ClipMeta = { ...info, clip_id, recorded_at: this.now().toISOString(), consent_confirmed: true };
    const enc = await this.cipher.encrypt(bytes, clip_id);
    await this.files.write(this.path(clip_id), enc);
    const all = (await this.meta.get<ClipMeta[]>(META_KEY)) ?? [];
    await this.meta.set(META_KEY, [...all, meta]);
    return meta;
  }

  /** Record from mic: startRecording() ... stopAndSave(). Caller must have verified mic ConsentRecord. */
  async startRecording(): Promise<void> {
    if (!this.mic) throw new Error('No microphone adapter');
    await this.mic.start();
  }
  async stopAndSave(info: Omit<ClipMeta, 'clip_id' | 'recorded_at' | 'mime' | 'consent_confirmed'> & { consent_confirmed: boolean }): Promise<ClipMeta> {
    if (!this.mic) throw new Error('No microphone adapter');
    const { bytes, mime } = await this.mic.stop();
    return this.save(bytes, { ...info, mime });
  }

  async play(clip_id: string): Promise<boolean> {
    const all = (await this.meta.get<ClipMeta[]>(META_KEY)) ?? [];
    const m = all.find((c) => c.clip_id === clip_id);
    if (!m) return false;
    const enc = await this.files.read(this.path(clip_id));
    if (!enc) return false;
    try {
      const plain = await this.cipher.decrypt(enc, clip_id);
      await this.audio.playBytes(plain, m.mime);
      return true;
    } catch {
      return false; // tampered or wrong device key: caller falls back to TTS phrase
    }
  }

  async remove(clip_id: string): Promise<void> {
    await this.files.remove(this.path(clip_id));
    const all = (await this.meta.get<ClipMeta[]>(META_KEY)) ?? [];
    await this.meta.set(META_KEY, all.filter((c) => c.clip_id !== clip_id));
  }
}
