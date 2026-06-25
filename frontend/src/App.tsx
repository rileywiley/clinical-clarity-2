import { Navigate, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "./api";
import AppShell from "./components/AppShell";
import Login from "./pages/Login";
import NetworkGrid from "./pages/NetworkGrid";
import ProjectionGrid from "./pages/ProjectionGrid";
import SiteChart from "./pages/SiteChart";
import SiteCalendar from "./pages/SiteCalendar";
import TrialDetail from "./pages/TrialDetail";
import TrialWizard from "./pages/TrialWizard";
import Metrics from "./pages/Metrics";
import AdminSettings from "./pages/AdminSettings";
import Onboarding from "./pages/Onboarding";
import Import from "./pages/Import";
import Studies from "./pages/Studies";

export default function App() {
  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    retry: (failureCount, err) => {
      if (err instanceof ApiError && err.status === 401) return false;
      return failureCount < 2;
    },
  });

  if (meQuery.isLoading) {
    return <div className="p-8 text-slate-500">Loading…</div>;
  }

  const isAuthed = !!meQuery.data;

  if (!isAuthed) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <AppShell me={meQuery.data!}>
      <Routes>
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="/" element={<NetworkGrid />} />
        <Route path="/studies" element={<Studies />} />
        <Route path="/projections" element={<ProjectionGrid />} />
        <Route path="/metrics" element={<Metrics />} />
        <Route path="/sites/:siteId" element={<SiteChart />} />
        <Route path="/sites/:siteId/calendar" element={<SiteCalendar />} />
        <Route path="/trials/new" element={<TrialWizard />} />
        <Route path="/trials/:trialId" element={<TrialDetail />} />
        <Route path="/admin/settings" element={<AdminSettings me={meQuery.data!} />} />
        <Route path="/onboarding" element={<Onboarding me={meQuery.data!} />} />
        <Route path="/import" element={<Import me={meQuery.data!} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
