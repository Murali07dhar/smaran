import type { PatientView } from "@smaran/contracts";
import { ApiClient, ApiError } from "../api/client";
import { login, type LoginResponse } from "../api/endpoints";
import type { TokenStore } from "../api/client";

// Contract: 15 min access token (no expires_in in the login response).
const ACCESS_TTL_S = 900;

function patientFromLogin(res: LoginResponse): PatientView {
  return { id: res.user.id, name: res.user.name, language: res.user.language };
}

const PIN_PATTERN = /^\d{4,6}$/;

export function isValidPin(pin: string): boolean {
  return PIN_PATTERN.test(pin.trim());
}

export type LoginResult =
  | { ok: true; patient: PatientView }
  | { ok: false; reason: "invalid_pin" | "unauthorized" | "network" };

/**
 * Caregiver-issued PIN or QR login. The elder taps 4-6 big digit buttons (or
 * a caregiver scans a QR at setup time); either way this is the single entry
 * point the UI calls.
 */
export async function loginWithPin(
  client: ApiClient,
  tokenStore: TokenStore,
  pin: string
): Promise<LoginResult> {
  if (!isValidPin(pin)) return { ok: false, reason: "invalid_pin" };
  try {
    const res = await login(client, { pin });
    await tokenStore.setTokens(res.access_token, res.refresh_token, ACCESS_TTL_S);
    return { ok: true, patient: patientFromLogin(res) };
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return { ok: false, reason: "unauthorized" };
    return { ok: false, reason: "network" };
  }
}

export async function loginWithQr(
  client: ApiClient,
  tokenStore: TokenStore,
  qrToken: string
): Promise<LoginResult> {
  try {
    const res = await login(client, { qr_token: qrToken });
    await tokenStore.setTokens(res.access_token, res.refresh_token, ACCESS_TTL_S);
    return { ok: true, patient: patientFromLogin(res) };
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return { ok: false, reason: "unauthorized" };
    return { ok: false, reason: "network" };
  }
}
