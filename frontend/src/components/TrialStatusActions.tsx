/**
 * Inline trial lifecycle controls (PRD §6.9 / §7.1).
 *
 * Drop-in transition buttons for a draft or planned trial — the same
 * validated transitions as the wizard's final step (`/activate`, `/plan`),
 * surfaced wherever a trial is shown (TrialDetail, Studies rows) so the
 * operator doesn't have to re-enter the wizard.
 *
 * Self-contained: it reads `me` for the edit permission and invalidates the
 * forecast/legend/list caches on success, so callers just pass id + status.
 *
 * Renders nothing for active/archived trials or for non-editing roles.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ApiError, api, type TrialStatus } from "../api";

type Failure = { reason: string; detail: string };

export function TrialStatusActions({
  trialId,
  status,
  variant = "panel",
}: {
  trialId: string;
  status: TrialStatus;
  variant?: "panel" | "inline";
}) {
  const qc = useQueryClient();
  const meQ = useQuery({ queryKey: ["me"], queryFn: api.me });
  const canEdit =
    meQ.data?.role === "org_admin" || meQ.data?.role === "ops_lead";

  const [failures, setFailures] = useState<Failure[] | null>(null);

  const onError = (err: unknown) => {
    if (err instanceof ApiError && err.status === 422) {
      const body = err.body as
        | { detail?: { failures?: Failure[] } }
        | null;
      setFailures(body?.detail?.failures ?? []);
    } else {
      setFailures([{ reason: "unknown_error", detail: String(err) }]);
    }
  };

  const invalidate = () => {
    setFailures(null);
    for (const key of [
      ["trials"],
      ["trials-readiness"],
      ["forecast-network"],
      ["trials-active"],
      ["trials-scoped"],
      ["trial-forecast", trialId],
      ["trial-metrics", trialId],
    ]) {
      qc.invalidateQueries({ queryKey: key });
    }
  };

  const activate = useMutation({
    mutationFn: () => api.activateTrial(trialId),
    onSuccess: invalidate,
    onError,
  });
  const plan = useMutation({
    mutationFn: () => api.planTrial(trialId),
    onSuccess: invalidate,
    onError,
  });

  // Nothing to do for non-editors or for trials past the draft/planned stage.
  if (!canEdit) return null;
  if (status !== "draft" && status !== "planned") return null;

  const busy = activate.isPending || plan.isPending;

  const activateBtn = (
    <button
      type="button"
      onClick={() => activate.mutate()}
      disabled={busy}
      className={
        variant === "panel"
          ? "rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-40"
          : "rounded bg-slate-900 px-2 py-1 text-xs text-white disabled:opacity-40"
      }
      data-testid={`trial-activate-${trialId}`}
    >
      {activate.isPending ? "Activating…" : "Activate"}
    </button>
  );

  // Only draft trials get the "mark planned" action (planned → plan is a no-op).
  const planBtn = status === "draft" && (
    <button
      type="button"
      onClick={() => plan.mutate()}
      disabled={busy}
      className={
        variant === "panel"
          ? "rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 disabled:opacity-40"
          : "rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 disabled:opacity-40"
      }
      data-testid={`trial-plan-${trialId}`}
    >
      {plan.isPending ? "Marking…" : "Mark planned"}
    </button>
  );

  if (variant === "inline") {
    return (
      <div className="flex items-center justify-end gap-1.5 no-print">
        {activateBtn}
        {planBtn}
        {failures && failures.length > 0 && (
          <span
            className="text-xs text-amber-700"
            title={failures.map((f) => f.detail).join("\n")}
            data-testid={`trial-transition-failed-${trialId}`}
          >
            ⚠ not ready ({failures.length})
          </span>
        )}
      </div>
    );
  }

  return (
    <section
      className="mb-4 rounded border border-slate-200 bg-white p-3 no-print"
      data-testid={`trial-status-actions-${trialId}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-slate-600">
          {status === "draft"
            ? "Ready to go live? Activate now, or mark as planned if it starts later."
            : "This trial is planned. Activate it when it starts."}
        </span>
        <span className="ml-auto flex gap-2">
          {activateBtn}
          {planBtn}
        </span>
      </div>
      {failures && failures.length > 0 && (
        <div
          className="mt-3 rounded border border-amber-200 bg-amber-50 p-3"
          data-testid={`trial-transition-failures-${trialId}`}
        >
          <p className="text-sm font-medium text-amber-900">
            Not ready yet — resolve these first:
          </p>
          <ul className="mt-2 list-disc pl-5 text-sm text-amber-900">
            {failures.map((f) => (
              <li key={f.reason}>
                <strong>{f.reason}:</strong> {f.detail}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-amber-800">
            Finish setup in the{" "}
            <Link
              to={`/trials/new?step=soa&trialId=${trialId}`}
              className="underline"
            >
              trial wizard
            </Link>
            .
          </p>
        </div>
      )}
    </section>
  );
}
