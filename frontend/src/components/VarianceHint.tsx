/**
 * Inline variance badges (PRD §7.3): "Randomized 87 / goal 100 · 13 under".
 *
 * Warn-and-allow: never blocks saves. The negative case is highlighted in
 * amber to signal "this is informational, not a stop."
 */

import type { TrialVarianceOut } from "../api";

export function VarianceHint({ variance }: { variance: TrialVarianceOut }) {
  return (
    <div className="flex flex-wrap items-center gap-3 text-sm">
      <Badge
        label="Randomized"
        sum={variance.randomization.sum_site}
        target={variance.randomization.target}
        diff={variance.randomization.diff}
      />
      <Badge
        label="Screened"
        sum={variance.screening.sum_site}
        target={variance.screening.target}
        diff={variance.screening.diff}
      />
    </div>
  );
}

function Badge({
  label,
  sum,
  target,
  diff,
}: {
  label: string;
  sum: number;
  target: number;
  diff: number;
}) {
  const status =
    target === 0 ? "neutral" : diff < 0 ? "under" : diff > 0 ? "over" : "match";
  const palette =
    status === "under"
      ? "bg-amber-50 text-amber-900 ring-amber-200"
      : status === "over"
        ? "bg-emerald-50 text-emerald-900 ring-emerald-200"
        : "bg-slate-50 text-slate-700 ring-slate-200";
  const tail =
    target === 0
      ? ""
      : diff === 0
        ? "· on target"
        : diff < 0
          ? `· ${Math.abs(diff)} under`
          : `· ${diff} over`;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-2 py-1 ring-1 ${palette}`}
      data-testid={`variance-${label.toLowerCase()}`}
    >
      <strong>{label}</strong> {sum} / goal {target} {tail}
    </span>
  );
}
