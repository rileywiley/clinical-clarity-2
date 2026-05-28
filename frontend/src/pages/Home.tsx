import { useQueryClient } from "@tanstack/react-query";
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
        Phase 0 placeholder. The real app starts in Phase 4 (network grid).
      </p>
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
