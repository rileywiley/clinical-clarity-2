/**
 * Enrollment metrics view (PRD §8.4).
 *
 * Study-level table showing per-trial: SFR, screen rate, enrollment rate,
 * pace vs plan, health vs both goals, WoW. Click trial name → trial detail.
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { TrialColorBadge } from "../components/TrialColorBadge";
import { fmtCount, fmtPct, fmtPct1 } from "../lib/formatters";

export default function Metrics() {
  const trialsQ = useQuery({
    queryKey: ["trials-active"],
    queryFn: api.listActiveTrials,
  });

  // Fetch metrics for each active trial.
  const metricsQ = useQuery({
    queryKey: ["all-trial-metrics", trialsQ.data?.map((t) => t.id).join(",")],
    queryFn: async () => {
      const out: Awaited<ReturnType<typeof api.trialMetrics>>[] = [];
      for (const t of trialsQ.data ?? []) {
        out.push(await api.trialMetrics(t.id));
      }
      return out;
    },
    enabled: !!trialsQ.data && trialsQ.data.length > 0,
  });

  const hasTrials = !!trialsQ.data && trialsQ.data.length > 0;
  // Loading while trials are loading, or while we know trials exist but the
  // dependent per-trial metrics fetches haven't yielded yet.
  const stillLoading =
    trialsQ.isLoading ||
    (hasTrials && (metricsQ.isPending || metricsQ.isFetching));
  if (stillLoading) {
    return <div className="p-8 text-slate-500">Loading…</div>;
  }

  const rows = metricsQ.data ?? [];

  return (
    <div className="mx-auto max-w-7xl p-6">
      <nav className="mb-4 text-sm text-slate-500" aria-label="Breadcrumb">
        <Link to="/" className="hover:underline">
          Network
        </Link>
        <span className="mx-2">/</span>
        <span className="text-slate-800">Metrics</span>
      </nav>

      <header className="mb-4">
        <h1 className="text-2xl font-semibold">Enrollment metrics</h1>
        <p className="text-sm text-slate-500">
          Window: last 12 weeks. Compares plan vs actual where past.
        </p>
      </header>

      <div className="overflow-x-auto rounded border border-slate-200 bg-white">
        <table className="w-full text-sm" data-testid="metrics-table">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-3 py-2">Trial</th>
              <th className="px-3 py-2 text-right">Screened</th>
              <th className="px-3 py-2 text-right">Randomized</th>
              <th className="px-3 py-2 text-right">SFR</th>
              <th className="px-3 py-2 text-right">Screen / site / wk</th>
              <th className="px-3 py-2 text-right">Enroll / site / wk</th>
              <th className="px-3 py-2 text-right">Pace</th>
              <th className="px-3 py-2 text-right">Rand. health</th>
              <th className="px-3 py-2 text-right">Screen health</th>
              <th className="px-3 py-2 text-right">WoW screened</th>
              <th className="px-3 py-2 text-right">WoW rand.</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td
                  colSpan={11}
                  className="px-3 py-6 text-center text-slate-500"
                >
                  No active trials yet.
                </td>
              </tr>
            )}
            {rows.map((row) => (
              <tr
                key={row.trial_id}
                className="border-t border-slate-100"
                data-testid={`metrics-row-${row.trial_id}`}
              >
                <td className="px-3 py-1.5">
                  <Link
                    to={`/trials/${row.trial_id}`}
                    className="hover:underline"
                  >
                    <TrialColorBadge
                      trialId={row.trial_id}
                      name={row.trial_name}
                    />
                  </Link>
                </td>
                <td className="px-3 py-1.5 text-right">
                  {fmtCount(row.metrics.screened)}
                </td>
                <td className="px-3 py-1.5 text-right">
                  {fmtCount(row.metrics.randomized)}
                </td>
                <td className="px-3 py-1.5 text-right">
                  {fmtPct(row.metrics.screen_fail_rate)}
                </td>
                <td className="px-3 py-1.5 text-right">
                  {row.metrics.screen_rate?.toFixed(1) ?? "—"}
                </td>
                <td className="px-3 py-1.5 text-right">
                  {row.metrics.enrollment_rate?.toFixed(1) ?? "—"}
                </td>
                <td
                  className={`px-3 py-1.5 text-right ${
                    row.metrics.pace_vs_plan != null &&
                    row.metrics.pace_vs_plan < 0.9
                      ? "text-amber-700"
                      : ""
                  }`}
                >
                  {fmtPct1(row.metrics.pace_vs_plan)}
                </td>
                <td className="px-3 py-1.5 text-right">
                  {fmtPct1(row.metrics.enrollment_health_randomized)}
                </td>
                <td className="px-3 py-1.5 text-right">
                  {fmtPct1(row.metrics.enrollment_health_screened)}
                </td>
                <td className="px-3 py-1.5 text-right">
                  {row.metrics.wow_screened ?? "—"}
                </td>
                <td className="px-3 py-1.5 text-right">
                  {row.metrics.wow_randomized ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
