/**
 * Reusable empty-state. Used on NetworkGrid (no sites), SiteChart (no trials
 * assigned), TrialDetail (no SoA), Metrics (no active trials), Calendar (no
 * data this month). Print-hidden so PDFs don't carry "no data yet" panels.
 */

import type { ReactNode } from "react";

export type EmptyStateProps = {
  title: string;
  body?: string;
  /** Optional CTA — usually a <Link> or <button>. */
  action?: ReactNode;
  /** Override for the icon. Defaults to a small empty-circle SVG. */
  icon?: ReactNode;
};

export function EmptyState({ title, body, action, icon }: EmptyStateProps) {
  return (
    <div
      className="no-print mx-auto max-w-md rounded border border-slate-200 bg-white p-6 text-center"
      data-testid="empty-state"
    >
      <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-slate-500">
        {icon ?? <DefaultIcon />}
      </div>
      <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
      {body && <p className="mt-1 text-sm text-slate-600">{body}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

function DefaultIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="12" cy="12" r="9" />
      <line x1="9" y1="9" x2="15" y2="15" />
      <line x1="15" y1="9" x2="9" y2="15" />
    </svg>
  );
}
