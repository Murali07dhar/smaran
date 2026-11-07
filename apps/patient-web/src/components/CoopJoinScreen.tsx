import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { createCoopTransport } from "../core/coop/coopTransport";
import { joinCoopRoom } from "../core/api/endpoints";
import { setActiveCoop } from "../core/coop/activeCoop";
import { getAppServices } from "../state/services";
import { BigButton } from "./BigButton";

// KNOWN GAP (see HANDOFF.md): this connects to the co-op WebSocket and joins
// a room, but doesn't yet hand the resulting CoopTransport into GameLauncher
// — that wiring depends on Claude 4's co-op-capable game UI, which this
// patient-web build only has a mock (non-coop) game module for.
export function CoopJoinScreen() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [status, setStatus] = useState<"idle" | "joining" | "joined" | "error">("idle");

  async function join() {
    setStatus("joining");
    try {
      const { apiClient } = await getAppServices();
      // Join code -> ws_token (short-lived, room-scoped); the socket uses it, not the access token.
      const { room_id, ws_token } = await joinCoopRoom(apiClient, { join_code: code.trim(), role: "patient" });
      const transport = createCoopTransport(import.meta.env.VITE_WS_BASE_URL || "", async () => ws_token);
      await transport.join(room_id);
      setActiveCoop(transport);
      setStatus("joined");
      navigate("/play");
    } catch {
      setStatus("error");
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-6 p-6">
      <h1 className="text-2xl font-bold text-primary">{t("coop.joinTitle")}</h1>
      <input
        value={code}
        onChange={(e) => setCode(e.target.value)}
        placeholder={t("coop.enterCode") ?? ""}
        aria-label={t("coop.enterCode") ?? ""}
        className="min-h-touch w-full rounded-token border-2 border-primary bg-surface px-4 text-center text-2xl tracking-widest"
      />
      <BigButton variant="success" onClick={() => void join()} disabled={!code.trim() || status === "joining"}>
        {t("login.submit")}
      </BigButton>
      {status === "joined" && <p className="text-base text-success">✓</p>}
      {status === "error" && <p className="text-base text-attention">{t("login.networkError")}</p>}
      <BigButton variant="surface" onClick={() => navigate("/home")}>
        {t("home.play")}
      </BigButton>
    </main>
  );
}
