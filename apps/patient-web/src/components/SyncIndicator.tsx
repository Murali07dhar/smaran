import { useTranslation } from "react-i18next";
import { useSync } from "../state/SyncContext";

const DOT_COLOR: Record<string, string> = {
  idle: "bg-success",
  syncing: "bg-accent animate-pulse motion-reduce:animate-none",
  offline: "bg-muted",
  error: "bg-attention"
};

export function SyncIndicator() {
  const { status } = useSync();
  const { t } = useTranslation();
  const labelKey = `sync.${status}` as const;

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-3 right-3 flex items-center gap-2 rounded-token bg-surface/90 px-3 py-1.5 text-base text-muted shadow"
    >
      <span className={`h-2.5 w-2.5 rounded-full ${DOT_COLOR[status]}`} aria-hidden="true" />
      <span>{t(labelKey)}</span>
    </div>
  );
}
