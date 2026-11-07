// Framework-agnostic types. NO react/DOM imports.

export type Locale = 'as' | 'bn' | 'ne' | 'brx' | 'mni' | 'en';
export type PackOnlyLocale = 'lus' | 'kha' | 'grt';
export type AnyLocale = Locale | PackOnlyLocale;

export const LOCALES: Locale[] = ['as', 'bn', 'ne', 'brx', 'mni', 'en'];
export const PACK_ONLY_LOCALES: PackOnlyLocale[] = ['lus', 'kha', 'grt'];

export type Intent = 'yes' | 'no' | 'next' | 'repeat' | 'help' | 'done' | 'unknown';

export interface ListenOpts {
  locale: AnyLocale;
  maxMs?: number;
}
export interface ListenResult {
  transcript: string;
  intent: Intent;
}

export interface VoiceAPI {
  speak(keyOrText: string, locale: AnyLocale): Promise<void>;
  listen(opts: ListenOpts): Promise<ListenResult>;
  playPack(pack_id: string, clip_id: string): Promise<void>;
  stop(): void;
}

export type ReminderCategory = 'medicine' | 'hydration' | 'activity' | 'appointment';

export interface Reminder {
  id: string;
  patient_id: string;
  category: ReminderCategory;
  title: string;
  schedule: string; // RRULE, optionally prefixed by DTSTART / TZID lines
  locale: AnyLocale;
  voice_clip_id?: string;
  escalate_after_misses: number;
}

// Adapter interfaces (web impl in src/adapters/web)
export interface AudioAdapter {
  speakText(text: string, locale: string): Promise<void>;
  playBytes(bytes: ArrayBuffer, mime: string): Promise<void>;
  stop(): void;
  hasTTS(locale: string): boolean;
}
export interface MicAdapter {
  /** Push-to-talk: start() begins capture, stop() resolves with audio blob bytes. */
  start(): Promise<void>;
  stop(): Promise<{ bytes: ArrayBuffer; mime: string }>;
}
export interface NotificationAdapter {
  notify(title: string, body: string, tag: string): Promise<void>;
}
export interface FileAdapter {
  read(key: string): Promise<ArrayBuffer | null>;
  write(key: string, data: ArrayBuffer): Promise<void>;
  remove(key: string): Promise<void>;
  list(prefix: string): Promise<string[]>;
}
export interface KeyValueAdapter {
  get<T>(key: string): Promise<T | undefined>;
  set<T>(key: string, value: T): Promise<void>;
  delete(key: string): Promise<void>;
}
