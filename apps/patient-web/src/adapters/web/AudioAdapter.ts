import type { AudioAdapter } from "../types";

let current: HTMLAudioElement | null = null;

export const webAudioAdapter: AudioAdapter = {
  play(url) {
    return new Promise((resolve, reject) => {
      current?.pause();
      const audio = new Audio(url);
      current = audio;
      audio.onended = () => resolve();
      audio.onerror = () => reject(new Error(`Failed to play audio: ${url}`));
      void audio.play().catch(reject);
    });
  },
  stop() {
    current?.pause();
    current = null;
  },
  isPlaying() {
    return !!current && !current.paused;
  }
};
