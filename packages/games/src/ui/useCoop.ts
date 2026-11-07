import { useCallback, useEffect, useRef, useState } from 'react';
import type { CoopTransport, Role } from '../types';
import { applyMessage, initialCoopState, type CoopViewState } from '../coop/state';
import { encourageMsg, fromOf, hintMsg, joinMsg, leaveMsg, picksMsg, progressMsg, type Progress } from '../coop/protocol';

export interface CoopApi {
  state: CoopViewState; connected: boolean;
  publish(p: Progress): void; sendHint(item_id: string): void; sendEncourage(text_key: string): void; sendPicks(ids: string[]): void;
}
/** Thin React wrapper over the pure co-op reducer + CoopTransport. Room id = session_id. */
export function useCoop(transport: CoopTransport | undefined, role: Role, room: string): CoopApi {
  const [state, setState] = useState<CoopViewState>(initialCoopState);
  const last = useRef<Progress | null>(null);
  useEffect(() => {
    if (!transport) return;
    const off = transport.onMessage((m) => {
      setState((s) => applyMessage(s, m, role));
      const from = fromOf(m);
      if (m.type === 'join' && from && from !== role && !m.payload.reply) {
        transport.send(joinMsg(role, true)); // announce ourselves to a late joiner (reply=true prevents loops)
        if (role === 'patient' && last.current) transport.send(progressMsg('patient', last.current));
      }
    });
    void Promise.resolve(transport.join(room)).then(() => {
      transport.send(joinMsg(role));
      if (role === 'patient' && last.current) transport.send(progressMsg('patient', last.current));
    });
    return () => { transport.send(leaveMsg(role)); off(); transport.leave(); };
  }, [transport, role, room]);
  const publish = useCallback((p: Progress) => { last.current = p; transport?.send(progressMsg(role, p)); }, [transport, role]);
  const sendHint = useCallback((id: string) => transport?.send(hintMsg(role, id)), [transport, role]);
  const sendEncourage = useCallback((k: string) => transport?.send(encourageMsg(role, k)), [transport, role]);
  const sendPicks = useCallback((ids: string[]) => { transport?.send(picksMsg(role, ids)); setState((s) => ({ ...s, picked_item_ids: ids })); }, [transport, role]);
  return { state, connected: !!transport, publish, sendHint, sendEncourage, sendPicks };
}
