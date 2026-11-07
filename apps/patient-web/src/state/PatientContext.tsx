import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { ReminderOut as Reminder } from "@smaran/contracts";
import { getReminders, getConsents } from "../core/api/endpoints";
import { consentFromRecords, type ConsentState } from "../core/validation/consent";
import { getDueReminder, recordReminderAck, recordMissedReminders, takeMissedEvents } from "../core/reminders/reminderState";
import { useAuth } from "./AuthContext";
import { getAppServices } from "./services";

interface PatientContextValue {
  reminders: Reminder[];
  consent: ConsentState | undefined;
  dueReminder: Reminder | null;
  setConsent(c: ConsentState): void;
  ackReminder(reminder: Reminder, status: "done" | "later"): Promise<void>;
}

const PatientContext = createContext<PatientContextValue | null>(null);
const REMINDERS_TABLE = "reminders";
const CONSENT_KV_KEY = "current_consent";

export function PatientProvider({ children }: { children: ReactNode }) {
  const { patient } = useAuth();
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [consent, setConsentState] = useState<ConsentState | undefined>(undefined);
  const [now, setNow] = useState(new Date());

  // Load cached reminders/consent immediately, then refresh from the API
  // when online (falls back silently to cache when offline).
  useEffect(() => {
    if (!patient) return;
    void (async () => {
      const { adapters, apiClient } = await getAppServices();
      const cachedReminders = await adapters.storage.getAll<Reminder>(REMINDERS_TABLE);
      setReminders(cachedReminders);
      const cachedConsent = await adapters.storage.get<{ id: string; value: ConsentState }>(
        "kv",
        CONSENT_KV_KEY
      );
      if (cachedConsent) setConsentState(cachedConsent.value);

      if (navigator.onLine) {
        try {
          const fresh = await getReminders(apiClient, patient.id);
          await adapters.storage.bulkPut(REMINDERS_TABLE, fresh);
          setReminders(fresh);
          const records = await getConsents(apiClient, patient.id); // caregiver may have granted/revoked
          const state = consentFromRecords(records);
          setConsentState(state);
          await adapters.storage.put("kv", { id: CONSENT_KV_KEY, value: state });
        } catch {
          // offline or API not reachable yet — cached data above already applied
        }
      }
    })();
  }, [patient]);

  // Tick once a minute so a due reminder's full-screen alert appears promptly.
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(id);
  }, []);

  const dueReminder = useMemo(() => getDueReminder(reminders, now), [reminders, now]);

  // Occurrences nobody acknowledged become `missed` reminder_events (synced; raises the caregiver alert).
  useEffect(() => {
    const missed = takeMissedEvents();
    if (!missed.length) return;
    void getAppServices().then(({ adapters, queue }) => recordMissedReminders(adapters.storage, queue, reminders, missed));
  }, [dueReminder, now, reminders]);

  const setConsent = (c: ConsentState) => {
    setConsentState(c);
    void getAppServices().then(({ adapters }) =>
      adapters.storage.put("kv", { id: CONSENT_KV_KEY, value: c })
    );
  };

  const ackReminder = async (reminder: Reminder, status: "done" | "later") => {
    const { adapters, queue } = await getAppServices();
    await recordReminderAck(adapters.storage, queue, reminder, status);
  };

  const value: PatientContextValue = { reminders, consent, dueReminder, setConsent, ackReminder };

  return <PatientContext.Provider value={value}>{children}</PatientContext.Provider>;
}

export function usePatientData(): PatientContextValue {
  const ctx = useContext(PatientContext);
  if (!ctx) throw new Error("usePatientData must be used within PatientProvider");
  return ctx;
}
