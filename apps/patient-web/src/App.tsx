import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "./state/AuthContext";
import { SyncProvider } from "./state/SyncContext";
import { PatientProvider } from "./state/PatientContext";
import { AppRouter } from "./routes/router";
import { FullScreenReminderAlert } from "./components/FullScreenReminderAlert";
import { SyncIndicator } from "./components/SyncIndicator";

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <SyncProvider>
          <PatientProvider>
            <AppRouter />
            <FullScreenReminderAlert />
            <SyncIndicator />
          </PatientProvider>
        </SyncProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
