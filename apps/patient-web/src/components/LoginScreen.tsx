import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { BigButton } from "./BigButton";
import { useAuth } from "../state/AuthContext";
import tokens from "@smaran/design-tokens/tokens.json";

const DIGITS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", "OK"];

export function LoginScreen() {
  const { t } = useTranslation();
  const { signInWithPin } = useAuth();
  const navigate = useNavigate();
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(value: string) {
    setSubmitting(true);
    setError(null);
    const result = await signInWithPin(value);
    setSubmitting(false);
    if (result.ok) {
      navigate("/home");
    } else {
      setError(t(`login.${result.reason === "invalid_pin" ? "invalidPin" : result.reason === "unauthorized" ? "unauthorized" : "networkError"}`));
      setPin("");
    }
  }

  function press(key: string) {
    if (key === "⌫") return setPin((p) => p.slice(0, -1));
    if (key === "OK") return void submit(pin);
    if (pin.length < 6) setPin((p) => p + key);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-8 p-6">
      <header className="text-center">
        <h1 className="text-3xl font-bold text-primary">{t("login.title")}</h1>
        <p className="mt-1 text-base text-muted">{tokens.tagline}</p>
      </header>

      <label htmlFor="pin-display" className="text-base text-text">
        {t("login.enterPin")}
      </label>
      <div
        id="pin-display"
        aria-live="polite"
        className="flex min-h-touch w-full items-center justify-center rounded-token bg-surface text-3xl tracking-widest text-text shadow"
      >
        {pin ? "•".repeat(pin.length) : <span className="text-muted">{t("login.pinPlaceholder")}</span>}
      </div>

      {error && (
        <p role="alert" className="text-base font-semibold text-attention">
          {error}
        </p>
      )}

      <div className="grid w-full grid-cols-3 gap-3">
        {DIGITS.map((key) => (
          <BigButton
            key={key}
            variant={key === "OK" ? "success" : "surface"}
            onClick={() => press(key)}
            disabled={submitting}
            aria-label={key === "⌫" ? "Backspace" : key === "OK" ? t("login.submit") : key}
          >
            {key === "OK" ? t("login.submit") : key}
          </BigButton>
        ))}
      </div>
    </main>
  );
}
