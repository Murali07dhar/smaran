import type { CoopMessage, CoopOutgoing, CoopTransport } from '../types';

/** In-memory co-op bus. Mimics the server: authoritative per-room seq, fan-out to every member including the sender. */
export function createCoopBus() {
  const rooms = new Map<string, { seq: number; subs: Set<(m: CoopMessage) => void> }>();
  return {
    rooms,
    transport(): CoopTransport {
      let room: string | null = null;
      const listeners = new Set<(m: CoopMessage) => void>();
      const handler = (m: CoopMessage) => listeners.forEach((f) => f(m));
      return {
        join(id) { room = id; let r = rooms.get(id); if (!r) { r = { seq: 0, subs: new Set() }; rooms.set(id, r); } r.subs.add(handler); },
        leave() { if (room) rooms.get(room)?.subs.delete(handler); room = null; },
        send(msg: CoopOutgoing) {
          const r = room ? rooms.get(room) : undefined;
          if (!r) return;
          const full: CoopMessage = { type: msg.type, seq: ++r.seq, payload: msg.payload };
          Array.from(r.subs).forEach((s) => { Promise.resolve().then(() => s(full)); });
        },
        onMessage(cb) { listeners.add(cb); return () => { listeners.delete(cb); }; },
      };
    },
  };
}
