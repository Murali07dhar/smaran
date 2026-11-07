// PORTABILITY: uses only the global `fetch`, available on web and React
// Native alike — no `window`, `document`, or other DOM-only globals. Token
// storage is injected via TokenStore so this file never touches Dexie
// directly.

export interface TokenStore {
  getAccessToken(): Promise<string | null>;
  setTokens(access: string, refresh: string, expiresInSeconds: number): Promise<void>;
  clear(): Promise<void>;
}

export interface ApiClientConfig {
  baseUrl: string; // full API base incl. version prefix, e.g. /api/v1 (relative, via dev proxy / reverse proxy)
  tokenStore: TokenStore;
}

export class ApiError extends Error {
  constructor(public status: number, public title: string, public detail?: unknown) {
    super(`${status} ${title}`);
  }
}

export class ApiClient {
  constructor(private cfg: ApiClientConfig) {}

  private url(path: string): string {
    return `${this.cfg.baseUrl.replace(/\/$/, "")}${path}`;
  }

  async request<T>(
    path: string,
    init: { method?: string; body?: unknown; auth?: boolean } = {}
  ): Promise<T> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (init.auth !== false) {
      const token = await this.cfg.tokenStore.getAccessToken();
      if (token) headers.Authorization = `Bearer ${token}`;
    }
    const res = await fetch(this.url(path), {
      method: init.method ?? "GET",
      headers,
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined
    });
    if (!res.ok) {
      // RFC 7807 problem+json per the shared briefing's error convention.
      let problem: { title?: string; detail?: unknown } = {};
      try {
        problem = await res.json();
      } catch {
        /* non-JSON error body, ignore */
      }
      throw new ApiError(res.status, problem.title ?? res.statusText, problem.detail);
    }
    if (res.status === 204) return undefined as T;
    return res.json() as Promise<T>;
  }
}
