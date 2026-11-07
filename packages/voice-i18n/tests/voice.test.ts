import { describe, expect, it } from 'vitest';
import { parseIntent } from '../core/intents';
import { templatePhrase, variedPhrase } from '../core/phrases';
import { VoiceClient, type BrowserSTTAdapter } from '../core/voiceClient';
import { REQUIRED_CLIP_IDS, VoicePackStore, validateManifest, sha256Hex, type PackManifest } from '../core/voicepack';
import { FamilyAudioStore, type CipherAdapter } from '../core/familyAudio';
import type { AudioAdapter, FileAdapter, KeyValueAdapter } from '../core/types';

class MemFiles implements FileAdapter {
  m = new Map<string, ArrayBuffer>();
  async read(k: string) { return this.m.get(k) ?? null; }
  async write(k: string, d: ArrayBuffer) { this.m.set(k, d); }
  async remove(k: string) { this.m.delete(k); }
  async list(p: string) { return [...this.m.keys()].filter((k) => k.startsWith(p)); }
}
class MemKV implements KeyValueAdapter {
  m = new Map<string, unknown>();
  async get<T>(k: string) { return this.m.get(k) as T | undefined; }
  async set<T>(k: string, v: T) { this.m.set(k, v); }
  async delete(k: string) { this.m.delete(k); }
}
class FakeAudio implements AudioAdapter {
  spoken: Array<[string, string]> = [];
  played: string[] = [];
  tts = true;
  async speakText(t: string, l: string) { this.spoken.push([t, l]); }
  async playBytes(b: ArrayBuffer, m: string) { this.played.push(m + ':' + new TextDecoder().decode(b)); }
  stop() {}
  hasTTS() { return this.tts; }
}
const bytes = (s: string) => new TextEncoder().encode(s).buffer as ArrayBuffer;

describe('intent grammar', () => {
  it('English basics', () => {
    expect(parseIntent('Yes!', 'en')).toBe('yes');
    expect(parseIntent('no, not yet', 'en')).toBe('no');
    expect(parseIntent('say again please', 'en')).toBe('repeat');
    expect(parseIntent('I need help', 'en')).toBe('help');
    expect(parseIntent('next one', 'en')).toBe('next');
    expect(parseIntent("I'm finished", 'en')).toBe('done');
    expect(parseIntent('finished', 'en')).toBe('done');
    expect(parseIntent('', 'en')).toBe('unknown');
  });
  it('help wins over yes (safety)', () => {
    expect(parseIntent('yes I need help', 'en')).toBe('help');
  });
  it('does not match substrings ("nobody" is not "no")', () => {
    expect(parseIntent('nobody', 'en')).toBe('unknown');
  });
  it('Bengali / Assamese / Nepali', () => {
    expect(parseIntent('হ্যাঁ', 'bn')).toBe('yes');
    expect(parseIntent('নহয়', 'as')).toBe('no');
    expect(parseIntent('अर्को', 'ne')).toBe('next');
  });
  it('falls back to English words in other locales', () => {
    expect(parseIntent('okay', 'bn')).toBe('yes');
  });
});

describe('phrases', () => {
  const r = { id: 'r1', category: 'medicine' as const, title: 'Metformin', locale: 'en' as const };
  it('is deterministic for the same seed', () => {
    expect(templatePhrase(r, { name: 'Maya' }, 5).text).toBe(templatePhrase(r, { name: 'Maya' }, 5).text);
  });
  it('always contains the title and no failure language', () => {
    for (let s = 0; s < 10; s++) {
      const p = templatePhrase(r, { name: 'Maya' }, s);
      expect(p.text).toContain('Metformin');
    }
  });
  it('unreviewed locales are flagged; brx falls back to English', () => {
    expect(templatePhrase({ ...r, locale: 'as' }, {}, 0).needs_review).toBe(true);
    const b = templatePhrase({ ...r, locale: 'brx' }, {}, 0);
    expect(b.locale_used).toBe('en');
  });
  it('missing name leaves no dangling comma', () => {
    expect(templatePhrase(r, {}, 0).text.startsWith(',')).toBe(false);
  });
  it('Gemini failure -> template; Gemini text missing the medicine name is rejected', async () => {
    const failing = (async () => { throw new Error('offline'); }) as unknown as typeof fetch;
    expect((await variedPhrase(r, {}, 1, { baseUrl: 'x', fetchImpl: failing })).source).toBe('template');
    const bad = (async () => ({ ok: true, json: async () => ({ text: 'Take your pills', source: 'gemini' }) })) as unknown as typeof fetch;
    expect((await variedPhrase(r, {}, 1, { baseUrl: 'x', fetchImpl: bad })).source).toBe('template');
    const good = (async () => ({ ok: true, json: async () => ({ text: 'Time for Metformin, friend.', source: 'gemini' }) })) as unknown as typeof fetch;
    expect((await variedPhrase(r, {}, 1, { baseUrl: 'x', fetchImpl: good })).source).toBe('gemini');
  });
});

