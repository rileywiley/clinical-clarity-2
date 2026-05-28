import { Navigate, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "./api";
import Login from "./pages/Login";
import Home from "./pages/Home";
import ProjectionGrid from "./pages/ProjectionGrid";

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

  return (
    <Routes>
      <Route
        path="/login"
        element={isAuthed ? <Navigate to="/" replace /> : <Login />}
      />
      <Route
        path="/"
        element={
          isAuthed ? <Home me={meQuery.data!} /> : <Navigate to="/login" replace />
        }
      />
      <Route
        path="/projections"
        element={
          isAuthed ? <ProjectionGrid /> : <Navigate to="/login" replace />
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
