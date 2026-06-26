/**
 * Hours / Visits chart metric — which value the forecast charts plot. The
 * choice persists per browser and is shared across charts.
 */

import { useCallback, useState } from "react";

export type ChartMetric = "hours" | "visits";

const KEY = "chart.metric";

export function useChartMetric(): [ChartMetric, (m: ChartMetric) => void] {
  const [metric, set] = useState<ChartMetric>(() =>
    localStorage.getItem(KEY) === "visits" ? "visits" : "hours",
  );
  const setMetric = useCallback((m: ChartMetric) => {
    localStorage.setItem(KEY, m);
    set(m);
  }, []);
  return [metric, setMetric];
}
