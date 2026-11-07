// Pure types. NO react/DOM imports. Shared by logic, UI and mocks.
export type Locale = 'as' | 'bn' | 'ne' | 'brx' | 'mni' | 'en' | 'lus' | 'kha' | 'grt';
export type Domain = 'memory' | 'attention' | 'routine' | 'pattern_object' | 'executive';
export type GameId =
  | 'memory_pairs' | 'image_grid' | 'target_tap' | 'spot_diff' | 'routine_order'
  | 'odd_one_out' | 'naming' | 'sorting' | 'arrange_steps' | 'routine_next';
export type EmotionLabel = 'joy' | 'comfort' | 'excitement' | 'amusement' | 'familiarity' | 'neutral' | 'negative';
export type Role = 'patient' | 'family';

export interface Patient { id: string; display_name?: string; age?: number; language?: string; estimated_stage?: string }

export type ContentKind = 'object' | 'photo' | 'step';
export interface ContentItem {
  id: string;
  kind: ContentKind;
  category: string;
  labels: Partial<Record<string, string>>; // locale -> label
  image?: string; // relative asset path, data: or https: URI
  icon?: string; // emoji fallback
  source: 'cc0' | 'placeholder' | 'caregiver';
  tags?: string[];
  routine_id?: string; // kind === 'step'
  step_order?: number; // kind === 'step'
}

export type CueType = 'photo' | 'audio' | 'music';
export interface Cue { cue_id: string; cue_type: CueType; uri: string; label?: string; valence_label?: EmotionLabel; item_id?: string }

export type GameEventType = 'item_shown' | 'answer' | 'hint_used' | 'cue_shown' | 'timeout' | 'reaction';
export interface GameEvent {
  event_id: string; session_id: string; type: GameEventType; item_id: string;
  correct?: boolean; response_ms?: number; cue_id?: string; with_cue: boolean; ts: string;
}

export interface CueArm { answers: number; correct: number }
export interface SessionSummary {
  session_id: string; game_id: GameId; difficulty: number; started_at: string; completed_at: string;
  items_total: number; answers: number; correct_answers: number; first_try_correct: number; hints_used: number;
  with_cue: CueArm; without_cue: CueArm; mean_response_ms: number | null;
  disclaimer_key: 'games.disclaimer'; // support tool, never a diagnosis
}

// Matches @smaran/voice-i18n core/types.ts VoiceAPI exactly (canonical owner: Claude 6).
// Kept as a structural duplicate here (not an import) so packages/games has no
// runtime/build dependency on voice-i18n; shapes must stay in sync by hand.
export type Intent = 'yes' | 'no' | 'next' | 'repeat' | 'help' | 'done' | 'unknown';
export interface ListenOpts {
  locale: string;
  maxMs?: number;
}
export interface ListenResult {
  transcript: string;
  intent: Intent;
}
export interface VoiceAPI {
  speak(keyOrText: string, locale: string): Promise<void>;
  listen(opts: ListenOpts): Promise<ListenResult>;
  playPack(pack_id: string, clip_id: string): Promise<void>;
  stop(): void;
}

export type CoopMessageType = 'join' | 'leave' | 'state_patch' | 'hint' | 'encourage';
export interface CoopMessage { type: CoopMessageType; seq: number; payload: Record<string, unknown> }
export interface CoopOutgoing { type: CoopMessageType; payload: Record<string, unknown>; seq?: number }
export interface CoopTransport {
  send(msg: CoopOutgoing): void;
  onMessage(cb: (m: CoopMessage) => void): () => void;
  join(room_id: string): void | Promise<void>;
  leave(): void;
}

export interface Observation { // feeds POST /ai/triggers/update (cue_id nullable: see HANDOFF CCR-2)
  cue_id: string | null; cue_type: CueType | null; valence_label: EmotionLabel; recalled: boolean; with_cue: boolean; ts: string;
}
