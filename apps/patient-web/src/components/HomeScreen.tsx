import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { BigButton } from "./BigButton";
import { useAuth } from "../state/AuthContext";

export function HomeScreen() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { patient } = useAuth();

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-5 p-6">
      {patient && (
        <p className="text-center text-base text-muted" aria-hidden="true">
          {new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
        </p>
      )}
      <BigButton variant="primary" onClick={() => navigate("/play")} className="text-2xl">
        {t("home.play")}
      </BigButton>
      <BigButton variant="accent" onClick={() => navigate("/reminders")} className="text-2xl">
        {t("home.reminders")}
      </BigButton>
      <BigButton variant="surface" onClick={() => navigate("/family")} className="text-2xl">
        {t("home.family")}
      </BigButton>
      <BigButton variant="surface" onClick={() => navigate("/help")} className="text-2xl">
        {t("home.help")}
      </BigButton>
    </main>
  );
}
