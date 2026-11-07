import type { MicAdapter } from "../types";

let stream: MediaStream | null = null;
let audioCtx: AudioContext | null = null;
let raf: number | null = null;

export const webMicAdapter: MicAdapter = {
  async requestPermission() {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      s.getTracks().forEach((t) => t.stop());
      return true;
    } catch {
      return false;
    }
  },
  async start(onLevel) {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    if (!onLevel) return;
    audioCtx = new AudioContext();
    const source = audioCtx.createMediaStreamSource(stream);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sumSquares = 0;
      for (const v of data) {
        const normalized = v / 128 - 1;
        sumSquares += normalized * normalized;
      }
      onLevel(Math.sqrt(sumSquares / data.length));
      raf = requestAnimationFrame(tick);
    };
    tick();
  },
  stop() {
    if (raf) cancelAnimationFrame(raf);
    raf = null;
    audioCtx?.close();
    audioCtx = null;
    stream?.getTracks().forEach((t) => t.stop());
    stream = null;
  }
};
