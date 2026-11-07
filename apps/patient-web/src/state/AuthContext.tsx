import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { PatientView } from "@smaran/contracts";
import { loginWithPin, loginWithQr, type LoginResult } from "../core/auth/pinAuth";
import { createTokenStore } from "../core/auth/tokenStore";
import { getAppServices } from "./services";

interface AuthContextValue {
  patient: PatientView | null;
  loading: boolean;
  signInWithPin(pin: string): Promise<LoginResult>;
  signInWithQr(qrToken: string): Promise<LoginResult>;
  signOut(): Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const PATIENT_CACHE_KEY = "cached_patient_profile";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [patient, setPatient] = useState<PatientView | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      const { adapters } = await getAppServices();
      const cached = await adapters.storage.get<{ id: string; value: PatientView }>("kv", PATIENT_CACHE_KEY);
      if (cached) setPatient(cached.value);
      setLoading(false);
    })();
  }, []);

  const persistPatient = useCallback(async (p: PatientView) => {
    const { adapters } = await getAppServices();
    await adapters.storage.put("kv", { id: PATIENT_CACHE_KEY, value: p });
    setPatient(p);
  }, []);

  const signInWithPin = useCallback(async (pin: string) => {
    const { adapters, apiClient } = await getAppServices();
    const tokenStore = createTokenStore(adapters.storage);
    const result = await loginWithPin(apiClient, tokenStore, pin);
    if (result.ok) await persistPatient(result.patient);
    return result;
  }, [persistPatient]);

  const signInWithQr = useCallback(async (qrToken: string) => {
    const { adapters, apiClient } = await getAppServices();
    const tokenStore = createTokenStore(adapters.storage);
    const result = await loginWithQr(apiClient, tokenStore, qrToken);
    if (result.ok) await persistPatient(result.patient);
    return result;
  }, [persistPatient]);

  const signOut = useCallback(async () => {
    const { adapters } = await getAppServices();
    const tokenStore = createTokenStore(adapters.storage);
    await tokenStore.clear();
    await adapters.storage.delete("kv", PATIENT_CACHE_KEY);
    setPatient(null);
  }, []);

  const value = useMemo(
    () => ({ patient, loading, signInWithPin, signInWithQr, signOut }),
    [patient, loading, signInWithPin, signInWithQr, signOut]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
