import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { Loading } from "./components/ui";
import AuthPage from "./pages/AuthPage";
import ProjectsPage from "./pages/ProjectsPage";
import ProjectLayout from "./pages/ProjectLayout";
import DashboardPage from "./pages/DashboardPage";
import BoardPage from "./pages/BoardPage";
import TeamPage from "./pages/TeamPage";
import AssistantPage from "./pages/AssistantPage";
import ModelPage from "./pages/ModelPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  const { user, ready } = useAuth();
  if (!ready) return <Loading label="Starting Foresight…" />;
  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/register" element={<AuthPage mode="register" />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }
  return (
    <Routes>
      <Route path="/" element={<ProjectsPage />} />
      <Route path="/p/:pid" element={<ProjectLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="board" element={<BoardPage />} />
        <Route path="team" element={<TeamPage />} />
        <Route path="assistant" element={<AssistantPage />} />
        <Route path="model" element={<ModelPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
