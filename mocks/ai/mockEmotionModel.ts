// MOCK for Claude 2's emotion ONNX model (loaded via onnxruntime-web in the
// real build). Returns a plausible-looking fused emotion reading without any
// actual inference, so the on-device emotion capture hook has something to
// call offline. Replace the loadModel/infer pair with a real ONNX session at
// merge time — the call shape (EmotionFuseResponse) must not change without
// a CONTRACT CHANGE REQUEST.
import type { EmotionFuseResponse } from "@smaran/contracts";

export interface MockEmotionModel {
  ready: boolean;
  infer(frame: { imageData?: ImageData; audioChunk?: Float32Array }): Promise<EmotionFuseResponse>;
}

const LABELS: EmotionFuseResponse["label"][] = [
  "joy",
  "comfort",
  "excitement",
  "amusement",
  "familiarity",
  "neutral"
];

export async function loadMockEmotionModel(): Promise<MockEmotionModel> {
  // Real impl: await InferenceSession.create(modelUrl) from onnxruntime-web.
  return {
    ready: true,
    async infer() {
      const label = LABELS[Math.floor(Math.random() * LABELS.length)];
      return {
        valence: label === "neutral" ? 0 : 0.3 + Math.random() * 0.6,
        arousal: Math.random() * 0.6,
        label,
        confidence: 0.4 + Math.random() * 0.3
      };
    }
  };
}