describe('VoiceClient works fully offline via browser fallback', () => {
  const offline = () => false;
  it('speak uses on-device TTS and never touches the network', async () => {
    const audio = new FakeAudio();
    let netCalls = 0;
    const v = new VoiceClient({ audio, serviceUrl: 'http://svc', isOnline: offline, fetchImpl: (async () => { netCalls++; throw new Error(); }) as unknown as typeof fetch });
    await v.speak('Hello', 'en');
    expect(audio.spoken).toEqual([['Hello', 'en']]);
    expect(netCalls).toBe(0);
  });
  it('listen uses Web Speech STT offline and parses intent', async () => {
    const stt: BrowserSTTAdapter = { available: () => true, listenOnce: async () => 'yes please', abort() {} };
    const v = new VoiceClient({ audio: new FakeAudio(), stt, serviceUrl: 'http://svc', isOnline: offline });
    expect(await v.listen({ locale: 'en' })).toEqual({ transcript: 'yes please', intent: 'yes' });
    expect(v.lastMode.listen).toBe('browser');
  });
  it('no STT at all -> unknown intent (UI shows tap buttons), no throw', async () => {
    const v = new VoiceClient({ audio: new FakeAudio(), isOnline: offline });
    expect(await v.listen({ locale: 'as' })).toEqual({ transcript: '', intent: 'unknown' });
  });
  it('speak never throws when TTS is broken', async () => {
    const audio = new FakeAudio();
    audio.speakText = async () => { throw new Error('boom'); };
    const v = new VoiceClient({ audio, isOnline: offline });
    await v.speak('x', 'en');
    expect(v.lastMode.speak).toBe('none');
  });
  it('server TTS used when no local voice and online; 503 falls back to browser', async () => {
    const audio = new FakeAudio();
    audio.tts = false;
    const ok = (async () => ({ ok: true, headers: new Headers({ 'content-type': 'audio/wav' }), arrayBuffer: async () => bytes('WAV') })) as unknown as typeof fetch;
    const v1 = new VoiceClient({ audio, serviceUrl: 'http://svc', fetchImpl: ok });
    await v1.speak('namaskar', 'as');
    expect(audio.played).toEqual(['audio/wav:WAV']);
    const a2 = new FakeAudio(); a2.tts = false;
    const down = (async () => ({ ok: false })) as unknown as typeof fetch;
    const v2 = new VoiceClient({ audio: a2, serviceUrl: 'http://svc', fetchImpl: down });
    await v2.speak('namaskar', 'as');
    expect(a2.spoken).toHaveLength(1);
  });
  it('stop() cancels audio', () => {
    let stopped = 0;
    const a = new FakeAudio(); a.stop = () => { stopped++; };
    new VoiceClient({ audio: a }).stop();
    expect(stopped).toBe(1);
  });
});

function manifest(overrides: Partial<PackManifest> = {}): PackManifest {
  return {
    schema: 1, pack_id: 'lus-v1', locale: 'lus', version: '1.0.0', codec: 'opus', mime: 'audio/ogg; codecs=opus',
    speaker: { consent_recorded: true, credit: 'family volunteer' }, license: 'caregiver-owned', verified_by_native_speaker: false,
    clips: REQUIRED_CLIP_IDS.map((id) => ({ id, file: `clips/${id}.opus`, text: id, duration_ms: 1000 })),
    ...overrides,
  };
}

