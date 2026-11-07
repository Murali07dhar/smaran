import type { StorageAdapter } from "../../adapters/types";
import type { TokenStore } from "../api/client";

const KV_TABLE = "kv";
const KEY = "auth_tokens";

interface StoredTokens {
  id: string;
  value: { access_token: string; refresh_token: string; expires_at: string };
}

export function createTokenStore(storage: StorageAdapter): TokenStore {
  return {
    async getAccessToken() {
      const row = await storage.get<StoredTokens>(KV_TABLE, KEY);
      if (!row) return null;
      if (new Date(row.value.expires_at) <= new Date()) return null; // expired, caller should re-login
      return row.value.access_token;
    },
    async setTokens(access, refresh, expiresInSeconds) {
      const expires_at = new Date(Date.now() + expiresInSeconds * 1000).toISOString();
      await storage.put<StoredTokens>(KV_TABLE, {
        id: KEY,
        value: { access_token: access, refresh_token: refresh, expires_at }
      });
    },
    async clear() {
      await storage.delete(KV_TABLE, KEY);
    }
  };
}
