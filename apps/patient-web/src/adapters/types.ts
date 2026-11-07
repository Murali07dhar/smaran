// PORTABILITY: these are the six adapter interfaces named in the briefing.
// Everything under src/core must depend on these interfaces only — never on
// Dexie, the DOM Notification API, getUserMedia, etc. directly. The web
// implementations live in src/adapters/web/*; a future React Native build
// swaps in native implementations of the same interfaces unchanged.

export interface StorageAdapter {
  put<T extends object>(table: string, record: T): Promise<void>;
  bulkPut<T extends { id: string }>(table: string, records: T[]): Promise<void>;
  get<T>(table: string, id: string): Promise<T | undefined>;
  getAll<T>(table: string): Promise<T[]>;
  query<T>(table: string, predicate: (item: T) => boolean): Promise<T[]>;
  delete(table: string, id: string): Promise<void>;
  clear(table: string): Promise<void>;
}

export interface AudioAdapter {
  play(url: string): Promise<void>;
  stop(): void;
  isPlaying(): boolean;
}

export interface NotificationAdapter {
  requestPermission(): Promise<"granted" | "denied" | "default">;
  show(title: string, body: string, opts?: { tag?: string }): Promise<void>;
  /** Best-effort scheduled notification; web PWAs cannot guarantee firing in
   * the background, so callers must not rely on this alone — the in-app
   * full-screen alert (while foregrounded) is the reliable path. */
  schedule(at: Date, title: string, body: string, opts?: { tag?: string }): Promise<void>;
  cancel(tag: string): Promise<void>;
}

export interface CameraAdapter {
  requestPermission(): Promise<boolean>;
  start(): Promise<void>;
  capturePhoto(): Promise<Blob>;
  stop(): void;
}

export interface MicAdapter {
  requestPermission(): Promise<boolean>;
  start(onLevel?: (rms: number) => void): Promise<void>;
  stop(): void;
}

export interface FileAdapter {
  save(path: string, data: Blob): Promise<string>; // returns a local URL/URI
  read(path: string): Promise<Blob | undefined>;
  remove(path: string): Promise<void>;
  /** Displayable local URL for a saved file (object URL on web, file:// on native); undefined if absent. */
  url(path: string): Promise<string | undefined>;
}

export interface PlatformAdapters {
  storage: StorageAdapter;
  audio: AudioAdapter;
  notification: NotificationAdapter;
  camera: CameraAdapter;
  mic: MicAdapter;
  file: FileAdapter;
}
