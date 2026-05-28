/**
 * Audit history drawer (PRD §7.3 — "View change history").
 *
 * Side panel that lists projection edits, most recent first. Only mounted
 * when open; query runs lazily.
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

export type HistoryDrawerProps = {
  siteTrialId: string;
  armId: string;
  open: boolean;
  onClose: () => void;
};

export function HistoryDrawer({
  siteTrialId,
  armId,
  open,
  onClose,
}: HistoryDrawerProps) {
  const q = useQuery({
    queryKey: ["history", siteTrialId, armId],
    queryFn: () => api.listEnrollmentHistory(siteTrialId, armId),
    enabled: open,
  });

  if (!open) return null;

  return (
    <div className="fixed inset-y-0 right-0 z-20 w-96 overflow-y-auto border-l border-slate-200 bg-white shadow-xl">
      <div className="flex items-center justify-between border-b border-slate-200 p-4">
        <h2 className="text-base font-semibold">Change history</h2>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-slate-500 hover:bg-slate-100"
          aria-label="Close history"
        >
          ✕
        </button>
      </div>
      <div className="p-4">
        {q.isLoading && <p className="text-slate-500">Loading…</p>}
        {q.isError && (
          <p className="text-red-600">Couldn't load history.</p>
        )}
        {q.data && q.data.length === 0 && (
          <p className="text-slate-500">No projection edits yet.</p>
        )}
        {q.data && q.data.length > 0 && (
          <ul className="space-y-3 text-sm">
            {q.data.map((h) => (
              <li
                key={h.id}
                className="rounded border border-slate-200 p-3"
                data-testid="history-row"
              >
                <p className="font-medium text-slate-800">
                  {labelForField(h.field)}
                </p>
                <p className="text-slate-600">
                  {valueOrDash(h.old_value)} → {valueOrDash(h.new_value)}
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  {new Date(h.changed_at).toLocaleString()}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function labelForField(field: string): string {
  switch (field) {
    case "proj_screened":
      return "Projected Screened";
    case "proj_randomized":
      return "Projected Randomized";
    default:
      return field;
  }
}

function valueOrDash(v: number | null): string {
  return v === null ? "—" : String(v);
}
