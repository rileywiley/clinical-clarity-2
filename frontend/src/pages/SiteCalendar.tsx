/**
 * Per-site calendar heatmap (PRD §8.5).
 *
 * Month grid. Each day cell colored by that day's utilization (same green/
 * amber/red scale as the network grid). Month nav. Click a day to expand a
 * panel showing visit breakdown.
 */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, type DailyVisitsOut } from "../api";
import { bandClasses, classifyUtil } from "../lib/utilization";
import { fmtCount, fmtPct } from "../lib/formatters";

function ymOf(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function parseYm(ym: string): Date {
  const [y, m] = ym.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1));
}

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function SiteCalendar() {
  const { siteId = "" } = useParams<{ siteId: string }>();
  const [month, setMonth] = useState<string>(() => ymOf(new Date()));
  const [selectedDay, setSelectedDay] = useState<string | null>(null);

  const sitesQ = useQuery({ queryKey: ["sites"], queryFn: api.listSites });
  const calQ = useQuery({
    queryKey: ["calendar", siteId, month],
    queryFn: () => api.siteCalendar(siteId, month),
    enabled: !!siteId,
  });
  const settingsQ = useQuery({
    queryKey: ["org-settings"],
    queryFn: async () => {
      const r = await fetch("/api/org-settings", { credentials: "include" });
      if (!r.ok) throw new Error("settings");
      return r.json() as Promise<{
        util_threshold_green_max: number;
        util_threshold_amber_max: number;
      }>;
    },
  });

  const site = sitesQ.data?.find((s) => s.id === siteId);
  const thresholds = {
    green_max_pct: settingsQ.data?.util_threshold_green_max ?? 70,
    amber_max_pct: settingsQ.data?.util_threshold_amber_max ?? 95,
  };

  const byDay = useMemo(() => {
    const m = new Map<string, DailyVisitsOut>();
    for (const d of calQ.data ?? []) m.set(d.day, d);
    return m;
  }, [calQ.data]);

  // Build the month grid: array of weeks, each week is 7 cells (Mon..Sun).
  // Pad with nulls for the leading/trailing days outside this month.
  const grid = useMemo(() => {
    const start = parseYm(month);
    const year = start.getUTCFullYear();
    const mo = start.getUTCMonth();
    const daysInMonth = new Date(Date.UTC(year, mo + 1, 0)).getUTCDate();

    const cells: (DailyVisitsOut | null)[] = [];
    // Leading padding: days before the 1st (Mon=0).
    const firstWeekday = start.getUTCDay() === 0 ? 6 : start.getUTCDay() - 1;
    for (let i = 0; i < firstWeekday; i++) cells.push(null);
    for (let d = 1; d <= daysInMonth; d++) {
      const iso = `${year}-${String(mo + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      cells.push(byDay.get(iso) ?? null);
    }
    // Trailing padding to complete the last week row.
    while (cells.length % 7 !== 0) cells.push(null);
    // Chunk into weeks.
    const weeks: (DailyVisitsOut | null)[][] = [];
    for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
    return weeks;
  }, [month, byDay]);

  if (!site && !sitesQ.isLoading) {
    return (
      <div className="mx-auto mt-12 max-w-2xl p-6">
        <p>Site not found.</p>
        <Link to="/" className="text-sm text-blue-600 hover:underline">
          ← Network
        </Link>
      </div>
    );
  }

  function shiftMonth(delta: number) {
    const d = parseYm(month);
    d.setUTCMonth(d.getUTCMonth() + delta);
    setMonth(ymOf(d));
    setSelectedDay(null);
  }

  const selectedCell = selectedDay ? byDay.get(selectedDay) ?? null : null;
  const monthLabel = parseYm(month).toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });

  return (
    <div className="mx-auto max-w-5xl p-6">
      <nav className="mb-4 text-sm text-slate-500" aria-label="Breadcrumb">
        <Link to="/" className="hover:underline">
          Network
        </Link>
        <span className="mx-2">/</span>
        <Link to={`/sites/${siteId}`} className="hover:underline">
          {site?.name ?? "site"}
        </Link>
        <span className="mx-2">/</span>
        <span className="text-slate-800">Calendar</span>
      </nav>

      <header className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{site?.name ?? "Site"} — Calendar</h1>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => shiftMonth(-1)}
            className="rounded border border-slate-300 px-2 py-1 text-sm"
            aria-label="Previous month"
          >
            ‹
          </button>
          <span className="min-w-[8rem] text-center text-sm font-medium">
            {monthLabel}
          </span>
          <button
            type="button"
            onClick={() => shiftMonth(1)}
            className="rounded border border-slate-300 px-2 py-1 text-sm"
            aria-label="Next month"
          >
            ›
          </button>
        </div>
      </header>

      <div className="grid grid-cols-7 gap-1 rounded border border-slate-200 bg-white p-2" data-testid="calendar-grid">
        {WEEKDAYS.map((d) => (
          <div
            key={d}
            className="px-1 pb-1 text-center text-xs font-medium text-slate-500"
          >
            {d}
          </div>
        ))}
        {grid.flat().map((cell, i) => {
          if (cell == null) {
            return <div key={i} className="aspect-square rounded bg-slate-50" />;
          }
          const band = classifyUtil(cell.utilization, thresholds);
          const cls = bandClasses(band);
          const day = parseInt(cell.day.split("-")[2], 10);
          return (
            <button
              key={i}
              type="button"
              onClick={() => setSelectedDay(cell.day)}
              data-testid={`day-${cell.day}`}
              data-band={band}
              className={`flex aspect-square flex-col items-center justify-center rounded text-sm hover:ring-2 hover:ring-blue-400 ${cls}`}
              title={`${cell.day}: ${fmtPct(cell.utilization)} util`}
            >
              <span className="font-medium">{day}</span>
              <span className="text-xs">{fmtPct(cell.utilization)}</span>
            </button>
          );
        })}
      </div>

      {selectedCell && (
        <aside
          className="mt-4 rounded border border-slate-200 bg-white p-4"
          data-testid="day-detail"
        >
          <header className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold">
              {new Date(selectedCell.day + "T00:00:00Z").toLocaleDateString(
                "en-US",
                {
                  weekday: "long",
                  month: "long",
                  day: "numeric",
                  year: "numeric",
                  timeZone: "UTC",
                },
              )}
            </h2>
            <button
              type="button"
              onClick={() => setSelectedDay(null)}
              className="text-slate-500 hover:text-slate-800"
              aria-label="Close day details"
            >
              ✕
            </button>
          </header>
          <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
            <Kv label="Demand hours" value={`${selectedCell.demand_hours.toFixed(1)} hr`} />
            <Kv label="Capacity hours" value={`${selectedCell.capacity_hours.toFixed(1)} hr`} />
            <Kv label="Utilization" value={fmtPct(selectedCell.utilization)} />
            <Kv label="Total visits" value={fmtCount(Object.values(selectedCell.visits_by_type).reduce((a, b) => a + b, 0))} />
          </dl>
          <h3 className="mt-3 text-xs font-medium uppercase tracking-wide text-slate-500">
            By visit type
          </h3>
          <ul className="mt-1 text-sm">
            {Object.entries(selectedCell.visits_by_type).map(([vt, n]) => (
              <li key={vt} className="flex justify-between border-b border-slate-100 py-1">
                <span className="text-slate-700">{vt}</span>
                <span>{fmtCount(n)}</span>
              </li>
            ))}
            {Object.keys(selectedCell.visits_by_type).length === 0 && (
              <li className="py-1 text-slate-500">no visits this day</li>
            )}
          </ul>
        </aside>
      )}
    </div>
  );
}

function Kv({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="text-slate-800">{value}</p>
    </div>
  );
}
