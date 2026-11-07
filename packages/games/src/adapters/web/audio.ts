import type { AudioAdapter } from '../types';
export function createWebAudio(): AudioAdapter {
  let el: HTMLAudioElement | null = null;
  return {
    async play(uri) { try { el?.pause(); el = new Audio(uri); await el.play(); } catch { /* autoplay blocked or asset missing: cues degrade silently */ } },
    stop() { el?.pause(); el = null; },
  };
}
