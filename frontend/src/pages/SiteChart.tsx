/**
 * Per-site chart (PRD §8.2) — diagnostic drill-down.
 *
 * Stacked area chart, y = room-hours/week, flat capacity reference line,
 * dashed "now" marker. Toggle: Stack by Trial / Stack by Visit type.
 * KPI strip on top.
 */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { KpiStrip } from "../components/KpiStrip";
import { MetricToggle } from "../components/MetricToggle";
import { useChartMetric } from "../lib/chartMetric";
import { TrialColorBadge } from "../components/TrialColorBadge";
import { trialColor } from "../lib/trialColors";
import { fmtMonDay, fmtPct, fmtUsd } from "../lib/formatters";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { usePrintToPdf } from "../hooks/usePrintToPdf";

type StackBy = "trial" | "visit_type";

const VISIT_TYPE_COLORS: Record<string, string> = {
  screening: "#0891b2",
  randomization: "#2563eb",
  follow_up: "#16a34a",
  other: "#ca8a04",
};

const VISIT_TYPE_LABELS: Record<string, string> = {
  screening: "Screening",
  randomization: "Randomization",
  follow_up: "Follow-up",
  other: "Other",
};

export default function SiteChart() {
  const { siteId = "" } = useParams<{ siteId: string }>();
  const [stackBy, setStackBy] = useState<StackBy>(() => {
    const saved = localStorage.getItem("siteChart.stackBy");
    return saved === "visit_type" ? "visit_type" : "trial";
  });
  const [metric, setMetric] = useChartMetric();

  const sitesQ = useQuery({ queryKey: ["sites"], queryFn: api.listSites });
  const cellsQ = useQuery({
    queryKey: ["site-forecast", siteId],
    queryFn: () => api.siteForecast(siteId),
    enabled: !!siteId,
  });
  const trialsQ = useQuery({
    queryKey: ["trials-active"],
    queryFn: api.listActiveTrials,
  });
  const trialsAtSiteQ = useQuery({
    queryKey: ["trials-at-site", siteId],
    queryFn: () => api.listTrialsAtSite(siteId),
    enabled: !!siteId,
  });

  const site = sitesQ.data?.find((s) => s.id === siteId);
  useDocumentTitle(site ? site.name : "Site");
  const printToPdf = usePrintToPdf();
  const cells = cellsQ.data ?? [];

  const trialsById = useMemo(() => {
    const m = new Map<string, string>();
    for (const t of trialsQ.data ?? []) m.set(t.id, t.name);
    return m;
  }, [trialsQ.data]);

  // Build the chart series. "hours" and "revenue" proportionally allocate the
  // cell's demand_hours / revenue across types/trials by visit weight; "visits"
  // uses the raw counts directly (scale = 1). Revenue comes from the SoA visit
  // prices the engine already folded into each cell's revenue.
  const chartData = useMemo(() => {
    return cells.map((c) => {
      const totalVisits = Object.values(c.visits_by_type).reduce(
        (a, b) => a + b,
        0,
      );
      const row: Record<string, number | string> = {
        week_start: c.week_start,
        label: fmtMonDay(c.week_start),
        capacity: c.capacity_hours,
        demand: c.demand_hours,
      };
      if (totalVisits === 0) return row;
      const scale =
        metric === "hours"
          ? c.demand_hours / totalVisits
          : metric === "revenue"
            ? c.revenue / totalVisits
            : 1;
      if (stackBy === "trial") {
        for (const [trialId, count] of Object.entries(c.visits_by_trial)) {
          row[`trial:${trialId}`] = count * scale;
        }
      } else {
        for (const [vt, count] of Object.entries(c.visits_by_type)) {
          row[`type:${vt}`] = count * scale;
        }
      }
      return row;
    });
  }, [cells, stackBy, metric]);

  // Series keys for the stacked area.
  const seriesKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const row of chartData) {
      for (const k of Object.keys(row)) {
        if (k.startsWith("trial:") || k.startsWith("type:")) keys.add(k);
      }
    }
    return Array.from(keys);
  }, [chartData]);

  // KPI math.
  const kpis = useMemo(() => {
    const now = cells[0];
    const currentUtil = now?.utilization ?? null;
    const trialIds = new Set<string>();
    for (const c of cells) {
      for (const t of Object.keys(c.visits_by_trial)) trialIds.add(t);
    }
    const overage = cells.find(
      (c) => c.utilization != null && c.utilization > 1.0,
    );
    const revenue = cells.reduce((s, c) => s + c.revenue, 0);
    return {
      currentUtil,
      activeTrials: trialIds.size,
      overage: overage ? fmtMonDay(overage.week_start) : "—",
      revenue,
    };
  }, [cells]);

  function onToggle(next: StackBy) {
    setStackBy(next);
    localStorage.setItem("siteChart.stackBy", next);
  }

  if (sitesQ.isLoading || cellsQ.isLoading) {
    return <div className="p-8 text-slate-500">Loading…</div>;
  }

  if (!site) {
    return (
      <div className="mx-auto mt-12 max-w-2xl p-6">
        <p>Site not found.</p>
        <Link to="/" className="text-sm text-blue-600 hover:underline">
          ← Network
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl p-6">
      <Breadcrumbs items={[{ label: "Network", to: "/" }, { label: site.name }]} />

      <header className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{site.name}</h1>
        <div className="flex items-center gap-2 no-print">
          <a
            href={`/api/sites/${siteId}/forecast.csv`}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm"
            data-testid="export-site-csv"
          >
            Download CSV
          </a>
          <button
            type="button"
            onClick={printToPdf}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm"
            data-testid="export-site-pdf"
          >
            Print to PDF
          </button>
          <Link
            to={`/sites/${siteId}/calendar`}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm"
          >
            Calendar view
          </Link>
        </div>
      </header>

      <div className="mb-4">
        <KpiStrip
          tiles={[
            {
              label: "Current util",
              value: fmtPct(kpis.currentUtil),
            },
            {
              label: "Active trials",
              value: String(kpis.activeTrials),
            },
            {
              label: "Projected overage",
              value: kpis.overage,
              tone: kpis.overage !== "—" ? "warning" : "default",
              sublabel: kpis.overage !== "—" ? "first week > 100%" : undefined,
            },
            {
              label: "Forecast revenue",
              value: fmtUsd(kpis.revenue),
            },
          ]}
        />
      </div>

      <section className="mb-4 rounded border border-slate-200 bg-white">
        <header className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
          <h2 className="text-sm font-medium text-slate-700">Assigned trials</h2>
          <span className="text-xs text-slate-500">
            {trialsAtSiteQ.data?.length ?? 0} total
          </span>
        </header>
        <table className="w-full text-sm" data-testid="trials-at-site-table">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-3 py-2">Trial</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2 text-right">Per-site rand</th>
              <th className="px-3 py-2 text-right">Per-site screen</th>
            </tr>
          </thead>
          <tbody>
            {(trialsAtSiteQ.data ?? []).map((row) => (
              <tr key={row.id} className="border-t border-slate-100">
                <td className="px-3 py-1.5">
                  <div className="flex items-center gap-2">
                    <Link
                      to={`/trials/${row.trial_id}`}
                      className="hover:underline"
                    >
                      <TrialColorBadge trialId={row.trial_id} name={row.trial_name} />
                    </Link>
                    <Link
                      to={`/projections?site=${siteId}&trial=${row.trial_id}`}
                      title="Open this study's projections for this site"
                      aria-label={`Projections for ${row.trial_name}`}
                      data-testid={`site-trial-projections-${row.trial_id}`}
                      className="text-slate-400 hover:text-slate-700"
                    >
                      <svg
                        width="15"
                        height="15"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden
                      >
                        <rect x="3" y="3" width="18" height="18" rx="2" />
                        <path d="M3 9h18M3 15h18M9 3v18M15 3v18" />
                      </svg>
                    </Link>
                  </div>
                </td>
                <td className="px-3 py-1.5 text-slate-600">
                  <StatusPill status={row.trial_status} />
                </td>
                <td className="px-3 py-1.5 text-right">
                  {row.per_site_enrollment_target}
                </td>
                <td className="px-3 py-1.5 text-right">
                  {row.per_site_screening_target}
                </td>
              </tr>
            ))}
            {(trialsAtSiteQ.data ?? []).length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-4 text-center text-slate-500">
                  No trials assigned to this site yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
        <div
          className="inline-flex rounded border border-slate-300"
          role="tablist"
          data-testid="stack-toggle"
        >
          <button
            type="button"
            role="tab"
            aria-selected={stackBy === "trial"}
            className={`px-3 py-1.5 text-sm ${
              stackBy === "trial"
                ? "bg-slate-900 text-white"
                : "bg-white text-slate-700"
            }`}
            onClick={() => onToggle("trial")}
          >
            Stack by trial
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={stackBy === "visit_type"}
            className={`border-l border-slate-300 px-3 py-1.5 text-sm ${
              stackBy === "visit_type"
                ? "bg-slate-900 text-white"
                : "bg-white text-slate-700"
            }`}
            onClick={() => onToggle("visit_type")}
          >
            Stack by visit type
          </button>
        </div>
        <MetricToggle value={metric} onChange={setMetric} />
        </div>
        {stackBy === "trial" && trialsQ.data && (
          <div className="flex flex-wrap items-center gap-3">
            {trialsQ.data.map((t) => (
              <Link
                key={t.id}
                to={`/trials/${t.id}`}
                className="hover:underline"
              >
                <TrialColorBadge trialId={t.id} name={t.name} />
              </Link>
            ))}
          </div>
        )}
      </div>

      <div className="rounded border border-slate-200 bg-white p-3" data-testid="chart-container">
        <ResponsiveContainer width="100%" height={400}>
          <ComposedChart data={chartData} margin={{ top: 8, right: 24, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="#f1f5f9" />
            <XAxis dataKey="label" />
            <YAxis
              tickFormatter={
                metric === "revenue" ? (v: number) => fmtUsd(v) : undefined
              }
              label={{
                value:
                  metric === "hours"
                    ? "room-hours / week"
                    : metric === "revenue"
                      ? "revenue / week"
                      : "visits / week",
                angle: -90,
                position: "insideLeft",
              }}
            />
            <Tooltip
              formatter={(v: number) =>
                metric === "hours"
                  ? `${v.toFixed(1)} hr`
                  : metric === "revenue"
                    ? fmtUsd(v)
                    : `${v.toFixed(1)} visits`
              }
              labelFormatter={(label, payload) => {
                const wk = payload?.[0]?.payload?.week_start;
                return wk ? `Week of ${wk}` : label;
              }}
            />
            <Legend />
            {seriesKeys.map((key) => {
              const id = key.split(":")[1];
              const isTrial = key.startsWith("trial:");
              const color = isTrial
                ? trialColor(id)
                : VISIT_TYPE_COLORS[id] ?? "#64748b";
              const label = isTrial
                ? trialsById.get(id) ?? id.slice(0, 6)
                : VISIT_TYPE_LABELS[id] ?? id;
              return (
                <Area
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stackId="demand"
                  name={label}
                  stroke={color}
                  fill={color}
                  fillOpacity={0.7}
                />
              );
            })}
            {metric === "hours" && (
              <Line
                type="monotone"
                dataKey="capacity"
                stroke="#334155"
                strokeWidth={2}
                dot={false}
                name="Capacity"
              />
            )}
            {chartData[0] && (
              <ReferenceLine
                x={chartData[0].label as string}
                stroke="#3b82f6"
                strokeDasharray="3 3"
                label={{ value: "now", position: "top", fill: "#3b82f6" }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const cls =
    status === "active"
      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
      : status === "draft"
        ? "bg-slate-50 text-slate-700 border-slate-200"
        : "bg-amber-50 text-amber-700 border-amber-200";
  return (
    <span className={`inline-block rounded border px-1.5 py-0.5 text-xs ${cls}`}>
      {status}
    </span>
  );
}
