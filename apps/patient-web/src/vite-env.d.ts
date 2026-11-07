/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_VOICE_BASE_URL: string;
  readonly VITE_WS_BASE_URL: string;
  readonly VITE_USE_MOCKS: string;
  readonly VITE_EMOTION_MODEL_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