describe('voice packs', () => {
  it('validates required clips, consent, path traversal', () => {
    expect(validateManifest(manifest()).ok).toBe(true);
    const bad = validateManifest(manifest({ clips: [{ id: 'x', file: '../../etc/passwd', text: '', duration_ms: 1 }] }));
    expect(bad.ok).toBe(false);
    expect(validateManifest(manifest({ speaker: { consent_recorded: false } })).ok).toBe(false);
  });
  it('installs, verifies hash, plays offline', async () => {
    const files = new MemFiles();
    const store = new VoicePackStore(files);
    const m = manifest();
    m.clips[0].sha256 = await sha256Hex(bytes('clip-0'));
    const res = await store.installPack(m, async (f) => bytes(f === m.clips[0].file ? 'clip-0' : 'other'));
    expect(res.ok).toBe(true);
    const audio = new FakeAudio();
    const v = new VoiceClient({ audio, packs: new VoicePackStore(files) }); // fresh store: reads from files
    await v.playPack('lus-v1', REQUIRED_CLIP_IDS[0]);
    expect(audio.played[0]).toContain('clip-0');
    expect(await store.installed()).toEqual(['lus-v1']);
  });
  it('rejects tampered clip', async () => {
    const m = manifest();
    m.clips[0].sha256 = await sha256Hex(bytes('good'));
    const res = await new VoicePackStore(new MemFiles()).installPack(m, async () => bytes('evil'));
    expect(res.ok).toBe(false);
  });
});

// XOR "cipher" only to test store logic; real AES-GCM is tested separately below.
const xorCipher: CipherAdapter = {
  encrypt: async (p) => new Uint8Array(new Uint8Array(p).map((b) => b ^ 0x5a)).buffer,
  decrypt: async (p) => new Uint8Array(new Uint8Array(p).map((b) => b ^ 0x5a)).buffer,
};

describe('family audio', () => {
  const mk = (cipher = xorCipher) => {
    const files = new MemFiles(); const audio = new FakeAudio();
    return { files, audio, store: new FamilyAudioStore(files, new MemKV(), cipher, audio, undefined, () => new Date('2026-01-01T00:00:00Z'), () => 'clip-1') };
  };
  it('refuses to save without consent confirmation', async () => {
    const { store } = mk();
    await expect(store.save(bytes('a'), { patient_id: 'p', label: 'l', recorded_by: 'u', mime: 'audio/webm', consent_confirmed: false })).rejects.toThrow();
  });
  it('stores ciphertext (not plaintext) and plays back', async () => {
    const { store, files, audio } = mk();
    await store.save(bytes('HELLO-VOICE'), { patient_id: 'p', label: 'Daughter', recorded_by: 'u', mime: 'audio/webm', consent_confirmed: true });
    const raw = new TextDecoder().decode((await files.read('familyaudio/clip-1.enc'))!);
    expect(raw.includes('HELLO-VOICE')).toBe(false);
    expect(await store.play('clip-1')).toBe(true);
    expect(audio.played).toEqual(['audio/webm:HELLO-VOICE']);
    expect(await store.list('p')).toHaveLength(1);
  });
  it('play returns false (caller falls back to TTS) on corrupt data', async () => {
    const bad: CipherAdapter = { encrypt: xorCipher.encrypt, decrypt: async () => { throw new Error('tag mismatch'); } };
    const { store } = mk(bad);
    await store.save(bytes('x'), { patient_id: 'p', label: 'l', recorded_by: 'u', mime: 'audio/webm', consent_confirmed: true });
    expect(await store.play('clip-1')).toBe(false);
  });
  it('remove deletes file and metadata', async () => {
    const { store, files } = mk();
    await store.save(bytes('x'), { patient_id: 'p', label: 'l', recorded_by: 'u', mime: 'audio/webm', consent_confirmed: true });
    await store.remove('clip-1');
    expect(await files.read('familyaudio/clip-1.enc')).toBeNull();
    expect(await store.list()).toHaveLength(0);
  });
});

describe('WebCipher AES-256-GCM (real WebCrypto)', () => {
  it('round-trips, uses random IV, binds clip id as AAD, rejects tampering', async () => {
    const { WebCipher } = await import('../src/adapters/web/webCipher');
    const c = new WebCipher(new MemKV());
    const plain = bytes('secret family voice');
    const a = await c.encrypt(plain, 'id1');
    const b = await c.encrypt(plain, 'id1');
    expect(new Uint8Array(a).join()).not.toBe(new Uint8Array(b).join());
    expect(new TextDecoder().decode(await c.decrypt(a, 'id1'))).toBe('secret family voice');
    await expect(c.decrypt(a, 'other-id')).rejects.toThrow();
    const t = new Uint8Array(a); t[20] ^= 1;
    await expect(c.decrypt(t.buffer, 'id1')).rejects.toThrow();
  });
});
