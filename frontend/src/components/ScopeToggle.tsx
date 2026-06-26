/**
 * Forecast scope selector (PRD §6.9).
 *
 * Lets the operator split reporting between committed (active) work and the
 * future pipeline (planned) — or view both combined. A headless segmented
 * control; the parent owns the scope state and refetches on change.
 */

import type { ForecastScope } from "../api";

const OPTIONS: { value: ForecastScope; label: string; title: string }[] = [
  { value: "active", label: "Active", title: "Currently-running trials only" },
  { value: "planned", label: "Planned", title: "Future pipeline trials only" },
  { value: "combined", label: "Combined", title: "Active + planned together" },
];

export function ScopeToggle({
  value,
  onChange,
}: {
  value: ForecastScope;
  onChange: (s: ForecastScope) => void;
}) {
  return (
    <div
      className="inline-flex overflow-hidden rounded border border-slate-300 no-print"
      role="group"
      aria-label="Forecast scope"
      data-testid="scope-toggle"
    >
      {OPTIONS.map((o) => {
        const selected = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            title={o.title}
            aria-pressed={selected}
            data-testid={`scope-${o.value}`}
            onClick={() => onChange(o.value)}
            className={
              "px-3 py-1.5 text-sm " +
              (selected
                ? "bg-slate-900 text-white"
                : "bg-white text-slate-600 hover:bg-slate-50")
            }
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
