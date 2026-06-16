/** Generic KPI tile strip (PRD §8.1, §8.2). */

export type KpiTile = {
  label: string;
  value: string;
  /** Optional emphasis color — e.g. red for "sites at risk". */
  tone?: "default" | "warning" | "danger";
  /** Optional sublabel rendered smaller beneath the value. */
  sublabel?: string;
};

export function KpiStrip({ tiles }: { tiles: KpiTile[] }) {
  return (
    <div
      className="grid gap-3"
      style={{ gridTemplateColumns: `repeat(${tiles.length}, minmax(0, 1fr))` }}
      data-testid="kpi-strip"
    >
      {tiles.map((t) => {
        const palette =
          t.tone === "danger"
            ? "border-red-300 bg-red-50"
            : t.tone === "warning"
              ? "border-amber-300 bg-amber-50"
              : "border-slate-200 bg-white";
        const valueColor =
          t.tone === "danger"
            ? "text-red-800"
            : t.tone === "warning"
              ? "text-amber-900"
              : "text-slate-900";
        return (
          <div
            key={t.label}
            className={`rounded border p-3 ${palette}`}
            data-testid={`kpi-${t.label.toLowerCase().replace(/\s+/g, "-")}`}
          >
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
              {t.label}
            </p>
            <p className={`mt-1 text-2xl font-semibold ${valueColor}`}>
              {t.value}
            </p>
            {t.sublabel && (
              <p className="mt-0.5 text-xs text-slate-500">{t.sublabel}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}
