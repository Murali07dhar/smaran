import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { games, setAssetBase, type ContentItem, type Cue, type SessionSummary } from "@smaran/games";
import { bundledContent, caregiverPhotoItems, cuesFromLocalMedia } from "../core/games/gameInputs";
import { localMedia, refreshMediaList, ensureLocal } from "../core/media/mediaCache";
import { getOrCreateDeviceId } from "../core/sync/syncClient";
import { createSessionRecord, startSession, recordGameEvent, completeSession, type GameSession } from "../core/games/sessionLogic";
import { getActiveCoop } from "../core/coop/activeCoop";
import { createVoice } from "../adapters/web/voice";
import { createTokenStore } from "../core/auth/tokenStore";
import { useAuth } from "../state/AuthContext";
import { usePatientData } from "../state/PatientContext";
import { getAppServices } from "../state/services";
import { BigButton } from "./BigButton";

const DEFAULT_DIFFICULTY = 3; // services/ai /ai/difficulty/next drives this once sessions exist
setAssetBase("/");

/** D7: the REAL @smaran/games registry. Default = first memory game; `?game=<id>` is honoured. */
function pickGame(): (typeof games)[number] {
  const wanted = new URLSearchParams(window.location.search).get("game");
  return games.find((g) => g.id === wanted) ?? games.find((g) => g.domain === "memory") ?? games[0];
}

export function GameLauncher() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { patient } = useAuth();
  const { consent } = usePatientData();
  const [content, setContent] = useState<ContentItem[]>([]);
  const [cues, setCues] = useState<Cue[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [summary, setSummary] = useState<SessionSummary | null>(null);
  const [token, setToken] = useState<string | undefined>(undefined);

  const game = useMemo(pickGame, []);
  const micAllowed = consent?.mic === true;
  const voice = useMemo(
    () => createVoice({ micAllowed, serviceUrl: import.meta.env.VITE_VOICE_BASE_URL || "/api/v1/voice", token }),
    [micAllowed, token]
  );

  useEffect(() => {
    if (!patient) return;
    void (async () => {
      const { adapters, apiClient, queue } = await getAppServices();
      setToken((await createTokenStore(adapters.storage).getAccessToken()) ?? undefined);

      // Cues = caregiver media. Offline: whatever was cached on the last online visit.
      let rows = await localMedia(adapters.storage, adapters.file, patient.id);
      if (navigator.onLine) {
        try {
          const base = import.meta.env.VITE_API_BASE_URL || "/api/v1";
          const list = await refreshMediaList(apiClient, adapters.storage, patient.id);
          await Promise.all(list.map((m) => ensureLocal(apiClient, adapters.file, base, m)));
          rows = await localMedia(adapters.storage, adapters.file, patient.id);
        } catch {
          /* keep cached rows */
        }
      }
      setCues(cuesFromLocalMedia(rows));
      setContent([...bundledContent(), ...caregiverPhotoItems(rows)]);

      const deviceId = await getOrCreateDeviceId(adapters.storage);
      const session = createSessionRecord(patient.id, game.id, game.domain, DEFAULT_DIFFICULTY, deviceId);
      await startSession(adapters.storage, queue, session);
      setSessionId(session.id);
    })();
  }, [patient, game]);

  if (summary) {
    return (
      <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-6 p-6 text-center">
        <p className="text-2xl font-semibold text-success">{t("game.complete")}</p>
        <BigButton onClick={() => navigate("/home")}>{t("home.play")}</BigButton>
      </main>
    );
  }

  if (!sessionId || !patient) {
    return (
      <p role="status" className="p-6 text-base text-muted">
        …
      </p>
    );
  }

  const Component = game.Component;

  return (
    <main className="min-h-screen" data-testid="game-root" data-game={game.id}>
      <Component
        session_id={sessionId}
        // display_name = users.name (login response / GET /patients/{id}).
        patient={{ id: patient.id, display_name: patient.name, language: String(patient.language) }}
        content={content}
        cues={cues}
        difficulty={DEFAULT_DIFFICULTY}
        locale={String(patient.language)}
        role="patient"
        voice={voice}
        coop={game.supports_coop ? (getActiveCoop() ?? undefined) : undefined}
        onEvent={(event) => {
          void getAppServices().then(({ adapters, queue }) => recordGameEvent(adapters.storage, queue, event, patient.id));
        }}
        onComplete={(s) => {
          void getAppServices().then(async ({ adapters, queue }) => {
            const session = await adapters.storage.get<GameSession>("sessions", sessionId);
            if (session) await completeSession(adapters.storage, queue, session, s);
          });
          setSummary(s);
        }}
      />
    </main>
  );
}
