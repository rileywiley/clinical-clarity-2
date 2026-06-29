/**
 * Hours / Visits chart metric — which value the forecast charts plot. The
 * choice persists per browser and is shared across charts.
 */

import { useCallback, useState } from "react";

export type ChartMetric = "hours" | "visits" | "revenue";

const KEY = "chart.metric";

export function useChartMetric(): [ChartMetric, (m: ChartMetric) => void] {
  const [metric, set] = useState<ChartMetric>(() => {
    const v = localStorage.getItem(KEY);
    return v === "visits" || v === "revenue" ? v : "hours";
  });
  const setMetric = useCallback((m: ChartMetric) => {
    localStorage.setItem(KEY, m);
    set(m);
  }, []);
  return [metric, setMetric];
}
