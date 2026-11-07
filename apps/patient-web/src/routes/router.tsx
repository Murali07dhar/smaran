import type { ReactElement } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { LoginScreen } from "../components/LoginScreen";
import { HomeScreen } from "../components/HomeScreen";
import { GameLauncher } from "../components/GameLauncher";
import { RemindersScreen } from "../components/RemindersScreen";
import { FamilyScreen } from "../components/FamilyScreen";
import { HelpScreen } from "../components/HelpScreen";
import { ConsentScreen } from "../components/ConsentScreen";
import { CoopJoinScreen } from "../components/CoopJoinScreen";
import { useAuth } from "../state/AuthContext";

function RequireAuth({ children }: { children: ReactElement }) {
  const { patient, loading } = useAuth();
  if (loading) return null;
  return patient ? children : <Navigate to="/login" replace />;
}

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginScreen />} />
      <Route
        path="/home"
        element={
          <RequireAuth>
            <HomeScreen />
          </RequireAuth>
        }
      />
      <Route
        path="/play"
        element={
          <RequireAuth>
            <GameLauncher />
          </RequireAuth>
        }
      />
      <Route
        path="/reminders"
        element={
          <RequireAuth>
            <RemindersScreen />
          </RequireAuth>
        }
      />
      <Route
        path="/family"
        element={
          <RequireAuth>
            <FamilyScreen />
          </RequireAuth>
        }
      />
      <Route
        path="/help"
        element={
          <RequireAuth>
            <HelpScreen />
          </RequireAuth>
        }
      />
      <Route
        path="/consent"
        element={
          <RequireAuth>
            <ConsentScreen />
          </RequireAuth>
        }
      />
      <Route
        path="/coop"
        element={
          <RequireAuth>
            <CoopJoinScreen />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/home" replace />} />
    </Routes>
  );
}
