/**
 * SoA review table (PRD §10.2 mitigation, Phase 5).
 *
 * Editable list of parsed visits. Each row carries a confidence band:
 *   green  ≥ 0.85   clean — review optional
 *   amber  0.6–0.85 review recommended
 *   red    < 0.6    blocking — must be touched before Confirm becomes enabled
 *
 * The user's edits ARE the truth — when they click Confirm, the current
 * values (not Claude's originals) get sent to /parse-jobs/{id}/apply.
 */

import { useMemo, useState } from "react";
import type { ParsedVisitOut } from "../api";

const VISIT_TYPES: ParsedVisitOut["visit_type"][] = [
  "screening",
  "randomization",
  "follow_up",
  "other",
];

export type SoaReviewTableProps = {
  initialVisits: ParsedVisitOut[];
  onConfirm: (visits: ParsedVisitOut[]) => Promise<void> | void;
  onDiscard?: () => void;
  saving?: boolean;
};

type Band = "green" | "amber" | "red";

function bandOf(confidence: number): Band {
  if (confidence >= 0.85) return "green";
  if (confidence >= 0.6) return "amber";
  return "red";
}

function bandClass(band: Band): string {
  switch (band) {
    case "green":
      return "bg-emerald-50 border-l-4 border-emerald-300";
    case "amber":
      return "bg-amber-50 border-l-4 border-amber-300";
    case "red":
      return "bg-red-50 border-l-4 border-red-400";
  }
}

export function SoaReviewTable({
  initialVisits,
  onConfirm,
  onDiscard,
  saving = false,
}: SoaReviewTableProps) {
  // Track each row's *original* confidence so we know which red rows the
  // user has touched (touching clears the block).
  type Row = ParsedVisitOut & { _originalBand: Band; _touched: boolean };
  const [rows, setRows] = useState<Row[]>(() =>
    initialVisits.map((v) => ({
      ...v,
      _originalBand: bandOf(v.confidence),
      _touched: false,
    })),
  );

  const unresolvedReds = useMemo(
    () => rows.filter((r) => r._originalBand === "red" && !r._touched).length,
    [rows],
  );
  const canConfirm = !saving && unresolvedReds === 0;

  function updateRow(i: number, patch: Partial<ParsedVisitOut>) {
    setRows((rs) => {
      const next = rs.slice();
      next[i] = { ...next[i], ...patch, _touched: true };
      return next;
    });
  }

  function removeRow(i: number) {
    setRows((rs) => rs.filter((_, idx) => idx !== i));
  }

  function addRow() {
    setRows((rs) => [
      ...rs,
      {
        name: "",
        visit_type: "follow_up",
        target_day_offset: 0,
        window_days: 0,
        confidence: 1.0, // user-added rows are implicitly confirmed
        flagged_reason: null,
        _originalBand: "green",
        _touched: true,
      },
    ]);
  }

  async function handleConfirm() {
    const payload: ParsedVisitOut[] = rows.map(({ _originalBand, _touched, ...v }) => v);
    await onConfirm(payload);
  }

  return (
    <div data-testid="soa-review-table" className="space-y-3">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold">Review parsed visits</h2>
          <p className="text-sm text-slate-500">
            Rows flagged in amber or red were uncertain. Touch any red row to
            unblock saving — review red rows carefully.
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs text-slate-600">
          <Legend color="emerald-300" label="Confident" />
          <Legend color="amber-300" label="Review" />
          <Legend color="red-400" label="Blocking" />
        </div>
      </header>

      {unresolvedReds > 0 && (
        <p
          className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-800"
          data-testid="soa-review-blocked"
        >
          {unresolvedReds} row{unresolvedReds === 1 ? "" : "s"} with low
          confidence must be touched before you can save.
        </p>
      )}

      <div className="overflow-x-auto rounded border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2 text-right">Day offset</th>
              <th className="px-3 py-2 text-right">Window (±d)</th>
              <th className="px-3 py-2 text-right">Confidence</th>
              <th className="px-3 py-2">Flag</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const liveBand = bandOf(row.confidence);
              const cls = bandClass(row._originalBand);
              return (
                <tr
                  key={i}
                  className={`border-b border-slate-100 ${cls}`}
                  data-testid={`soa-row-${i}`}
                  data-original-band={row._originalBand}
                  data-touched={row._touched}
                >
                  <td className="px-3 py-1.5">
                    <input
                      type="text"
                      value={row.name}
                      onChange={(e) => updateRow(i, { name: e.target.value })}
                      className="w-full rounded border border-slate-300 bg-white px-2 py-1"
                      data-testid={`soa-row-${i}-name`}
                    />
                  </td>
                  <td className="px-3 py-1.5">
                    <select
                      value={row.visit_type}
                      onChange={(e) =>
                        updateRow(i, {
                          visit_type: e.target.value as ParsedVisitOut["visit_type"],
                        })
                      }
                      className="rounded border border-slate-300 bg-white px-2 py-1"
                      data-testid={`soa-row-${i}-type`}
                    >
                      {VISIT_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    <input
                      type="number"
                      value={row.target_day_offset}
                      onChange={(e) =>
                        updateRow(i, {
                          target_day_offset: Number(e.target.value),
                        })
                      }
                      className="w-20 rounded border border-slate-300 bg-white px-2 py-1 text-right"
                      data-testid={`soa-row-${i}-offset`}
                    />
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    <input
                      type="number"
                      min={0}
                      value={row.window_days}
                      onChange={(e) =>
                        updateRow(i, {
                          window_days: Math.max(0, Number(e.target.value)),
                        })
                      }
                      className="w-16 rounded border border-slate-300 bg-white px-2 py-1 text-right"
                      data-testid={`soa-row-${i}-window`}
                    />
                  </td>
                  <td
                    className="px-3 py-1.5 text-right tabular-nums"
                    data-testid={`soa-row-${i}-confidence`}
                    data-live-band={liveBand}
                  >
                    {(row.confidence * 100).toFixed(0)}%
                  </td>
                  <td className="px-3 py-1.5 text-xs text-slate-600">
                    {row.flagged_reason ?? ""}
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    <button
                      type="button"
                      onClick={() => removeRow(i)}
                      className="text-slate-400 hover:text-red-600"
                      aria-label={`Remove row ${i + 1}`}
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr>
                <td
                  colSpan={7}
                  className="px-3 py-6 text-center text-slate-500"
                >
                  Parser returned no visits. Add rows manually or discard.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={addRow}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm"
        >
          + Add visit
        </button>
        <div className="flex gap-2">
          {onDiscard && (
            <button
              type="button"
              onClick={onDiscard}
              className="rounded border border-slate-300 px-3 py-1.5 text-sm"
            >
              Discard parsing
            </button>
          )}
          <button
            type="button"
            onClick={handleConfirm}
            disabled={!canConfirm}
            className="rounded bg-slate-900 px-4 py-1.5 text-sm text-white disabled:opacity-40"
            data-testid="soa-confirm-button"
          >
            {saving
              ? "Saving…"
              : unresolvedReds > 0
                ? `Confirm (${unresolvedReds} flagged)`
                : `Confirm ${rows.length} visit${rows.length === 1 ? "" : "s"}`}
          </button>
        </div>
      </div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={`inline-block h-3 w-3 rounded-sm border-l-4 border-${color}`} />
      {label}
    </span>
  );
}
