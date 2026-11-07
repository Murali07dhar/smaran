import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { usePatientData } from "../state/PatientContext";
import { BigButton } from "./BigButton";

export function RemindersScreen() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { reminders } = usePatientData();

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col gap-5 p-6">
      <h1 className="text-center text-2xl font-bold text-primary">{t("home.reminders")}</h1>
      <ul className="flex flex-col gap-4">
        {reminders.map((r) => (
          <li key={r.id} className="rounded-token bg-surface p-5 text-base text-text shadow">
            {r.title}
          </li>
        ))}
        {reminders.length === 0 && <li className="text-center text-base text-muted">—</li>}
      </ul>
      <BigButton variant="surface" onClick={() => navigate("/home")}>
        {t("home.play")}
      </BigButton>
    </main>
  );
}
