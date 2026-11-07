import type { CoopTransport, CoopMessage, CoopOutgoing } from "@smaran/games";

/**
 * Talks to /ws/coop/{room_id}?token=<ws_token> per the CO-OP WEBSOCKET contract. The server is authoritative on
 * `seq`; the relay stamps and fans out. Uses the global WebSocket (web and React Native), no DOM-only APIs.
 * `wsBaseUrl` may be empty: the URL is then derived from the current origin (ws/wss, same host as the app).
 */
export function createCoopTransport(wsBaseUrl: string, getToken: () => Promise<string | null>): CoopTransport {
  let socket: WebSocket | null = null;
  const handlers = new Set<(m: CoopMessage) => void>();

  const base = () => {
    if (wsBaseUrl) return wsBaseUrl.replace(/\/$/, "");
    const loc = globalThis.location;
    return `${loc.protocol === "https:" ? "wss" : "ws"}://${loc.host}`;
  };

  return {
    async join(room_id: string) {
      const token = await getToken();
      const ws = new WebSocket(`${base()}/ws/coop/${room_id}?token=${encodeURIComponent(token ?? "")}`);
      socket = ws;
      await new Promise<void>((resolve, reject) => {
        ws.onopen = () => resolve();
        ws.onerror = () => reject(new Error("coop socket error"));
      });
      ws.onmessage = (ev) => {
        try {
          const parsed = JSON.parse(typeof ev.data === "string" ? ev.data : "") as CoopMessage;
          handlers.forEach((h) => h(parsed));
        } catch {
          /* ignore malformed frames */
        }
      };
      this.send({ type: "join", payload: {} });
    },
    leave() {
      if (socket) {
        try {
          socket.send(JSON.stringify({ type: "leave", seq: 0, payload: {} }));
        } catch {
          /* already closed */
        }
        socket.close();
      }
      socket = null;
    },
    send(msg: CoopOutgoing) {
      socket?.send(JSON.stringify({ seq: 0, ...msg }));
    },
    onMessage(cb) {
      handlers.add(cb);
      return () => void handlers.delete(cb);
    }
  };
}
