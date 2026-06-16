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
import { KpiStrip } from "../components/KpiStrip";
import { TrialColorBadge } from "../components/TrialColorBadge";
import { trialColor } from "../lib/trialColors";
import { fmtMonDay, fmtPct, fmtUsd } from "../lib/formatters";

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

  const site = sitesQ.data?.find((s) => s.id === siteId);
  const cells = cellsQ.data ?? [];

  const trialsById = useMemo(() => {
    const m = new Map<string, string>();
    for (const t of trialsQ.data ?? []) m.set(t.id, t.name);
    return m;
  }, [trialsQ.data]);

  // Build the chart series. Convert visit counts to demand hours using each
  // cell's per-type weight. The engine already returned demand_hours so we
  // proportionally allocate across types/trials.
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
      const scale = c.demand_hours / totalVisits;
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
  }, [cells, stackBy]);

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
      <nav className="mb-4 text-sm text-slate-500" aria-label="Breadcrumb">
        <Link to="/" className="hover:underline">
          Network
        </Link>
        <span className="mx-2">/</span>
        <span className="text-slate-800">{site.name}</span>
      </nav>

      <header className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{site.name}</h1>
        <Link
          to={`/sites/${siteId}/calendar`}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm"
        >
          Calendar view
        </Link>
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

      <div className="mb-3 flex items-center justify-between">
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
            <YAxis label={{ value: "room-hours / week", angle: -90, position: "insideLeft" }} />
            <Tooltip
              formatter={(v: number) => `${v.toFixed(1)} hr`}
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
            <Line
              type="monotone"
              dataKey="capacity"
              stroke="#334155"
              strokeWidth={2}
              dot={false}
              name="Capacity"
            />
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
