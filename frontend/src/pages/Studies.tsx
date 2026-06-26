/**
 * Studies dashboard (post-Phase-6).
 *
 * One row per trial, grouped by status (Active, then Planned, then Draft,
 * then Archived). Planned = future pipeline (PRD §6.9). Click a row to open
 * the existing /trials/:id detail page.
 * Visible to every role — viewers see the dashboard but lose the
 * editing affordances on the detail page.
 */

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type TrialOut, type TrialStatus } from "../api";
import { TrialColorBadge } from "../components/TrialColorBadge";
import { TrialStatusActions } from "../components/TrialStatusActions";
import { EmptyState } from "../components/EmptyState";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { fmtCount } from "../lib/formatters";

const STATUS_ORDER: TrialStatus[] = ["active", "planned", "draft", "archived"];
const STATUS_LABEL: Record<TrialStatus, string> = {
  active: "Active",
  planned: "Planned",
  draft: "Draft",
  archived: "Archived",
};

export default function Studies() {
  useDocumentTitle("Studies");

  const trialsQ = useQuery({ queryKey: ["trials"], queryFn: api.listTrials });
  const sitesQ = useQuery({ queryKey: ["sites"], queryFn: api.listSites });

  const trials = trialsQ.data ?? [];

  // For per-trial site counts we'd need a fan-out call per trial; instead
  // use the inverse view if we can. The existing endpoint we have is
  // /trials/:id/sites — fan-out is fine here because the dashboard is
  // typically small. TanStack Query will dedupe + cache.
  const grouped = useMemo(() => {
    const m: Record<TrialStatus, TrialOut[]> = {
      active: [],
      planned: [],
      draft: [],
      archived: [],
    };
    for (const t of trials) {
      const s = (t.status as TrialStatus) ?? "draft";
      (m[s] ?? m.draft).push(t);
    }
    for (const s of STATUS_ORDER) {
      m[s].sort((a, b) => a.name.localeCompare(b.name));
    }
    return m;
  }, [trials]);

  if (trialsQ.isLoading || sitesQ.isLoading) {
    return <div className="p-8 text-slate-500">Loading…</div>;
  }

  return (
    <div className="mx-auto max-w-7xl p-6">
      <header className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Studies</h1>
        <Link
          to="/trials/new"
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white"
          data-testid="studies-new-trial"
        >
          + New trial
        </Link>
      </header>

      {trials.length === 0 && (
        <EmptyState
          title="No studies yet"
          body="Create a trial through the wizard to see it here."
          action={
            <Link
              to="/trials/new"
              className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white"
            >
              Open trial setup
            </Link>
          }
        />
      )}

      {STATUS_ORDER.map((s) =>
        grouped[s].length === 0 ? null : (
          <section key={s} className="mb-6">
            <h2 className="mb-2 text-sm font-medium text-slate-700">
              {STATUS_LABEL[s]}{" "}
              <span className="ml-1 text-slate-500">({grouped[s].length})</span>
            </h2>
            <div className="overflow-x-auto rounded border border-slate-200 bg-white">
              <table className="w-full text-sm" data-testid={`studies-${s}-table`}>
                <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-600">
                  <tr>
                    <th className="px-3 py-2">Trial</th>
                    <th className="px-3 py-2">FPFV</th>
                    <th className="px-3 py-2">LPFV</th>
                    <th className="px-3 py-2">LPLV</th>
                    <th className="px-3 py-2 text-right">Rand target</th>
                    <th className="px-3 py-2 text-right">Screen target</th>
                    {(s === "draft" || s === "planned") && (
                      <th className="px-3 py-2 text-right">Actions</th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {grouped[s].map((t) => (
                    <tr key={t.id} className="border-t border-slate-100 hover:bg-slate-50">
                      <td className="px-3 py-1.5">
                        <Link
                          to={`/trials/${t.id}`}
                          className="hover:underline"
                          data-testid={`studies-row-${t.id}`}
                        >
                          <TrialColorBadge trialId={t.id} name={t.name} />
                        </Link>
                      </td>
                      <td className="px-3 py-1.5 text-slate-600">{t.fpfv}</td>
                      <td className="px-3 py-1.5 text-slate-600">{t.lpfv}</td>
                      <td className="px-3 py-1.5 text-slate-600">{t.lplv}</td>
                      <td className="px-3 py-1.5 text-right">
                        {fmtCount(t.enrollment_target)}
                      </td>
                      <td className="px-3 py-1.5 text-right">
                        {fmtCount(t.screening_target)}
                      </td>
                      {(s === "draft" || s === "planned") && (
                        <td className="px-3 py-1.5 text-right">
                          <TrialStatusActions
                            trialId={t.id}
                            status={t.status}
                            variant="inline"
                          />
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ),
      )}
    </div>
  );
}
