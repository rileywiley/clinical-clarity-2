/**
 * Network grid (PRD §8.1) — the anchor view.
 *
 * Rows = sites, columns = weeks (~12 visible, scrollable to horizon).
 * Cells shaded by utilization band. KPI strip on top.
 * Click row label or cell → /sites/:id.
 */

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import type { ForecastCellOut } from "../api";
import { KpiStrip } from "../components/KpiStrip";
import { bandClasses, classifyUtil, type UtilThresholds } from "../lib/utilization";
import { fmtCount, fmtMonDay, fmtPct, fmtUsd } from "../lib/formatters";

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function isoMondayOf(iso: string): string {
  const d = new Date(iso + "T00:00:00Z");
  const dow = d.getUTCDay();
  const delta = dow === 0 ? -6 : 1 - dow;
  d.setUTCDate(d.getUTCDate() + delta);
  return d.toISOString().slice(0, 10);
}

function addWeeks(iso: string, n: number): string {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n * 7);
  return d.toISOString().slice(0, 10);
}

export default function NetworkGrid() {
  const todayMonday = useMemo(() => isoMondayOf(isoToday()), []);
  const from = todayMonday;
  const to = useMemo(() => addWeeks(todayMonday, 11), [todayMonday]);

  const sitesQ = useQuery({ queryKey: ["sites"], queryFn: api.listSites });
  const settingsQ = useQuery({
    queryKey: ["org-settings"],
    queryFn: async () => {
      const r = await fetch("/api/org-settings", { credentials: "include" });
      if (!r.ok) throw new Error("settings");
      return r.json() as Promise<{
        util_threshold_green_max: number;
        util_threshold_amber_max: number;
        default_horizon_months: number;
      }>;
    },
  });
  const cellsQ = useQuery({
    queryKey: ["forecast-network", from, to],
    queryFn: () => api.networkForecast(from, to),
  });
  const trialsQ = useQuery({
    queryKey: ["trials-active"],
    queryFn: api.listActiveTrials,
  });

  const navigate = useNavigate();

  const thresholds: UtilThresholds = {
    green_max_pct: settingsQ.data?.util_threshold_green_max ?? 70,
    amber_max_pct: settingsQ.data?.util_threshold_amber_max ?? 95,
  };

  // Build the column list (week_start ISO strings) from today's Monday → +11.
  const weeks = useMemo(() => {
    const out: string[] = [];
    for (let i = 0; i < 12; i++) out.push(addWeeks(todayMonday, i));
    return out;
  }, [todayMonday]);

  // Bucket cells by site+week.
  const cellByKey = useMemo(() => {
    const m = new Map<string, ForecastCellOut>();
    if (!cellsQ.data) return m;
    for (const c of cellsQ.data) m.set(`${c.site_id}:${c.week_start}`, c);
    return m;
  }, [cellsQ.data]);

  // KPI math — only over cells inside the visible window.
  const kpis = useMemo(() => {
    const cells = cellsQ.data ?? [];
    const sites = sitesQ.data ?? [];
    const activeSites = sites.filter((s) => s.active).length;

    const revenue = cells.reduce((sum, c) => sum + c.revenue, 0);

    let demandSum = 0;
    let capacitySum = 0;
    for (const c of cells) {
      if (c.capacity_hours > 0) {
        demandSum += c.demand_hours;
        capacitySum += c.capacity_hours;
      }
    }
    const avgUtil = capacitySum > 0 ? demandSum / capacitySum : null;

    // Sites at risk: any site with any visible-window cell whose util > amber_max.
    const atRiskSites = new Set<string>();
    for (const c of cells) {
      if (c.utilization == null) continue;
      const band = classifyUtil(c.utilization, thresholds);
      if (band === "red" || band === "critical") atRiskSites.add(c.site_id);
    }

    return {
      activeSites,
      revenue,
      avgUtil,
      atRisk: atRiskSites.size,
    };
  }, [cellsQ.data, sitesQ.data, thresholds]);

  if (sitesQ.isLoading || cellsQ.isLoading || settingsQ.isLoading) {
    return <div className="p-8 text-slate-500">Loading…</div>;
  }

  const sites = sitesQ.data ?? [];
  if (sites.length === 0) {
    return (
      <div className="mx-auto mt-12 max-w-2xl p-6">
        <h1 className="text-2xl font-semibold">Network forecast</h1>
        <div className="mt-6 rounded border border-slate-200 bg-white p-4">
          <p className="text-slate-700">
            No sites yet. Add a site and an active trial to see the network forecast.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl p-6">
      <header className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Network forecast</h1>
        <nav className="flex items-center gap-3 text-sm">
          <Link to="/projections" className="text-slate-600 hover:underline">
            Projections
          </Link>
          <Link to="/metrics" className="text-slate-600 hover:underline">
            Metrics
          </Link>
          <Link
            to="/trials/new"
            className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white"
            data-testid="new-trial-link"
          >
            + New trial
          </Link>
        </nav>
      </header>

      <div className="mb-4">
        <KpiStrip
          tiles={[
            {
              label: "Active sites",
              value: String(kpis.activeSites),
            },
            {
              label: "Forecast revenue",
              value: fmtUsd(kpis.revenue),
              sublabel: "visible window",
            },
            {
              label: "Avg utilization",
              value: fmtPct(kpis.avgUtil),
            },
            {
              label: "Sites at risk",
              value: String(kpis.atRisk),
              tone: kpis.atRisk > 0 ? "danger" : "default",
            },
          ]}
        />
      </div>

      {trialsQ.data && trialsQ.data.length > 0 && (
        <div className="mb-3 text-xs text-slate-500">
          <span className="mr-2 font-medium uppercase tracking-wide">Past · Today · Future</span>
          {trialsQ.data.length} active {trialsQ.data.length === 1 ? "trial" : "trials"}
        </div>
      )}

      <div className="overflow-x-auto rounded border border-slate-200 bg-white">
        <table className="w-full border-collapse text-sm" data-testid="network-grid">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 border-b border-r border-slate-200 bg-slate-50 px-3 py-2 text-left font-medium text-slate-600">
                Site
              </th>
              {weeks.map((wk, i) => (
                <th
                  key={wk}
                  className="border-b border-slate-200 bg-slate-50 px-2 py-2 text-center text-xs font-medium text-slate-600"
                  title={wk}
                >
                  <div>{fmtMonDay(wk)}</div>
                  {i === 0 && <div className="text-blue-600">now</div>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sites.map((site) => (
              <tr key={site.id} data-testid={`site-row-${site.id}`}>
                <th
                  className="sticky left-0 z-10 cursor-pointer border-r border-slate-200 bg-white px-3 py-2 text-left font-medium text-slate-700 hover:underline"
                  scope="row"
                  onClick={() => navigate(`/sites/${site.id}`)}
                >
                  {site.name}
                </th>
                {weeks.map((wk) => {
                  const cell = cellByKey.get(`${site.id}:${wk}`);
                  const band = classifyUtil(
                    cell?.utilization ?? null,
                    thresholds,
                  );
                  const cls = bandClasses(band);
                  const label =
                    cell?.utilization != null ? fmtPct(cell.utilization) : "—";
                  return (
                    <td
                      key={wk}
                      className={`cursor-pointer border-b border-slate-100 px-2 py-2 text-center ${cls}`}
                      data-testid={`cell-${site.id}-${wk}`}
                      data-band={band}
                      onClick={() => navigate(`/sites/${site.id}`)}
                      title={
                        cell
                          ? `${fmtCount(
                              Object.values(cell.visits_by_type).reduce(
                                (a, b) => a + b,
                                0,
                              ),
                            )} visits / ${cell.capacity_hours} hr cap`
                          : "no data"
                      }
                    >
                      {label}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
