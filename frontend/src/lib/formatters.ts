/** Display formatters. Currency is USD-locked in v1 (PRD §4.5). */

const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const PCT = new Intl.NumberFormat("en-US", {
  style: "percent",
  maximumFractionDigits: 0,
});

const PCT1 = new Intl.NumberFormat("en-US", {
  style: "percent",
  maximumFractionDigits: 1,
});

export function fmtUsd(value: number | null | undefined): string {
  if (value == null) return "—";
  return USD.format(value);
}

export function fmtPct(value: number | null | undefined): string {
  if (value == null) return "—";
  return PCT.format(value);
}

export function fmtPct1(value: number | null | undefined): string {
  if (value == null) return "—";
  return PCT1.format(value);
}

export function fmtHours(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${value.toFixed(1)} hr`;
}

export function fmtCount(value: number | null | undefined): string {
  if (value == null) return "—";
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(1);
}

/** Short month-day, e.g. "Jun 8". */
export function fmtMonDay(iso: string): string {
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}
