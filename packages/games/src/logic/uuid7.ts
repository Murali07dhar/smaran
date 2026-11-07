type Filler = (b: Uint8Array) => void;
const g = globalThis as unknown as { crypto?: { getRandomValues(a: Uint8Array): Uint8Array } };
const defaultFill: Filler = (b) => {
  if (g.crypto && g.crypto.getRandomValues) g.crypto.getRandomValues(b);
  else for (let i = 0; i < b.length; i++) b[i] = Math.floor(Math.random() * 256);
};
/** RFC 9562 UUIDv7 (client-generated ids per SMARAN conventions). */
export function uuidv7(nowMs: number = Date.now(), fill: Filler = defaultFill): string {
  const b = new Uint8Array(16);
  fill(b);
  const hi = Math.floor(nowMs / 0x10000), lo = nowMs % 0x10000;
  b[0] = (hi >>> 24) & 255; b[1] = (hi >>> 16) & 255; b[2] = (hi >>> 8) & 255; b[3] = hi & 255;
  b[4] = (lo >>> 8) & 255; b[5] = lo & 255;
  b[6] = (b[6] & 0x0f) | 0x70; b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}
