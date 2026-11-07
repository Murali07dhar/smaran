import type { Cue } from '../types';
/** Mock cue list. Assets live in packages/content/assets/cues (generated, CC0). Real cues come from caregiver uploads. */
export const mockCues: Cue[] = [
  { cue_id: 'cue-photo-tea-garden', cue_type: 'photo', uri: 'assets/cues/tea_garden.svg', label: 'Tea garden', valence_label: 'comfort' },
  { cue_id: 'cue-photo-family', cue_type: 'photo', uri: 'assets/cues/family.svg', label: 'Family together', valence_label: 'joy' },
  { cue_id: 'cue-audio-chime', cue_type: 'audio', uri: 'assets/cues/chime.wav', label: 'Temple bell chime', valence_label: 'familiarity' },
  { cue_id: 'cue-music-melody', cue_type: 'music', uri: 'assets/cues/melody.wav', label: 'Festival melody', valence_label: 'excitement' },
];
