import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { getSpeaker } from "../adapters/web/voice";
import { usePatientData } from "../state/PatientContext";
import { BigButton } from "./BigButton";

export function FullScreenReminderAlert() {
  const { t } = useTranslation();
  const { dueReminder, ackReminder } = usePatientData();
  const spokenFor = useRef<string | null>(null);

  useEffect(() => {
    if (dueReminder && spokenFor.current !== dueReminder.id) {
      spokenFor.current = dueReminder.id;
      void getSpeaker().speak(dueReminder.title, dueReminder.locale as never);
    }
  }, [dueReminder]);

  if (!dueReminder) return null;

  return (
    <div
      role="alertdialog"
      aria-modal="true"
      aria-label={dueReminder.title}
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-8 bg-bg p-6"
    >
      <p className="text-center text-3xl font-bold text-text">{dueReminder.title}</p>
      <div className="flex w-full max-w-sm flex-col gap-4">
        <BigButton variant="success" onClick={() => void ackReminder(dueReminder, "done")} className="text-2xl">
          {t("reminder.done")}
        </BigButton>
        <BigButton variant="surface" onClick={() => void ackReminder(dueReminder, "later")} className="text-2xl">
          {t("reminder.later")}
        </BigButton>
      </div>
    </div>
  );
}
