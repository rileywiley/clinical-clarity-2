import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, Me } from "../api";

export default function Home({ me }: { me: Me }) {
  const qc = useQueryClient();

  async function onLogout() {
    await api.logout();
    await qc.invalidateQueries({ queryKey: ["me"] });
  }

  return (
    <div className="mx-auto mt-12 max-w-2xl p-6">
      <h1 className="text-2xl font-semibold">Volume Forecasting Platform</h1>
      <p className="mt-2 text-slate-600">
        Phase 3 — projections &amp; actuals grid. The forecast network grid lands in Phase 4.
      </p>
      <nav className="mt-4 flex flex-wrap gap-3">
        <Link
          to="/projections"
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white"
        >
          Open projections grid
        </Link>
      </nav>
      <div className="mt-6 rounded border border-slate-200 bg-white p-4">
        <p>
          Signed in as <strong>{me.name}</strong> ({me.email}) —{" "}
          <span className="rounded bg-slate-100 px-2 py-0.5 text-sm">{me.role}</span>
        </p>
        <p className="mt-1 text-sm text-slate-500">
          Org: <code>{me.org_id}</code>
        </p>
        <button
          className="mt-4 rounded border border-slate-300 px-3 py-1.5 text-sm"
          onClick={onLogout}
        >
          Sign out
        </button>
      </div>
    </div>
  );
}
