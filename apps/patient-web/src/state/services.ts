import { webAdapters } from "../adapters/web";
import { ApiClient } from "../core/api/client";
import { createTokenStore } from "../core/auth/tokenStore";
import { createSyncClient } from "../core/sync/syncClient";
import type { SyncQueue } from "@smaran/sync-core";

export interface AppServices {
  adapters: typeof webAdapters;
  apiClient: ApiClient;
  queue: SyncQueue;
}

let servicesPromise: Promise<AppServices> | null = null;

export function getAppServices(onSyncStatusChange?: (s: "idle" | "syncing" | "offline" | "error") => void): Promise<AppServices> {
  if (!servicesPromise) {
    servicesPromise = (async () => {
      const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "/api/v1";
      const tokenStore = createTokenStore(webAdapters.storage);
      const apiClient = new ApiClient({ baseUrl: apiBaseUrl, tokenStore });
      const { queue } = await createSyncClient(webAdapters.storage, apiBaseUrl, onSyncStatusChange);
      return { adapters: webAdapters, apiClient, queue };
    })();
  }
  return servicesPromise;
}
