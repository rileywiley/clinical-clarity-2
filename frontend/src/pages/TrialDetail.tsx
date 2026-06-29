/**
 * Trial detail (PRD §8.3) — drill-down + post-Phase-6 edit surface.
 *
 * Read view:
 *   - trial metadata, KPI strip, forecast chart, SoA table, assigned sites
 *
 * Edit (admin / ops_lead only):
 *   - "Edit details" → metadata modal (name, sponsor, dates, targets, curve)
 *   - "Edit SoA" → inline editable visit rows, add/delete, Save/Cancel
 *   - "Re-parse from PDF" → upload + Claude parse + review, then replace
 *     existing visits (auto-snapshots first so the user can revert)
 *   - "Take snapshot" → manual SoA snapshot
 *   - Snapshot history panel with Restore buttons
 *
 * Active trials show a banner: edits re-flow live (PRD §5.2). We don't
 * block edits on active trials — fixing a typo in a visit name is a
 * common everyday case.
 */

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import {
  ApiError,
  api,
  type ParsedVisitOut,
  type SoaParseJobOut,
} from "../api";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { KpiStrip } from "../components/KpiStrip";
import { MetricToggle } from "../components/MetricToggle";
import { useChartMetric } from "../lib/chartMetric";
import { SoaReviewTable } from "../components/SoaReviewTable";
import { TrialStatusActions } from "../components/TrialStatusActions";
import { trialColor } from "../lib/trialColors";
import { fmtCount, fmtMonDay, fmtPct, fmtUsd } from "../lib/formatters";

type VisitOut = {
  id: string;
  name: string;
  visit_type: string;
  target_day_offset: number;
  window_days: number;
  price: number | null;
  confidence: number | null;
  flagged_reason: string | null;
};

const VISIT_TYPE_LABELS: Record<string, string> = {
  screening: "Screening",
  randomization: "Randomization",
  follow_up: "Follow-up",
  other: "Other",
};
const VISIT_TYPES = ["screening", "randomization", "follow_up", "other"] as const;

