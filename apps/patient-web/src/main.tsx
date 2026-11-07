import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./i18n/i18n";
import "./styles/index.css";
import { startMocksIfEnabled } from "./mocks/browser";

async function bootstrap() {
  await startMocksIfEnabled();
  createRoot(document.getElementById("root") as HTMLElement).render(
    <StrictMode>
      <App />
    </StrictMode>
  );
}

void bootstrap();
