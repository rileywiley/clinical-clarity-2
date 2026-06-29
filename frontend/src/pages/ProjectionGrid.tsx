/**
 * Projections & Actuals grid page (PRD §7.3).
 *
 * Weeks as rows. Columns grouped:
 *   Projected → screened, randomized
 *   Actual    → screened, randomized
 *
 * Row classes:
 *   - Past:    projection cells DISABLED (locked); actual cells editable.
 *   - Current: both columns editable; row highlighted.
 *   - Future:  projection cells editable; actual cells DISABLED (greyed).
 *
 * Horizontal divider separates the actuals period from the projection period
 * (drawn after the current week).
 *
 * Save model: explicit Save button + dirty state + unsaved-changes guard.
 */

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { ApiError, api, type EnrollmentWeekIn, type EnrollmentWeekOut } from "../api";
import { SpreadsheetGrid } from "../components/SpreadsheetGrid";
import type { CellCoord, CellState, ColumnSpec } from "../components/SpreadsheetGrid";
import { VarianceHint } from "../components/VarianceHint";
import { HistoryDrawer } from "../components/HistoryDrawer";
import { useUnsavedChangesGuard } from "../hooks/useUnsavedChangesGuard";

type WeekRow = EnrollmentWeekOut;

const PROJ_FIELDS: (keyof EnrollmentWeekIn)[] = ["proj_screened", "proj_randomized"];
const ACTUAL_FIELDS: (keyof EnrollmentWeekIn)[] = [
  "actual_screened",
  "actual_randomized",
];

const COLUMNS: ColumnSpec<WeekRow>[] = [
  {
    id: "proj_screened",
    header: "Screened",
    group: "Projected",
    accessor: (r) => r.proj_screened,
  },
  {
    id: "proj_randomized",
    header: "Randomized",
    group: "Projected",
    accessor: (r) => r.proj_randomized,
  },
  {
    id: "actual_screened",
    header: "Screened",
    group: "Actual",
    accessor: (r) => r.actual_screened,
  },
  {
    id: "actual_randomized",
    header: "Randomized",
    group: "Actual",
    accessor: (r) => r.actual_randomized,
  },
];

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function isoMondayOf(iso: string): string {
  const d = new Date(iso + "T00:00:00Z");
  const dow = d.getUTCDay(); // Sun=0..Sat=6
  const delta = dow === 0 ? -6 : 1 - dow; // shift to Monday
  d.setUTCDate(d.getUTCDate() + delta);
  return d.toISOString().slice(0, 10);
}

function addWeeks(iso: string, n: number): string {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n * 7);
  return d.toISOString().slice(0, 10);
}

function classifyWeek(weekStartIso: string, todayMondayIso: string): "past" | "current" | "future" {
  if (weekStartIso < todayMondayIso) return "past";
  if (weekStartIso === todayMondayIso) return "current";
  return "future";
}

