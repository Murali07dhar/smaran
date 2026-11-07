import type { AudioAdapter } from '../adapters/types';
import { createWebAudio } from '../adapters/web/audio';
let audio: AudioAdapter | null = null;
export const setAudioAdapter = (a: AudioAdapter) => { audio = a; };
export const getAudio = (): AudioAdapter => audio ?? (audio = createWebAudio());
