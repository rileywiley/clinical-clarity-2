/** Small chip showing a trial's persistent color (PRD §8.2). */

import { trialColor } from "../lib/trialColors";

export function TrialColorBadge({
  trialId,
  name,
}: {
  trialId: string;
  name: string;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-slate-700">
      <span
        className="inline-block h-3 w-3 rounded-sm"
        style={{ backgroundColor: trialColor(trialId) }}
        aria-hidden
      />
      {name}
    </span>
  );
}
