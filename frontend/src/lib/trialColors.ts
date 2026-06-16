/**
 * Deterministic trial → color mapping (PRD §8.2).
 *
 * Each trial gets a persistent color reused across all views. Hashing the
 * trial UUID into a fixed palette means:
 *   - Same color across users, sessions, browsers (no DB column needed)
 *   - Same color across views (network grid, site chart, trial detail)
 *   - At small N (a few trials) collisions are extremely unlikely
 *
 * Palette tuned for stacked-area readability against a light background:
 * distinct hues, similar saturation, ~50% luminance. Generated offline.
 */

const PALETTE = [
  "#2563eb", // blue
  "#16a34a", // green
  "#dc2626", // red
  "#9333ea", // purple
  "#ea580c", // orange
  "#0891b2", // cyan
  "#ca8a04", // amber
  "#db2777", // pink
  "#65a30d", // lime
  "#475569", // slate
  "#0d9488", // teal
  "#7c3aed", // violet
] as const;

/** djb2 hash, 32-bit. Deterministic and uniform enough for palette indexing. */
function djb2(s: string): number {
  let h = 5381;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  }
  return h;
}

export function trialColor(trialId: string): string {
  return PALETTE[djb2(trialId) % PALETTE.length];
}

export function paletteSize(): number {
  return PALETTE.length;
}
