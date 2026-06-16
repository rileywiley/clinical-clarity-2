/**
 * Utilization → color band. Thresholds come from OrgSettings (PRD §5.1):
 *   - green   → util ≤ green_max
 *   - amber   → green_max < util ≤ amber_max
 *   - red     → amber_max < util ≤ 1.0
 *   - critical → util > 1.0 (over capacity — PRD §8.1: must read loudly)
 *
 * OrgSettings values are percentages (0..100). util is a fraction (0..1).
 */

export type UtilBand = "none" | "green" | "amber" | "red" | "critical";

export type UtilThresholds = {
  green_max_pct: number; // e.g. 70
  amber_max_pct: number; // e.g. 95
};

export function classifyUtil(
  util: number | null,
  thresholds: UtilThresholds,
): UtilBand {
  if (util == null) return "none";
  if (util > 1.0) return "critical";
  if (util * 100 <= thresholds.green_max_pct) return "green";
  if (util * 100 <= thresholds.amber_max_pct) return "amber";
  return "red";
}

/** Tailwind class fragments per band. The cell renderer composes them. */
export function bandClasses(band: UtilBand): string {
  switch (band) {
    case "green":
      return "bg-emerald-100 text-emerald-900";
    case "amber":
      return "bg-amber-100 text-amber-900";
    case "red":
      return "bg-red-200 text-red-900";
    case "critical":
      return "bg-red-600 text-white font-semibold";
    case "none":
      return "bg-slate-50 text-slate-400";
  }
}
