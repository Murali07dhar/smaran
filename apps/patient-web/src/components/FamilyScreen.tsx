import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { MediaAsset } from "@smaran/contracts";
import { getAppServices } from "../state/services";
import { useAuth } from "../state/AuthContext";
import { localMedia, refreshMediaList, ensureLocal } from "../core/media/mediaCache";
import { BigButton } from "./BigButton";

export function FamilyScreen() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { patient } = useAuth();
  const [media, setMedia] = useState<Array<{ media: MediaAsset; url?: string }>>([]);

  useEffect(() => {
    if (!patient) return;
    void (async () => {
      const { adapters, apiClient } = await getAppServices();
      setMedia(await localMedia(adapters.storage, adapters.file, patient.id)); // offline-first
      if (!navigator.onLine) return;
      try {
        const base = import.meta.env.VITE_API_BASE_URL || "/api/v1";
        const list = await refreshMediaList(apiClient, adapters.storage, patient.id);
        await Promise.all(list.map((m) => ensureLocal(apiClient, adapters.file, base, m)));
        setMedia(await localMedia(adapters.storage, adapters.file, patient.id));
      } catch {
        /* stay with the local copy */
      }
    })();
  }, [patient]);

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col gap-5 p-6">
      <h1 className="text-center text-2xl font-bold text-primary">{t("home.family")}</h1>
      <div className="grid grid-cols-2 gap-4">
        {media.map(({ media: m, url }) => (
          <div key={m.id} className="aspect-square rounded-token bg-surface shadow">
            {m.kind === "photo" && url && <img src={url} alt="" className="h-full w-full rounded-token object-cover" />}
          </div>
        ))}
      </div>
      <BigButton variant="accent" onClick={() => navigate("/coop")}>
        {t("coop.joinTitle")}
      </BigButton>
      <BigButton variant="surface" onClick={() => navigate("/home")}>
        {t("home.play")}
      </BigButton>
    </main>
  );
}
