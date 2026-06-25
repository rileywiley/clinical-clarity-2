/** Thin shell around every authed page: top bar with user + sign out. */

import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type Me } from "../api";

export default function AppShell({ me, children }: { me: Me; children: React.ReactNode }) {
  const qc = useQueryClient();
  async function onLogout() {
    await api.logout();
    await qc.invalidateQueries({ queryKey: ["me"] });
  }
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-2 text-sm">
          <div className="flex items-center gap-4">
            <Link to="/" className="font-semibold text-slate-800 hover:underline">
              Clinical Clarity
            </Link>
            <nav className="flex items-center gap-3 text-slate-500 no-print">
              <Link to="/" className="hover:underline">Network</Link>
              <Link
                to="/studies"
                className="hover:underline"
                data-testid="nav-studies"
              >
                Studies
              </Link>
              <Link to="/metrics" className="hover:underline">Metrics</Link>
              {me.role === "org_admin" && (
                <>
                  <Link
                    to="/admin/settings"
                    className="hover:underline"
                    data-testid="nav-admin-settings"
                  >
                    Admin
                  </Link>
                  <Link
                    to="/import"
                    className="hover:underline"
                    data-testid="nav-import"
                  >
                    Import
                  </Link>
                </>
              )}
            </nav>
          </div>
          <div className="flex items-center gap-3 text-slate-600">
            <span>
              {me.name} <span className="text-slate-400">({me.role})</span>
            </span>
            <button
              type="button"
              onClick={onLogout}
              className="rounded border border-slate-300 px-2 py-0.5 text-xs no-print"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
