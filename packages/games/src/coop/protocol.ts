import type { CoopMessage, CoopOutgoing, Role } from '../types';

export interface Progress {
  round_index: number; rounds_total: number; prompt_key: string; prompt_params?: Record<string, string>;
  focus_item_id?: string | null; answer_item_id?: string | null; answer_label?: string | null;
  last_correct?: boolean | null; solved?: boolean; hints_used: number;
}
export const joinMsg = (from: Role, reply = false): CoopOutgoing => ({ type: 'join', payload: { from, reply } });
export const leaveMsg = (from: Role): CoopOutgoing => ({ type: 'leave', payload: { from } });
export const progressMsg = (from: Role, progress: Progress): CoopOutgoing => ({ type: 'state_patch', payload: { from, kind: 'progress', progress } });
export const picksMsg = (from: Role, item_ids: string[]): CoopOutgoing => ({ type: 'state_patch', payload: { from, kind: 'picks', item_ids } });
export const hintMsg = (from: Role, item_id: string): CoopOutgoing => ({ type: 'hint', payload: { from, item_id } });
export const encourageMsg = (from: Role, text_key: string): CoopOutgoing => ({ type: 'encourage', payload: { from, text_key } });
export const fromOf = (m: CoopMessage): Role | undefined => (m.payload.from === 'patient' || m.payload.from === 'family' ? m.payload.from : undefined);
