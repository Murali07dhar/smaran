import type React from 'react';
import type { ContentItem, CoopTransport, Cue, Domain, GameEvent, GameId, Patient, Role, SessionSummary, VoiceAPI } from './types';

export interface GameProps {
  session_id: string; patient: Patient; content: ContentItem[]; cues: Cue[];
  difficulty: number; // 1..10
  locale: string; role: Role; voice: VoiceAPI;
  onEvent(e: GameEvent): void; onComplete(s: SessionSummary): void;
  coop?: CoopTransport;
}
export interface GameModule { id: GameId; domain: Domain; supports_coop: boolean; Component: React.FC<GameProps> }
