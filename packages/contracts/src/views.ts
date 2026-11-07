// Client-side views (not API wire shapes).
import type { Locale } from "./domain";

/** What patient-web knows about the logged-in patient (from login `user`). */
export interface PatientView {
  id: string;
  name: string;
  age?: number;
  language: Locale | string;
  estimated_stage?: string | number | null;
  notes?: string | null;
}

import type { Reminder } from "./domain";
/** Reminder as the API serialises it (GET/POST /patients/{id}/reminders, sync pull): RRULE under `schedule`. */
export type ReminderOut = Omit<Reminder, "schedule_rrule"> & { schedule: string };
