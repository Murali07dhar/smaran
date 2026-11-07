import { uuid7, SyncQueue } from "@smaran/sync-core";
import type { StorageAdapter } from "../../adapters/types";
import { ApiClient } from "../api/client";
import { syncPush, syncPull } from "../api/endpoints";
import { createQueueStorage } from "./queueStorageAdapter";
import { createTokenStore } from "../auth/tokenStore";

const DEVICE_ID_KEY = "device_id";

export async function getOrCreateDeviceId(storage: StorageAdapter): Promise<string> {
  const existing = await storage.get<{ id: string; value: string }>("kv", DEVICE_ID_KEY);
  if (existing) return existing.value;
  const id = uuid7();
  await storage.put("kv", { id: DEVICE_ID_KEY, value: id });
  return id;
}

export interface SyncClientBundle {
  queue: SyncQueue;
  apiClient: ApiClient;
}

export async function createSyncClient(
  storage: StorageAdapter,
  apiBaseUrl: string,
  onStatusChange?: (status: "idle" | "syncing" | "offline" | "error") => void
): Promise<SyncClientBundle> {
  const tokenStore = createTokenStore(storage);
  const apiClient = new ApiClient({ baseUrl: apiBaseUrl, tokenStore });
  const device_id = await getOrCreateDeviceId(storage);

  const queue = new SyncQueue({
    device_id,
    storage: createQueueStorage(storage),
    push: (req) => syncPush(apiClient, req),
    pull: (since) => syncPull(apiClient, since),
    onStatusChange
  });

  return { queue, apiClient };
}
