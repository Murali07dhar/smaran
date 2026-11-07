import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getAppServices } from "./services";

type SyncStatus = "idle" | "syncing" | "offline" | "error";

interface SyncContextValue {
  status: SyncStatus;
  online: boolean;
  syncNow(): Promise<void>;
}

const SyncContext = createContext<SyncContextValue | null>(null);

export function SyncProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SyncStatus>("idle");
  const [online, setOnline] = useState(typeof navigator !== "undefined" ? navigator.onLine : true);

  const syncNow = useMemo(
    () => async () => {
      if (!online) return;
      const { queue } = await getAppServices(setStatus);
      try {
        await queue.syncOnce();
      } catch {
        // SyncQueue already reports "error" via onStatusChange; pushPending's
        // own retry/backoff handles transient failures without surfacing here.
      }
    },
    [online]
  );

  useEffect(() => {
    const handleOnline = () => {
      setOnline(true);
      void syncNow();
    };
    const handleOffline = () => {
      setOnline(false);
      setStatus("offline");
    };
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    if (navigator.onLine) void syncNow();
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value = useMemo(() => ({ status, online, syncNow }), [status, online, syncNow]);

  return <SyncContext.Provider value={value}>{children}</SyncContext.Provider>;
}

export function useSync(): SyncContextValue {
  const ctx = useContext(SyncContext);
  if (!ctx) throw new Error("useSync must be used within SyncProvider");
  return ctx;
}
