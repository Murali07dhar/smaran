import type { CameraAdapter } from "../types";

let stream: MediaStream | null = null;
let videoEl: HTMLVideoElement | null = null;

export const webCameraAdapter: CameraAdapter = {
  async requestPermission() {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: true });
      s.getTracks().forEach((t) => t.stop());
      return true;
    } catch {
      return false;
    }
  },
  async start() {
    stream = await navigator.mediaDevices.getUserMedia({ video: true });
    videoEl = document.createElement("video");
    videoEl.srcObject = stream;
    videoEl.muted = true;
    await videoEl.play();
  },
  async capturePhoto() {
    if (!videoEl) throw new Error("Camera not started");
    const canvas = document.createElement("canvas");
    canvas.width = videoEl.videoWidth;
    canvas.height = videoEl.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas unsupported");
    ctx.drawImage(videoEl, 0, 0);
    return new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("capture failed"))), "image/jpeg", 0.9);
    });
  },
  stop() {
    stream?.getTracks().forEach((t) => t.stop());
    stream = null;
    videoEl = null;
  }
};
