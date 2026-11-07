// Fake services/voice on :8002 (zero dependencies). Canned audio + transcripts so other workstreams can integrate.
// Run: node mocks/voice/server.mjs   (PORT env to override)
// POST /voice/asr?locale=xx   -> cycles through canned transcripts (override with header x-mock-transcript)
// POST /voice/tts             -> returns a 300 ms beep WAV
// POST /voice/lid             -> {locale:'as'|'en'...}
// GET  /voice/health | /voice/capabilities
import { createServer } from 'node:http';

const PORT = Number(process.env.PORT ?? 8002);
const TRANSCRIPTS = ['yes', 'no', 'next', 'repeat', 'help', 'done'];
let i = 0;

function beepWav(ms = 300, freq = 440, rate = 16000) {
  const n = Math.floor((rate * ms) / 1000);
  const buf = Buffer.alloc(44 + n * 2);
  buf.write('RIFF', 0); buf.writeUInt32LE(36 + n * 2, 4); buf.write('WAVEfmt ', 8);
  buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(1, 22);
  buf.writeUInt32LE(rate, 24); buf.writeUInt32LE(rate * 2, 28); buf.writeUInt16LE(2, 32); buf.writeUInt16LE(16, 34);
  buf.write('data', 36); buf.writeUInt32LE(n * 2, 40);
  for (let k = 0; k < n; k++) buf.writeInt16LE(Math.round(9000 * Math.sin((2 * Math.PI * freq * k) / rate)), 44 + k * 2);
  return buf;
}

const json = (res, code, obj) => {
  res.writeHead(code, { 'content-type': 'application/json', 'access-control-allow-origin': '*', 'access-control-allow-headers': '*' });
  res.end(JSON.stringify(obj));
};

createServer((req, res) => {
  const url = new URL(req.url, 'http://x');
  if (req.method === 'OPTIONS') return json(res, 204, {});
  const chunks = [];
  req.on('data', (c) => chunks.push(c));
  req.on('end', () => {
    const body = Buffer.concat(chunks);
    if (url.pathname === '/voice/health') return json(res, 200, { status: 'ok', mock: true });
    if (url.pathname === '/voice/capabilities')
      return json(res, 200, { asr_locales: ['as', 'bn', 'ne', 'brx', 'mni', 'en'], tts_locales: ['as', 'bn', 'ne', 'brx', 'mni', 'en'], voice_pack_only_locales: ['lus', 'kha', 'grt'], mock: true });
    if (url.pathname === '/voice/asr' && req.method === 'POST') {
      const t = req.headers['x-mock-transcript'] ?? TRANSCRIPTS[i++ % TRANSCRIPTS.length];
      return json(res, 200, { transcript: String(t), locale: url.searchParams.get('locale'), engine: 'mock' });
    }
    if (url.pathname === '/voice/tts' && req.method === 'POST') {
      res.writeHead(200, { 'content-type': 'audio/wav', 'access-control-allow-origin': '*' });
      return res.end(beepWav());
    }
    if (url.pathname === '/voice/lid' && req.method === 'POST') {
      let text = ''; try { text = JSON.parse(body.toString()).text ?? ''; } catch {}
      return json(res, 200, { locale: /[\u0980-\u09FF]/.test(text) ? 'as' : 'en', confidence: 0.5, method: 'mock', ambiguous_with: [] });
    }
    res.writeHead(404, { 'content-type': 'application/problem+json' });
    res.end(JSON.stringify({ type: 'about:blank', title: 'Not found', status: 404 }));
  });
}).listen(PORT, () => console.log(`mock voice service on :${PORT}`));
