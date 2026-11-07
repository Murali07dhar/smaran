import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { postConsent } from "../core/api/endpoints";
import { buildConsentRequests, consentFromRecords } from "../core/validation/consent";
import { setEmotionCaptureEnabled } from "../core/emotion/emotionCapture";
import { useAuth } from "../state/AuthContext";
import { usePatientData } from "../state/PatientContext";
import { getAppServices } from "../state/services";
import { BigButton } from "./BigButton";

export function ConsentScreen() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { patient } = useAuth();
  const { setConsent } = usePatientData();
  const [camera, setCamera] = useState(false);
  const [mic, setMic] = useState(false);
  const [needsOnline, setNeedsOnline] = useState(false);

  async function finish(dataSharing: boolean) {
    if (!patient) return;
    const { adapters, apiClient } = await getAppServices();
    const choices = { camera, mic, data_sharing: dataSharing };
    try {
      // Consent is online-only (not in the sync push list). One ConsentRecord per kind.
      const saved = [];
      for (const req of buildConsentRequests(choices)) saved.push(await postConsent(apiClient, patient.id, req));
      const state = consentFromRecords(saved);
      setConsent(state);
      await setEmotionCaptureEnabled(adapters.storage, state.camera || state.mic);
      navigate("/home");
    } catch {
      // Offline/unreachable: nothing is recorded, so camera and microphone stay OFF. Gentle, non-failure wording.
      setNeedsOnline(true);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 p-6">
      <h1 className="text-center text-2xl font-bold text-primary">{t("consent.title")}</h1>

      <label className="flex items-center justify-between gap-4 rounded-token bg-surface p-5 text-base text-text shadow">
        <span>{t("consent.camera")}</span>
        <input
          type="checkbox"
          className="h-8 w-8"
          checked={camera}
          onChange={(e) => setCamera(e.target.checked)}
          aria-label={t("consent.camera")}
        />
      </label>

      <label className="flex items-center justify-between gap-4 rounded-token bg-surface p-5 text-base text-text shadow">
        <span>{t("consent.mic")}</span>
        <input
          type="checkbox"
          className="h-8 w-8"
          checked={mic}
          onChange={(e) => setMic(e.target.checked)}
          aria-label={t("consent.mic")}
        />
      </label>

      <p className="text-base text-muted">{t("consent.disclaimer")}</p>
      {needsOnline && (
        <p role="status" className="text-base text-muted">
          {t("consent.needOnline")}
        </p>
      )}

      <div className="flex flex-col gap-3">
        <BigButton variant="success" onClick={() => void finish(true)}>
          {t("consent.agree")}
        </BigButton>
        <BigButton variant="surface" onClick={() => void finish(false)}>
          {t("consent.decline")}
        </BigButton>
      </div>
    </main>
  );
}
