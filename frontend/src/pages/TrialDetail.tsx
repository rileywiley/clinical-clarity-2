/**
 * Trial detail (PRD §8.3) — deepest read-only drill-down.
 *
 * Shows trial metadata, attrition curve, the SoA table, per-site assignments,
 * and the trial's forecast contribution chart.
 */

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api";
import { KpiStrip } from "../components/KpiStrip";
import { trialColor } from "../lib/trialColors";
import { fmtCount, fmtMonDay, fmtPct, fmtUsd } from "../lib/formatters";

const VISIT_TYPE_LABELS: Record<string, string> = {
  screening: "Screening",
  randomization: "Randomization",
  follow_up: "Follow-up",
  other: "Other",
};

export default function TrialDetail() {
  const { trialId = "" } = useParams<{ trialId: string }>();

  const trialsQ = useQuery({ queryKey: ["trials"], queryFn: api.listTrials });
  const armsQ = useQuery({
    queryKey: ["arms", trialId],
    queryFn: () => api.listArms(trialId),
    enabled: !!trialId,
  });
  const assignmentsQ = useQuery({
    queryKey: ["assignments", trialId],
    queryFn: () => api.listAssignments(trialId),
    enabled: !!trialId,
  });
  const sitesQ = useQuery({ queryKey: ["sites"], queryFn: api.listSites });
  const cellsQ = useQuery({
    queryKey: ["trial-forecast", trialId],
    queryFn: () => api.trialForecast(trialId),
    enabled: !!trialId,
  });
  const metricsQ = useQuery({
    queryKey: ["trial-metrics", trialId],
    queryFn: () => api.trialMetrics(trialId),
    enabled: !!trialId,
  });

  const trial = trialsQ.data?.find((t) => t.id === trialId);
  const arms = armsQ.data ?? [];

  // Fetch visits for each arm.
  const visitsQ = useQuery({
    queryKey: ["visits", arms.map((a) => a.id).join(",")],
    queryFn: async () => {
      const all: Record<string, Awaited<ReturnType<typeof fetchArmVisits>>> = {};
      for (const a of arms) {
        all[a.id] = await fetchArmVisits(a.id);
      }
      return all;
    },
    enabled: arms.length > 0,
  });

  const cells = cellsQ.data ?? [];
  const chartData = useMemo(() => {
    return cells.map((c) => ({
      week_start: c.week_start,
      label: fmtMonDay(c.week_start),
      hours: c.demand_hours,
    }));
  }, [cells]);

  if (trialsQ.isLoading) {
    return <div className="p-8 text-slate-500">Loading…</div>;
  }
  if (!trial) {
    return (
      <div className="mx-auto mt-12 max-w-2xl p-6">
        <p>Trial not found.</p>
        <Link to="/" className="text-sm text-blue-600 hover:underline">
          ← Network
        </Link>
      </div>
    );
  }

  const sitesById = new Map(sitesQ.data?.map((s) => [s.id, s]) ?? []);

  return (
    <div className="mx-auto max-w-7xl p-6">
      <nav className="mb-4 text-sm text-slate-500" aria-label="Breadcrumb">
        <Link to="/" className="hover:underline">
          Network
        </Link>
        <span className="mx-2">/</span>
        <span className="text-slate-800">{trial.name}</span>
      </nav>

      <header className="mb-4 flex items-center gap-3">
        <span
          className="inline-block h-4 w-4 rounded-sm"
          style={{ backgroundColor: trialColor(trial.id) }}
          aria-hidden
        />
        <h1 className="text-2xl font-semibold">{trial.name}</h1>
        <span
          className={`rounded px-2 py-0.5 text-xs ${
            trial.status === "active"
              ? "bg-emerald-100 text-emerald-900"
              : "bg-slate-100 text-slate-700"
          }`}
        >
          {trial.status}
        </span>
      </header>

      <section className="mb-4 grid gap-3 rounded border border-slate-200 bg-white p-4 text-sm md:grid-cols-3">
        <KvP label="FPFV" value={trial.fpfv} />
        <KvP label="LPFV" value={trial.lpfv} />
        <KvP label="LPLV" value={trial.lplv} />
        <KvP label="Randomization target" value={String(trial.enrollment_target)} />
        <KvP label="Screening target" value={String(trial.screening_target)} />
        <KvP label="Multi-arm" value={trial.is_multi_arm ? "Yes" : "No"} />
      </section>

      {metricsQ.data && (
        <div className="mb-4">
          <KpiStrip
            tiles={[
              {
                label: "SFR",
                value: fmtPct(metricsQ.data.metrics.screen_fail_rate),
              },
              {
                label: "Pace vs plan",
                value: fmtPct(metricsQ.data.metrics.pace_vs_plan),
                tone:
                  metricsQ.data.metrics.pace_vs_plan != null &&
                  metricsQ.data.metrics.pace_vs_plan < 0.9
                    ? "warning"
                    : "default",
              },
              {
                label: "Rand. health",
                value: fmtPct(
                  metricsQ.data.metrics.enrollment_health_randomized,
                ),
              },
              {
                label: "Forecast revenue",
                value: fmtUsd(cells.reduce((s, c) => s + c.revenue, 0)),
              },
            ]}
          />
        </div>
      )}

      <section className="mb-6 rounded border border-slate-200 bg-white p-3">
        <h2 className="mb-2 text-sm font-medium text-slate-700">
          Trial forecast contribution — demand hours / week
        </h2>
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={chartData} margin={{ top: 8, right: 24, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="#f1f5f9" />
            <XAxis dataKey="label" />
            <YAxis />
            <Tooltip formatter={(v: number) => `${v.toFixed(1)} hr`} />
            <Area
              type="monotone"
              dataKey="hours"
              stroke={trialColor(trial.id)}
              fill={trialColor(trial.id)}
              fillOpacity={0.6}
            />
          </AreaChart>
        </ResponsiveContainer>
      </section>

      <section className="mb-6">
        <h2 className="mb-2 text-sm font-medium text-slate-700">
          Schedule of Activities
        </h2>
        <div className="overflow-x-auto rounded border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-3 py-2">Visit</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2 text-right">Day offset</th>
                <th className="px-3 py-2 text-right">Window</th>
                <th className="px-3 py-2 text-right">Price</th>
                <th className="px-3 py-2">Source</th>
              </tr>
            </thead>
            <tbody>
              {arms.flatMap((arm) =>
                (visitsQ.data?.[arm.id] ?? []).map((v) => (
                  <tr key={v.id} className="border-t border-slate-100">
                    <td className="px-3 py-1.5">{v.name}</td>
                    <td className="px-3 py-1.5 text-slate-600">
                      {VISIT_TYPE_LABELS[v.visit_type] ?? v.visit_type}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      {fmtCount(v.target_day_offset)}
                    </td>
                    <td className="px-3 py-1.5 text-right text-slate-600">
                      ±{v.window_days}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      {fmtUsd(v.price)}
                    </td>
                    <td className="px-3 py-1.5">
                      <ConfidenceBadge
                        confidence={v.confidence}
                        flagged={v.flagged_reason}
                      />
                    </td>
                  </tr>
                )),
              )}
              {arms.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-4 text-center text-slate-500">
                    No arms.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-medium text-slate-700">Assigned sites</h2>
        <div className="rounded border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-3 py-2">Site</th>
                <th className="px-3 py-2 text-right">Per-site rand.</th>
                <th className="px-3 py-2 text-right">Per-site screen.</th>
              </tr>
            </thead>
            <tbody>
              {(assignmentsQ.data ?? []).map((a) => {
                const s = sitesById.get(a.site_id);
                return (
                  <tr key={a.id} className="border-t border-slate-100">
                    <td className="px-3 py-1.5">
                      <Link
                        to={`/sites/${a.site_id}`}
                        className="text-blue-600 hover:underline"
                      >
                        {s?.name ?? a.site_id.slice(0, 6)}
                      </Link>
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      {a.per_site_enrollment_target}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      {a.per_site_screening_target}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function ConfidenceBadge({
  confidence,
  flagged,
}: {
  confidence: number | null;
  flagged: string | null;
}) {
  if (confidence == null) {
    return <span className="text-xs text-slate-400">Manual</span>;
  }
  // Bands match the SoA review table (green ≥0.85, amber ≥0.6, red <0.6).
  const band =
    confidence >= 0.85 ? "green" : confidence >= 0.6 ? "amber" : "red";
  const cls = {
    green: "bg-emerald-50 text-emerald-700 border-emerald-200",
    amber: "bg-amber-50 text-amber-700 border-amber-200",
    red: "bg-red-50 text-red-700 border-red-200",
  }[band];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs ${cls}`}
      title={flagged ?? undefined}
    >
      AI · {(confidence * 100).toFixed(0)}%
    </span>
  );
}

function KvP({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="text-slate-800">{value}</p>
    </div>
  );
}

async function fetchArmVisits(armId: string): Promise<
  {
    id: string;
    name: string;
    visit_type: string;
    target_day_offset: number;
    window_days: number;
    price: number | null;
    confidence: number | null;
    flagged_reason: string | null;
  }[]
> {
  const r = await fetch(`/api/arms/${armId}/visits`, { credentials: "include" });
  if (!r.ok) throw new Error("visits");
  return r.json();
}
