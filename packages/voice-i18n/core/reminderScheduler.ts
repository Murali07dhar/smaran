// Glue: periodic tick -> engine -> speak/notify + outbox of caregiver alerts (synced later via sync-core).
// No DOM. Host provides timers (setInterval on web; background task on native).
import type { EngineEvent, EngineState } from './reminderEngine';
import { ReminderEngine } from './reminderEngine';
import { templatePhrase, variedPhrase, type GeminiClientOpts } from './phrases';
import type { KeyValueAdapter, NotificationAdapter, Reminder, VoiceAPI } from './types';
import type { FamilyAudioStore } from './familyAudio';

export interface AlertOutboxItem {
  op_id: string;            // idempotency key for sync push
  type: 'reminder_escalation';
  patient_id: string;
  reminder_id: string;
  category: Reminder['category'];
  title: string;
  consecutive_misses: number;
  due_ts: number;
  created_at: string;
}

export interface SchedulerDeps {
  engine: ReminderEngine;
  kv: KeyValueAdapter;
  voice?: VoiceAPI;
  notify?: NotificationAdapter;
  family?: FamilyAudioStore;
  patientName?: () => string | undefined;
  gemini?: () => GeminiClientOpts | undefined;
  now?: () => number;
  newId?: () => string;
  onEvent?: (e: EngineEvent) => void;
  autoSpeak?: boolean;
}

const STATE_KEY = 'reminders/engine-state';
const OUTBOX_KEY = 'reminders/alert-outbox';

export class ReminderScheduler {
  private timer: ReturnType<typeof setInterval> | undefined;
  private reminders = new Map<string, Reminder>();
  constructor(private d: SchedulerDeps) {}

  private now() { return (this.d.now ?? Date.now)(); }

  static async restoreState(kv: KeyValueAdapter): Promise<EngineState> {
    return (await kv.get<EngineState>(STATE_KEY)) ?? {};
  }

  setReminders(list: Reminder[]) {
    const ids = new Set(list.map((r) => r.id));
    for (const id of this.reminders.keys()) if (!ids.has(id)) { this.d.engine.remove(id); this.reminders.delete(id); }
    for (const r of list) { this.reminders.set(r.id, r); this.d.engine.upsert(r, this.now()); }
  }

  start(intervalMs = 15_000) {
    this.stop();
    void this.tick();
    this.timer = setInterval(() => void this.tick(), intervalMs);
  }
  stop() { if (this.timer) clearInterval(this.timer); this.timer = undefined; }

  /** Call also on app resume / visibilitychange: this is the offline catch-up path. */
  async tick(): Promise<EngineEvent[]> {
    const events = this.d.engine.tick(this.now());
    for (const e of events) {
      this.d.onEvent?.(e);
      if (e.type === 'due') await this.announce(e.reminder_id, e.due_ts, e.snoozed);
      if (e.type === 'escalation') await this.enqueueAlert(e);
    }
    await this.d.kv.set(STATE_KEY, this.d.engine.getState());
    return events;
  }

  private async announce(reminderId: string, dueTs: number, snoozed: boolean) {
    const r = this.reminders.get(reminderId);
    if (!r) return;
    const name = this.d.patientName?.();
    const seed = Math.floor(dueTs / 86_400_000);
    const phrase = await variedPhrase(r, { name }, seed, this.d.gemini?.());
    try { await this.d.notify?.notify(r.title, phrase.text, `${reminderId}:${dueTs}`); } catch { /* ignore */ }
    if (this.d.autoSpeak === false || !this.d.voice) return;
    // Prefer a real family recording if the caregiver attached one, else the spoken phrase.
    if (r.voice_clip_id && this.d.family && !snoozed && (await this.d.family.play(r.voice_clip_id))) return;
    await this.d.voice.speak(phrase.text, phrase.locale_used);
  }

  private async enqueueAlert(e: Extract<EngineEvent, { type: 'escalation' }>) {
    const box = (await this.d.kv.get<AlertOutboxItem[]>(OUTBOX_KEY)) ?? [];
    const op_id = `esc:${e.reminder_id}:${e.due_ts}`; // deterministic => idempotent
    if (box.some((b) => b.op_id === op_id)) return;
    box.push({
      op_id, type: 'reminder_escalation', patient_id: e.patient_id, reminder_id: e.reminder_id,
      category: e.category, title: e.title, consecutive_misses: e.consecutive_misses, due_ts: e.due_ts,
      created_at: new Date(e.at).toISOString(),
    });
    await this.d.kv.set(OUTBOX_KEY, box);
  }

  async acknowledge(reminderId: string, dueTs: number) {
    const ev = this.d.engine.acknowledge(reminderId, dueTs, this.now());
    if (ev) this.d.onEvent?.(ev);
    await this.d.kv.set(STATE_KEY, this.d.engine.getState());
    return ev;
  }

  async snooze(reminderId: string, dueTs: number, minutes?: number) {
    const at = this.d.engine.snooze(reminderId, dueTs, this.now(), minutes);
    await this.d.kv.set(STATE_KEY, this.d.engine.getState());
    return at;
  }

  /** sync-core drains this and POSTs each as an Alert via /sync/push; call ackOutbox with the accepted op_ids. */
  async outbox(): Promise<AlertOutboxItem[]> { return (await this.d.kv.get<AlertOutboxItem[]>(OUTBOX_KEY)) ?? []; }
  async ackOutbox(opIds: string[]) {
    const box = (await this.outbox()).filter((b) => !opIds.includes(b.op_id));
    await this.d.kv.set(OUTBOX_KEY, box);
  }

  /** Fallback phrase without any network/AI. */
  phraseFor(r: Reminder) { return templatePhrase(r, { name: this.d.patientName?.() }, Math.floor(this.now() / 86_400_000)); }
}