export default function TrialDetail() {
  const { trialId = "" } = useParams<{ trialId: string }>();
  const qc = useQueryClient();

  const meQ = useQuery({ queryKey: ["me"], queryFn: api.me });
  const canEdit = meQ.data?.role === "org_admin" || meQ.data?.role === "ops_lead";

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
  const snapshotsQ = useQuery({
    queryKey: ["soa-snapshots", trialId],
    queryFn: () => api.listSoaSnapshots(trialId),
    enabled: !!trialId,
  });

  const trial = trialsQ.data?.find((t) => t.id === trialId);
  const arms = armsQ.data ?? [];

  const visitsQ = useQuery({
    queryKey: ["visits", arms.map((a) => a.id).join(",")],
    queryFn: async () => {
      const all: Record<string, VisitOut[]> = {};
      for (const a of arms) all[a.id] = await fetchArmVisits(a.id);
      return all;
    },
    enabled: arms.length > 0,
  });

  // Wide invalidation helper — many panels share state and the costs
  // are small. Used after every mutation in this page.
  function invalidateTrial() {
    qc.invalidateQueries({ queryKey: ["visits"] });
    qc.invalidateQueries({ queryKey: ["trials"] });
    qc.invalidateQueries({ queryKey: ["arms", trialId] });
    qc.invalidateQueries({ queryKey: ["trial-forecast", trialId] });
    qc.invalidateQueries({ queryKey: ["trial-metrics", trialId] });
    qc.invalidateQueries({ queryKey: ["forecast-network"] });
    qc.invalidateQueries({ queryKey: ["site-forecast"] });
    qc.invalidateQueries({ queryKey: ["soa-snapshots", trialId] });
  }

  const cells = cellsQ.data ?? [];
  const [metric, setMetric] = useChartMetric();
  const chartData = useMemo(
    () =>
      cells.map((c) => ({
        week_start: c.week_start,
        label: fmtMonDay(c.week_start),
        hours: c.demand_hours,
        visits: Object.values(c.visits_by_type).reduce((a, b) => a + b, 0),
        revenue: c.revenue,
      })),
    [cells],
  );

  const [editDetailsOpen, setEditDetailsOpen] = useState(false);
  const [soaEditMode, setSoaEditMode] = useState(false);
  const [reparseOpen, setReparseOpen] = useState(false);

  if (trialsQ.isLoading) {
    return <div className="p-8 text-slate-500">Loading…</div>;
  }
  if (!trial) {
    return (
      <div className="mx-auto mt-12 max-w-2xl p-6">
        <p>Trial not found.</p>
        <Link to="/studies" className="text-sm text-blue-600 hover:underline">
          ← Studies
        </Link>
      </div>
    );
  }

  const sitesById = new Map(sitesQ.data?.map((s) => [s.id, s]) ?? []);
  const primaryArm = arms[0];

  return (
    <div className="mx-auto max-w-7xl p-6">
      <Breadcrumbs
        items={[{ label: "Studies", to: "/studies" }, { label: trial.name }]}
      />

      <header className="mb-4 flex flex-wrap items-center gap-3">
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
              : trial.status === "planned"
                ? "bg-indigo-100 text-indigo-900"
                : "bg-slate-100 text-slate-700"
          }`}
        >
          {trial.status}
        </span>
        {canEdit && (
          <button
            type="button"
            onClick={() => setEditDetailsOpen(true)}
            className="ml-auto rounded border border-slate-300 px-3 py-1 text-sm"
            data-testid="trial-edit-details"
          >
            Edit details
          </button>
        )}
      </header>

      {trial.status === "active" && canEdit && (
        <div className="mb-4 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <strong>This trial is active.</strong> Edits re-flow live to the
          network forecast and metrics — no re-publish step (PRD §5.2).
        </div>
      )}

      {trial.status === "planned" && (
        <div className="mb-4 rounded border border-indigo-200 bg-indigo-50 p-3 text-sm text-indigo-900">
          <strong>This trial is planned.</strong> It contributes to the{" "}
          <em>planned</em> and <em>combined</em> forecast scopes, not the default
          active view.
        </div>
      )}

      {/* Inline lifecycle control — renders only for draft/planned + editors. */}
      <TrialStatusActions trialId={trialId} status={trial.status} variant="panel" />

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
              { label: "SFR", value: fmtPct(metricsQ.data.metrics.screen_fail_rate) },
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
                value: fmtPct(metricsQ.data.metrics.enrollment_health_randomized),
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
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-medium text-slate-700">
            Trial forecast contribution —{" "}
            {metric === "hours"
              ? "demand hours"
              : metric === "revenue"
                ? "revenue"
                : "visits"}{" "}
            / week
          </h2>
          <MetricToggle value={metric} onChange={setMetric} />
        </div>
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={chartData} margin={{ top: 8, right: 24, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="#f1f5f9" />
            <XAxis dataKey="label" />
            <YAxis
              tickFormatter={
                metric === "revenue" ? (v: number) => fmtUsd(v) : undefined
              }
            />
            <Tooltip
              formatter={(v: number) =>
                metric === "hours"
                  ? `${v.toFixed(1)} hr`
                  : metric === "revenue"
                    ? fmtUsd(v)
                    : `${v.toFixed(1)} visits`
              }
            />
            <Area
              type="monotone"
              dataKey={metric}
              stroke={trialColor(trial.id)}
              fill={trialColor(trial.id)}
              fillOpacity={0.6}
            />
          </AreaChart>
        </ResponsiveContainer>
      </section>

      <section className="mb-6">
        <header className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-medium text-slate-700">
            Schedule of Activities
          </h2>
          {canEdit && !soaEditMode && !reparseOpen && (
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setSoaEditMode(true)}
                disabled={!primaryArm}
                className="rounded border border-slate-300 px-3 py-1 text-sm disabled:opacity-40"
                data-testid="soa-edit-toggle"
              >
                Edit SoA
              </button>
              <button
                type="button"
                onClick={() => setReparseOpen(true)}
                disabled={!primaryArm}
                className="rounded border border-slate-300 px-3 py-1 text-sm disabled:opacity-40"
                data-testid="soa-reparse-toggle"
              >
                Re-parse from PDF
              </button>
              <ManualSnapshotButton
                trialId={trialId}
                onSnapshotted={() => invalidateTrial()}
              />
            </div>
          )}
        </header>

        {soaEditMode && primaryArm ? (
          <EditableSoaTable
            arm={primaryArm}
            visits={visitsQ.data?.[primaryArm.id] ?? []}
            onDone={() => {
              setSoaEditMode(false);
              invalidateTrial();
            }}
            onCancel={() => setSoaEditMode(false)}
          />
        ) : reparseOpen && primaryArm ? (
          <ReparsePanel
            trialId={trialId}
            armId={primaryArm.id}
            onClose={() => {
              setReparseOpen(false);
              invalidateTrial();
            }}
          />
        ) : (
          <ReadOnlySoaTable
            arms={arms}
            visitsByArm={visitsQ.data ?? {}}
          />
        )}
      </section>

      <SnapshotHistoryPanel
        snapshots={snapshotsQ.data ?? []}
        canEdit={!!canEdit}
        onRestored={() => invalidateTrial()}
      />

      <section className="mt-6">
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

      {editDetailsOpen && (
        <EditTrialModal
          trial={trial}
          onClose={() => setEditDetailsOpen(false)}
          onSaved={() => {
            setEditDetailsOpen(false);
            invalidateTrial();
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SoA — read-only table (unchanged behavior from earlier).

function ReadOnlySoaTable({
  arms,
  visitsByArm,
}: {
  arms: Array<{ id: string }>;
  visitsByArm: Record<string, VisitOut[]>;
}) {
  return (
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
            (visitsByArm[arm.id] ?? []).map((v) => (
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
                <td className="px-3 py-1.5 text-right">{fmtUsd(v.price)}</td>
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
  );
}

// ---------------------------------------------------------------------------
// SoA — inline edit mode (single-arm only; multi-arm is v2).

type EditRow = {
  id: string | null; // null = pending insert
  name: string;
  visit_type: string;
  target_day_offset: number;
  window_days: number;
  price: number | null;
  toDelete?: boolean;
};

function EditableSoaTable({
  arm,
  visits,
  onDone,
  onCancel,
}: {
  arm: { id: string; name: string };
  visits: VisitOut[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const [rows, setRows] = useState<EditRow[]>(() =>
    visits.map((v) => ({
      id: v.id,
      name: v.name,
      visit_type: v.visit_type,
      target_day_offset: v.target_day_offset,
      window_days: v.window_days,
      price: v.price,
    })),
  );
  const [status, setStatus] = useState<"idle" | "saving" | "error">("idle");
  const [errorText, setErrorText] = useState<string | null>(null);

  function addRow() {
    setRows((r) => [
      ...r,
      {
        id: null,
        name: "New visit",
        visit_type: "follow_up",
        target_day_offset: 0,
        window_days: 0,
        price: null,
      },
    ]);
  }

  function updateRow(i: number, patch: Partial<EditRow>) {
    setRows((r) => r.map((row, j) => (i === j ? { ...row, ...patch } : row)));
  }

  function markDelete(i: number) {
    setRows((r) =>
      r.map((row, j) =>
        i === j
          ? row.id == null
            ? { ...row, toDelete: true } // pending insert — drop on save
            : { ...row, toDelete: !row.toDelete }
          : row,
      ),
    );
  }

  async function save() {
    setStatus("saving");
    setErrorText(null);
    try {
      for (const row of rows) {
        if (row.toDelete && row.id) {
          await api.deleteVisit(arm.id, row.id);
        } else if (row.toDelete && row.id == null) {
          // pending insert dropped — no-op
        } else if (row.id == null) {
          await api.createVisit(arm.id, {
            name: row.name,
            visit_type: row.visit_type as
              | "screening"
              | "randomization"
              | "follow_up"
              | "other",
            target_day_offset: row.target_day_offset,
            window_days: row.window_days,
            price: row.price,
            sort_order: 0,
          });
        } else {
          await api.patchVisit(arm.id, row.id, {
            name: row.name,
            visit_type: row.visit_type as
              | "screening"
              | "randomization"
              | "follow_up"
              | "other",
            target_day_offset: row.target_day_offset,
            window_days: row.window_days,
            price: row.price,
          });
        }
      }
      onDone();
    } catch (err) {
      setStatus("error");
      setErrorText(
        err instanceof ApiError
          ? `Save failed (${err.status}). Some rows may have written.`
          : "Save failed.",
      );
    }
  }

  return (
    <div className="rounded border border-blue-200 bg-blue-50/30 p-3">
      <p className="mb-2 text-xs text-blue-900">
        Editing SoA for arm <strong>{arm.name}</strong>. Changes apply on
        Save.
      </p>
      <div className="overflow-x-auto rounded border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-2 py-2">Visit</th>
              <th className="px-2 py-2">Type</th>
              <th className="px-2 py-2 text-right">Day offset</th>
              <th className="px-2 py-2 text-right">Window ±days</th>
              <th className="px-2 py-2 text-right">Price (USD)</th>
              <th className="px-2 py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr
                key={i}
                className={`border-t border-slate-100 ${
                  r.toDelete ? "bg-red-50 line-through opacity-60" : ""
                }`}
              >
                <td className="px-2 py-1">
                  <input
                    type="text"
                    value={r.name}
                    onChange={(e) => updateRow(i, { name: e.target.value })}
                    className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
                    data-testid={`soa-edit-name-${i}`}
                  />
                </td>
                <td className="px-2 py-1">
                  <select
                    value={r.visit_type}
                    onChange={(e) =>
                      updateRow(i, { visit_type: e.target.value })
                    }
                    className="rounded border border-slate-300 px-1 py-1 text-sm"
                  >
                    {VISIT_TYPES.map((vt) => (
                      <option key={vt} value={vt}>
                        {VISIT_TYPE_LABELS[vt]}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-2 py-1 text-right">
                  <input
                    type="number"
                    value={r.target_day_offset}
                    onChange={(e) =>
                      updateRow(i, {
                        target_day_offset: Number(e.target.value),
                      })
                    }
                    className="w-20 rounded border border-slate-300 px-2 py-1 text-right text-sm"
                  />
                </td>
                <td className="px-2 py-1 text-right">
                  <input
                    type="number"
                    min={0}
                    value={r.window_days}
                    onChange={(e) =>
                      updateRow(i, { window_days: Number(e.target.value) })
                    }
                    className="w-20 rounded border border-slate-300 px-2 py-1 text-right text-sm"
                  />
                </td>
                <td className="px-2 py-1 text-right">
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    value={r.price ?? ""}
                    onChange={(e) =>
                      updateRow(i, {
                        price: e.target.value === "" ? null : Number(e.target.value),
                      })
                    }
                    className="w-24 rounded border border-slate-300 px-2 py-1 text-right text-sm"
                  />
                </td>
                <td className="px-2 py-1 text-right">
                  <button
                    type="button"
                    onClick={() => markDelete(i)}
                    className="text-xs text-red-700 hover:underline"
                    data-testid={`soa-edit-delete-${i}`}
                  >
                    {r.toDelete ? "Undo delete" : "Delete"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          onClick={addRow}
          className="rounded border border-slate-300 px-3 py-1 text-sm"
          data-testid="soa-edit-add-row"
        >
          + Add visit
        </button>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-slate-300 px-3 py-1 text-sm"
            data-testid="soa-edit-cancel"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={save}
            disabled={status === "saving"}
            className="rounded bg-slate-900 px-3 py-1 text-sm text-white disabled:opacity-40"
            data-testid="soa-edit-save"
          >
            {status === "saving" ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
      {errorText && (
        <p className="mt-2 text-sm text-red-700">{errorText}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SoA — re-parse from a new PDF, then replace existing visits on apply.

function ReparsePanel({
  trialId,
  armId,
  onClose,
}: {
  trialId: string;
  armId: string;
  onClose: () => void;
}) {
  const [job, setJob] = useState<SoaParseJobOut | null>(null);
  const [parsedVisits, setParsedVisits] = useState<ParsedVisitOut[] | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!job) return;
    if (
      job.status === "succeeded" ||
      job.status === "failed" ||
      job.status === "applied" ||
      job.status === "discarded"
    ) {
      if (job.status === "succeeded") {
        api
          .getParsedVisits(job.id)
          .then((d) => setParsedVisits(d.parsed_visits ?? []))
          .catch(() => setError("Couldn't load parsed visits."));
      }
      return;
    }
    const t = setTimeout(async () => {
      try {
        const next = await api.getParseJob(job.id);
        setJob(next);
      } catch {
        setError("Lost connection to parse job.");
      }
    }, 2000);
    return () => clearTimeout(t);
  }, [job]);

  const upload = useMutation({
    mutationFn: async (file: File) => api.uploadDocument(trialId, file),
    onSuccess: (j) => {
      setJob(j);
      setParsedVisits(null);
      setError(null);
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : "Upload failed.");
    },
  });

  const apply = useMutation({
    mutationFn: async (visits: ParsedVisitOut[]) => {
      if (!job) throw new Error("no job");
      // replace_existing=true takes a snapshot + deletes prior visits
      // before writing the new ones — the whole point of the re-parse path.
      return await api.applyParseJob(job.id, {
        arm_id: armId,
        visits,
        replace_existing: true,
      });
    },
    onSuccess: () => onClose(),
    onError: () => setError("Failed to apply parsed visits."),
  });

  const discard = useMutation({
    mutationFn: async () => {
      if (!job) throw new Error("no job");
      await api.discardParseJob(job.id);
    },
    onSuccess: () => {
      setJob(null);
      setParsedVisits(null);
    },
  });

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) upload.mutate(f);
  }

  return (
    <div className="rounded border border-blue-200 bg-blue-50/30 p-3">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm text-blue-900">
          <strong>Re-parse SoA from PDF.</strong> Applying will replace the
          current SoA — a snapshot is taken automatically so you can revert.
        </p>
        <button
          type="button"
          onClick={onClose}
          className="text-xs text-slate-500 hover:underline"
          data-testid="soa-reparse-close"
        >
          Cancel re-parse
        </button>
      </div>

      {!job && (
        <div className="rounded border border-slate-200 bg-white p-3">
          <input
            type="file"
            accept="application/pdf"
            onChange={onFile}
            data-testid="soa-reparse-file"
            className="block text-sm"
          />
          <p className="mt-2 text-xs text-slate-500">
            PDF only, up to 20 MB. The parse runs through Claude and usually
            takes 30–90 seconds.
          </p>
        </div>
      )}

      {job && (
        <div className="rounded border border-slate-200 bg-white p-3 text-sm">
          <p>
            Parse job{" "}
            <span className="font-mono text-xs">{job.id.slice(0, 8)}</span> —{" "}
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs">
              {job.status}
            </span>
          </p>
          {(job.status === "queued" || job.status === "running") && (
            <p className="mt-2 text-slate-500">
              {job.status === "queued"
                ? "Queued — waiting for a worker…"
                : "Running — Claude is reading the PDF…"}
            </p>
          )}
          {job.status === "failed" && (
            <p className="mt-2 rounded border border-red-200 bg-red-50 p-2 text-red-800">
              Parse failed: {job.error ?? "unknown error"}
            </p>
          )}
        </div>
      )}

      {error && (
        <p className="mt-3 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-800">
          {error}
        </p>
      )}

      {job?.status === "succeeded" && parsedVisits !== null && (
        <div className="mt-4">
          <SoaReviewTable
            initialVisits={parsedVisits}
            onConfirm={async (v) => {
              await apply.mutateAsync(v);
            }}
            onDiscard={() => discard.mutate()}
            saving={apply.isPending}
          />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Manual snapshot button — fires off "manual" snapshot creation.

function ManualSnapshotButton({
  trialId,
  onSnapshotted,
}: {
  trialId: string;
  onSnapshotted: () => void;
}) {
  const m = useMutation({
    mutationFn: async () => {
      const label = window.prompt("Optional label for this snapshot:") || undefined;
      return await api.createSoaSnapshot(trialId, label);
    },
    onSuccess: () => onSnapshotted(),
  });
  return (
    <button
      type="button"
      onClick={() => m.mutate()}
      disabled={m.isPending}
      className="rounded border border-slate-300 px-3 py-1 text-sm disabled:opacity-40"
      data-testid="soa-take-snapshot"
    >
      {m.isPending ? "Saving…" : "Take snapshot"}
    </button>
  );
}

// ---------------------------------------------------------------------------
// SoA snapshot history — list + Restore.

function SnapshotHistoryPanel({
  snapshots,
  canEdit,
  onRestored,
}: {
  snapshots: Array<{
    id: string;
    reason: "reparse_replace" | "manual" | "pre_restore";
    label: string | null;
    created_at: string;
    visit_count: number;
  }>;
  canEdit: boolean;
  onRestored: () => void;
}) {
  const restore = useMutation({
    mutationFn: async (snapId: string) => api.restoreSoaSnapshot(snapId),
    onSuccess: () => onRestored(),
  });
  const reasonLabel = (r: string) =>
    r === "reparse_replace"
      ? "Pre re-parse"
      : r === "pre_restore"
        ? "Pre-restore (auto)"
        : "Manual";

  return (
    <section className="mt-6">
      <h2 className="mb-2 text-sm font-medium text-slate-700">
        SoA version history{" "}
        <span className="text-xs text-slate-500">({snapshots.length})</span>
      </h2>
      <div className="rounded border border-slate-200 bg-white">
        <table className="w-full text-sm" data-testid="soa-snapshots-table">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-3 py-2">Created</th>
              <th className="px-3 py-2">Reason</th>
              <th className="px-3 py-2">Label</th>
              <th className="px-3 py-2 text-right">Visits</th>
              <th className="px-3 py-2 text-right" />
            </tr>
          </thead>
          <tbody>
            {snapshots.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-4 text-center text-slate-500">
                  No snapshots yet. One will be taken automatically the next
                  time you re-parse from PDF.
                </td>
              </tr>
            )}
            {snapshots.map((s) => (
              <tr key={s.id} className="border-t border-slate-100">
                <td className="px-3 py-1.5 text-slate-600">
                  {s.created_at
                    ? new Date(s.created_at).toLocaleString()
                    : "—"}
                </td>
                <td className="px-3 py-1.5 text-slate-700">
                  {reasonLabel(s.reason)}
                </td>
                <td className="px-3 py-1.5 text-slate-700">{s.label ?? "—"}</td>
                <td className="px-3 py-1.5 text-right">{s.visit_count}</td>
                <td className="px-3 py-1.5 text-right">
                  {canEdit && (
                    <button
                      type="button"
                      onClick={() => {
                        if (
                          window.confirm(
                            "Restore this snapshot? Current SoA will be replaced (a pre-restore snapshot is taken automatically).",
                          )
                        ) {
                          restore.mutate(s.id);
                        }
                      }}
                      disabled={restore.isPending}
                      className="rounded border border-slate-300 px-2 py-0.5 text-xs disabled:opacity-40"
                      data-testid={`soa-snapshot-restore-${s.id}`}
                    >
                      Restore
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Edit trial metadata modal.

function EditTrialModal({
  trial,
  onClose,
  onSaved,
}: {
  trial: {
    id: string;
    name: string;
    fpfv: string;
    lpfv: string;
    lplv: string;
    enrollment_target: number;
    screening_target: number;
    attrition_curve_id: string | null;
  };
  onClose: () => void;
  onSaved: () => void;
}) {
  const curvesQ = useQuery({
    queryKey: ["attrition-curves"],
    queryFn: api.listAttritionCurves,
  });
  const [form, setForm] = useState({
    name: trial.name,
    fpfv: trial.fpfv,
    lpfv: trial.lpfv,
    lplv: trial.lplv,
    enrollment_target: trial.enrollment_target,
    screening_target: trial.screening_target,
    attrition_curve_id: trial.attrition_curve_id ?? "",
  });
  const [status, setStatus] = useState<"idle" | "saving" | "error">("idle");
  const [errorText, setErrorText] = useState<string | null>(null);

  async function save() {
    setStatus("saving");
    setErrorText(null);
    try {
      await api.patchTrial(trial.id, {
        name: form.name,
        fpfv: form.fpfv,
        lpfv: form.lpfv,
        lplv: form.lplv,
        enrollment_target: form.enrollment_target,
        screening_target: form.screening_target,
        attrition_curve_id: form.attrition_curve_id || null,
      });
      onSaved();
    } catch (err) {
      setStatus("error");
      setErrorText(
        err instanceof ApiError
          ? typeof err.body === "object" && err.body
            ? JSON.stringify(err.body)
            : `Save failed (${err.status}).`
          : "Save failed.",
      );
    }
  }

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/40 p-4"
      data-testid="trial-edit-modal"
    >
      <div className="w-full max-w-xl rounded-lg bg-white p-5 shadow-lg">
        <h3 className="text-base font-semibold">Edit trial</h3>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <Field label="Name" md="col-span-2">
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5"
              data-testid="trial-edit-name"
            />
          </Field>
          <Field label="FPFV">
            <input
              type="date"
              value={form.fpfv}
              onChange={(e) => setForm((f) => ({ ...f, fpfv: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5"
            />
          </Field>
          <Field label="LPFV">
            <input
              type="date"
              value={form.lpfv}
              onChange={(e) => setForm((f) => ({ ...f, lpfv: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5"
            />
          </Field>
          <Field label="LPLV">
            <input
              type="date"
              value={form.lplv}
              onChange={(e) => setForm((f) => ({ ...f, lplv: e.target.value }))}
              className="w-full rounded border border-slate-300 px-2 py-1.5"
            />
          </Field>
          <Field label="Randomization target">
            <input
              type="number"
              min={0}
              value={form.enrollment_target}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  enrollment_target: Number(e.target.value),
                }))
              }
              className="w-full rounded border border-slate-300 px-2 py-1.5"
            />
          </Field>
          <Field label="Screening target">
            <input
              type="number"
              min={0}
              value={form.screening_target}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  screening_target: Number(e.target.value),
                }))
              }
              className="w-full rounded border border-slate-300 px-2 py-1.5"
            />
          </Field>
          <Field label="Attrition curve" md="col-span-2">
            <select
              value={form.attrition_curve_id}
              onChange={(e) =>
                setForm((f) => ({ ...f, attrition_curve_id: e.target.value }))
              }
              className="w-full rounded border border-slate-300 px-2 py-1.5"
            >
              <option value="">(none)</option>
              {(curvesQ.data ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </Field>
        </div>

        {errorText && (
          <p className="mt-3 text-sm text-red-700">{errorText}</p>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={save}
            disabled={status === "saving"}
            className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-40"
            data-testid="trial-edit-save"
          >
            {status === "saving" ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  md,
  children,
}: {
  label: string;
  md?: string;
  children: React.ReactNode;
}) {
  return (
    <label className={`text-sm ${md ? `md:${md}` : ""}`}>
      <span className="block text-xs font-medium text-slate-600">{label}</span>
      <span className="mt-0.5 block">{children}</span>
    </label>
  );
}

// ---------------------------------------------------------------------------
// Shared helpers.

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

async function fetchArmVisits(armId: string): Promise<VisitOut[]> {
  const r = await fetch(`/api/arms/${armId}/visits`, { credentials: "include" });
  if (!r.ok) throw new Error("visits");
  return r.json();
}
