/**
 * Hours / Visits toggle for the forecast charts. The engine returns both demand
 * hours and visit counts per cell; this switches which the chart plots. State
 * lives in lib/chartMetric (useChartMetric), shared across charts.
 */

import type { ChartMetric } from "../lib/chartMetric";

const OPTIONS: { value: ChartMetric; label: string }[] = [
  { value: "hours", label: "Hours" },
  { value: "visits", label: "Visits" },
  { value: "revenue", label: "Revenue" },
];

export function MetricToggle({
  value,
  onChange,
}: {
  value: ChartMetric;
  onChange: (m: ChartMetric) => void;
}) {
  return (
    <div
      className="inline-flex rounded border border-slate-300 no-print"
      role="group"
      aria-label="Chart metric"
      data-testid="metric-toggle"
    >
      {OPTIONS.map((o, i) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          data-testid={`metric-${o.value}`}
          onClick={() => onChange(o.value)}
          className={
            (i > 0 ? "border-l border-slate-300 " : "") +
            "px-3 py-1.5 text-sm " +
            (value === o.value
              ? "bg-slate-900 text-white"
              : "bg-white text-slate-700 hover:bg-slate-50")
          }
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
