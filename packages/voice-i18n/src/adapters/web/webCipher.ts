import type { CipherAdapter } from '../../../core/familyAudio';
import type { KeyValueAdapter } from '../../../core/types';

const KEY_NAME = 'familyaudio/device-key-v1';

/**
 * AES-256-GCM via WebCrypto. Per-device key generated once, stored as a NON-EXTRACTABLE CryptoKey in IndexedDB
 * (structured clone), so JS (and XSS) cannot read the raw key bytes. Limit: anyone with the unlocked browser
 * profile can still call decrypt; this protects data at rest on disk / in backups, not against a compromised session.
 * `kv` must be able to store CryptoKey objects (IndexedDB does; localStorage does not).
 */
export class WebCipher implements CipherAdapter {
  private key?: CryptoKey;
  constructor(private kv: KeyValueAdapter) {}

  private async getKey(): Promise<CryptoKey> {
    if (this.key) return this.key;
    let k = await this.kv.get<CryptoKey>(KEY_NAME);
    if (!k) {
      k = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
      await this.kv.set(KEY_NAME, k);
    }
    this.key = k;
    return k;
  }

  async encrypt(plain: ArrayBuffer, aad: string): Promise<ArrayBuffer> {
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv, additionalData: new TextEncoder().encode(aad) }, await this.getKey(), plain);
    const out = new Uint8Array(12 + ct.byteLength);
    out.set(iv, 0);
    out.set(new Uint8Array(ct), 12);
    return out.buffer;
  }

  async decrypt(blob: ArrayBuffer, aad: string): Promise<ArrayBuffer> {
    const u = new Uint8Array(blob);
    if (u.length < 29) throw new Error('ciphertext too short');
    return crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: u.slice(0, 12), additionalData: new TextEncoder().encode(aad) },
      await this.getKey(),
      u.slice(12),
    );
  }
}
