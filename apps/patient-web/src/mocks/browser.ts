import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";

export const worker = setupWorker(...handlers);

export async function startMocksIfEnabled(): Promise<void> {
  if (import.meta.env.VITE_USE_MOCKS !== "true") return;
  await worker.start({ onUnhandledRequest: "bypass" });
}
