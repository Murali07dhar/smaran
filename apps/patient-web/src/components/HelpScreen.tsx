import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { BigButton } from "./BigButton";

export function HelpScreen() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-6 p-6 text-center">
      <h1 className="text-2xl font-bold text-primary">{t("help.title")}</h1>
      <p className="text-base text-text">{t("help.body")}</p>
      <BigButton variant="surface" onClick={() => navigate("/home")}>
        {t("home.play")}
      </BigButton>
    </main>
  );
}