export default function ProjectionGrid() {
  // --- Pickers (site → trial → arm). Minimal v1 UX; Phase 4 drill-down
  // navigation lands later. --------------------------------------------
  const sitesQ = useQuery({ queryKey: ["sites"], queryFn: api.listSites });
  const trialsQ = useQuery({ queryKey: ["trials"], queryFn: api.listTrials });

  // Deep-link support: ?site=&trial= pre-selects the pickers (e.g. clicking an
  // assigned study on the site page jumps straight to its projections).
  const [searchParams] = useSearchParams();
  const [trialId, setTrialId] = useState<string | null>(
    () => searchParams.get("trial"),
  );
  const [siteId, setSiteId] = useState<string | null>(
    () => searchParams.get("site"),
  );

  // Auto-pick the first option if available so the page isn't a blank picker
  // forever — easier to demo.
  useEffect(() => {
    if (!trialId && trialsQ.data && trialsQ.data.length > 0) {
      setTrialId(trialsQ.data[0].id);
    }
  }, [trialId, trialsQ.data]);
  useEffect(() => {
    if (!siteId && sitesQ.data && sitesQ.data.length > 0) {
      setSiteId(sitesQ.data[0].id);
    }
  }, [siteId, sitesQ.data]);

  const armsQ = useQuery({
    queryKey: ["arms", trialId],
    queryFn: () => api.listArms(trialId!),
    enabled: !!trialId,
  });
  const assignmentsQ = useQuery({
    queryKey: ["assignments", trialId],
    queryFn: () => api.listAssignments(trialId!),
    enabled: !!trialId,
  });

  const selectedSite = sitesQ.data?.find((s) => s.id === siteId) ?? null;
  const armId = armsQ.data?.[0]?.id ?? null;
  const siteTrial = useMemo(
    () =>
      assignmentsQ.data?.find((a) => a.site_id === siteId && a.active) ?? null,
    [assignmentsQ.data, siteId],
  );

  // --- Date range: 4 past weeks + current + 11 future = 16 rows. ------
  const todayMonday = useMemo(() => isoMondayOf(isoToday()), []);
  const from = useMemo(() => addWeeks(todayMonday, -4), [todayMonday]);
  const to = useMemo(() => addWeeks(todayMonday, 11), [todayMonday]);

  const weeksQ = useQuery({
    queryKey: ["enrollment-weeks", siteTrial?.id, armId, from, to],
    queryFn: () => api.listEnrollmentWeeks(siteTrial!.id, armId!, from, to),
    enabled: !!siteTrial && !!armId,
  });

  const varianceQ = useQuery({
    queryKey: ["trial-variance", trialId],
    queryFn: () => api.getTrialVariance(trialId!),
    enabled: !!trialId,
  });

  // --- Local edit buffer + dirty tracking -----------------------------
  const [draft, setDraft] = useState<WeekRow[]>([]);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (weeksQ.data) {
      setDraft(weeksQ.data);
      setDirty(false);
      setError(null);
    }
  }, [weeksQ.data]);

  useUnsavedChangesGuard({ dirty });

  // --- Mutations ------------------------------------------------------
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: async () => {
      if (!siteTrial || !armId) throw new Error("no site_trial");
      const payload: EnrollmentWeekIn[] = draft.map((r) => ({
        week_start: r.week_start,
        proj_screened: r.proj_screened,
        proj_randomized: r.proj_randomized,
        actual_screened: r.actual_screened,
        actual_randomized: r.actual_randomized,
      }));
      return api.saveEnrollmentWeeks(siteTrial.id, armId, payload);
    },
    onSuccess: () => {
      setDirty(false);
      setError(null);
      qc.invalidateQueries({ queryKey: ["enrollment-weeks"] });
      qc.invalidateQueries({ queryKey: ["history"] });
      qc.invalidateQueries({ queryKey: ["trial-variance"] });
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError) {
        const detail = (err.body as { detail?: { error?: string; offending_week_starts?: string[] } } | null)?.detail;
        if (detail?.error === "past_projection_locked") {
          setError(
            `Past-week projections are locked. Offending: ${detail.offending_week_starts?.join(", ")}`,
          );
          return;
        }
      }
      setError("Save failed.");
    },
  });

  // --- Cell state policy ---------------------------------------------
  const cellState = (row: WeekRow, _ri: number, columnId: string): CellState => {
    const cls = classifyWeek(row.week_start, todayMonday);
    const isProj = PROJ_FIELDS.includes(columnId as keyof EnrollmentWeekIn);
    const isAct = ACTUAL_FIELDS.includes(columnId as keyof EnrollmentWeekIn);
    if (cls === "past" && isProj) {
      return { kind: "disabled", reason: "past-locked" };
    }
    if (cls === "future" && isAct) {
      return { kind: "disabled", reason: "future-greyed" };
    }
    const accessor = COLUMNS.find((c) => c.id === columnId)!.accessor;
    return { kind: "editable", value: accessor(row) };
  };

  const rowClassName = (row: WeekRow) => {
    const cls = classifyWeek(row.week_start, todayMonday);
    if (cls === "current") return "bg-blue-50/40";
    return "";
  };

  const dividerAfterRow = useMemo(() => {
    const idx = draft.findIndex((r) => r.week_start === todayMonday);
    return idx >= 0 ? idx : null;
  }, [draft, todayMonday]);

  const onCellChange = (coord: CellCoord, value: number | null) => {
    const colId = COLUMNS[coord.col].id as keyof EnrollmentWeekIn;
    setDraft((rows) => {
      const next = rows.slice();
      const row = { ...next[coord.row] } as WeekRow;
      // proj_* are non-null in the model; coalesce null → 0 for those.
      if (colId === "proj_screened" || colId === "proj_randomized") {
        (row as Record<string, unknown>)[colId] = value ?? 0;
      } else {
        (row as Record<string, unknown>)[colId] = value;
      }
      next[coord.row] = row;
      return next;
    });
    setDirty(true);
  };

  const [historyOpen, setHistoryOpen] = useState(false);

  // --- Render ---------------------------------------------------------
  return (
    <div className="mx-auto max-w-6xl p-6">
      <Breadcrumbs
        items={[
          { label: "Network", to: "/" },
          ...(selectedSite
            ? [{ label: selectedSite.name, to: `/sites/${selectedSite.id}` }]
            : []),
          { label: "Projections" },
        ]}
      />
      <div className="mb-4">
        <h1 className="text-2xl font-semibold">Projections &amp; actuals</h1>
      </div>

      <div className="mb-4 flex flex-wrap items-end gap-4 rounded border border-slate-200 bg-white p-4">
        <div>
          <label className="block text-xs font-medium text-slate-600">Trial</label>
          <select
            className="mt-1 rounded border border-slate-300 px-2 py-1.5 text-sm"
            value={trialId ?? ""}
            onChange={(e) => {
              if (dirty) {
                // Don't lose unsaved edits when switching context. The
                // navigation guard doesn't fire for state-only changes.
                if (!window.confirm("You have unsaved changes. Discard them?")) {
                  return;
                }
              }
              setTrialId(e.target.value);
            }}
            data-testid="trial-picker"
          >
            {trialsQ.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600">Site</label>
          <select
            className="mt-1 rounded border border-slate-300 px-2 py-1.5 text-sm"
            value={siteId ?? ""}
            onChange={(e) => {
              if (dirty) {
                if (!window.confirm("You have unsaved changes. Discard them?")) {
                  return;
                }
              }
              setSiteId(e.target.value);
            }}
            data-testid="site-picker"
          >
            {sitesQ.data?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => setHistoryOpen(true)}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm"
          >
            View change history
          </button>
          <button
            type="button"
            onClick={() => save.mutate()}
            disabled={!dirty || save.isPending}
            className="rounded bg-slate-900 px-4 py-1.5 text-sm text-white disabled:opacity-40"
            data-testid="save-button"
          >
            {save.isPending ? "Saving…" : dirty ? "Save" : "Saved"}
          </button>
        </div>
      </div>

      {varianceQ.data && (
        <div className="mb-3">
          <VarianceHint variance={varianceQ.data} />
        </div>
      )}

      {error && (
        <div className="mb-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {!siteTrial && (
        <p className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          This site isn't assigned to the selected trial. Assign it under trial
          setup first.
        </p>
      )}

      {siteTrial && armId && draft.length > 0 && (
        <SpreadsheetGrid
          rows={draft}
          columns={COLUMNS}
          rowHeader={(r) => r.week_start}
          rowClassName={rowClassName}
          cellState={cellState}
          onCellChange={onCellChange}
          dividerAfterRow={dividerAfterRow}
        />
      )}

      {siteTrial && armId && (
        <HistoryDrawer
          siteTrialId={siteTrial.id}
          armId={armId}
          open={historyOpen}
          onClose={() => setHistoryOpen(false)}
        />
      )}
    </div>
  );
}
