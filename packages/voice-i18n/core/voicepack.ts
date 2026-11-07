// Recorded voice-pack format for locales without good TTS: lus (Mizo), kha (Khasi), grt (Garo).
// A pack = manifest.json + opus clips. Real recordings by native speakers only (no synthetic voices claimed as human).
import type { FileAdapter, PackOnlyLocale } from './types';

export interface PackClip {
  id: string;            // e.g. "greeting.morning", "reminder.medicine", "intent.yes"
  file: string;          // relative path inside the pack, e.g. "clips/reminder.medicine.opus"
  text: string;          // transcript (for on-screen display and review)
  duration_ms: number;
  sha256?: string;       // integrity (hex)
}

export interface PackManifest {
  schema: 1;
  pack_id: string;       // e.g. "lus-v1"
  locale: PackOnlyLocale;
  version: string;
  codec: 'opus';
  mime: 'audio/ogg; codecs=opus' | 'audio/webm; codecs=opus';
  speaker: { consent_recorded: boolean; credit?: string };
  license: 'CC0-1.0' | 'caregiver-owned' | 'CC-BY-4.0';
  verified_by_native_speaker: boolean;
  clips: PackClip[];
}

export const REQUIRED_CLIP_IDS = [
  'greeting.morning', 'greeting.evening', 'reminder.medicine', 'reminder.hydration',
  'reminder.activity', 'reminder.appointment', 'intent.yes', 'intent.no', 'encourage.good', 'prompt.listen_now',
];

export function validateManifest(m: unknown): { ok: true; manifest: PackManifest } | { ok: false; errors: string[] } {
  const errors: string[] = [];
  const x = m as Partial<PackManifest>;
  if (!x || typeof x !== 'object') return { ok: false, errors: ['manifest is not an object'] };
  if (x.schema !== 1) errors.push('schema must be 1');
  if (!x.pack_id) errors.push('pack_id missing');
  if (!x.locale || !['lus', 'kha', 'grt'].includes(x.locale)) errors.push('locale must be lus|kha|grt');
  if (x.codec !== 'opus') errors.push('codec must be opus');
  if (!x.speaker?.consent_recorded) errors.push('speaker.consent_recorded must be true');
  if (!x.license || !['CC0-1.0', 'caregiver-owned', 'CC-BY-4.0'].includes(x.license)) errors.push('license must be CC0-1.0, caregiver-owned or CC-BY-4.0');
  if (!Array.isArray(x.clips) || x.clips.length === 0) errors.push('clips empty');
  else {
    const ids = new Set<string>();
    for (const c of x.clips) {
      if (!c.id || !c.file) errors.push('clip missing id/file');
      if (c.file?.includes('..') || c.file?.startsWith('/')) errors.push(`unsafe path: ${c.file}`);
      if (ids.has(c.id)) errors.push(`duplicate clip id: ${c.id}`);
      ids.add(c.id);
    }
    for (const r of REQUIRED_CLIP_IDS) if (!ids.has(r)) errors.push(`missing required clip: ${r}`);
  }
  return errors.length ? { ok: false, errors } : { ok: true, manifest: x as PackManifest };
}

export async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const d = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(d)).map((b) => b.toString(16).padStart(2, '0')).join('');
}

export interface PackLoader {
  getClip(pack_id: string, clip_id: string): Promise<{ bytes: ArrayBuffer; mime: string; text: string } | null>;
}

/**
 * Loads packs from a FileAdapter (IndexedDB on web, filesystem later).
 * Install flow: fetch manifest + clips (online, once) -> installPack() -> works offline forever.
 */
export class VoicePackStore implements PackLoader {
  private manifests = new Map<string, PackManifest>();
  constructor(private files: FileAdapter, private verifyHash = true) {}

  private key(pack: string, rel: string) { return `voicepack/${pack}/${rel}`; }

  async installPack(manifest: unknown, readClip: (file: string) => Promise<ArrayBuffer>): Promise<{ ok: boolean; errors: string[] }> {
    const v = validateManifest(manifest);
    if (!v.ok) return { ok: false, errors: v.errors };
    const m = v.manifest;
    const errors: string[] = [];
    for (const clip of m.clips) {
      const bytes = await readClip(clip.file);
      if (this.verifyHash && clip.sha256 && (await sha256Hex(bytes)) !== clip.sha256) { errors.push(`hash mismatch: ${clip.id}`); continue; }
      await this.files.write(this.key(m.pack_id, clip.file), bytes);
    }
    if (errors.length) return { ok: false, errors };
    await this.files.write(this.key(m.pack_id, 'manifest.json'), new TextEncoder().encode(JSON.stringify(m)).buffer as ArrayBuffer);
    this.manifests.set(m.pack_id, m);
    return { ok: true, errors: [] };
  }

  async getManifest(pack_id: string): Promise<PackManifest | null> {
    const cached = this.manifests.get(pack_id);
    if (cached) return cached;
    const raw = await this.files.read(this.key(pack_id, 'manifest.json'));
    if (!raw) return null;
    const v = validateManifest(JSON.parse(new TextDecoder().decode(raw)));
    if (!v.ok) return null;
    this.manifests.set(pack_id, v.manifest);
    return v.manifest;
  }

  async getClip(pack_id: string, clip_id: string) {
    const m = await this.getManifest(pack_id);
    const clip = m?.clips.find((c) => c.id === clip_id);
    if (!m || !clip) return null;
    const bytes = await this.files.read(this.key(pack_id, clip.file));
    return bytes ? { bytes, mime: m.mime, text: clip.text } : null;
  }

  async installed(): Promise<string[]> {
    const keys = await this.files.list('voicepack/');
    return [...new Set(keys.map((k) => k.split('/')[1]))];
  }
}
