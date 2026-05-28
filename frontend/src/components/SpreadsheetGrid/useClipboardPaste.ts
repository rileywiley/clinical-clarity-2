/**
 * Clipboard paste — fill a rectangular block of cells from a TSV (Excel /
 * Numbers / Google Sheets copy format) starting at the active cell. PRD §7.3:
 * paste is a first-class acceptance criterion.
 *
 * The hook is stateless w.r.t. the grid — it just parses the clipboard text
 * and fans the values out to the writer the parent passes in.
 */

import { useCallback } from "react";
import type { CellCoord } from "./types";

export type PasteWriter = (coord: CellCoord, value: number | null) => void;

export type UsePasteOptions = {
  rowCount: number;
  columnCount: number;
  isEnabled: (row: number, col: number) => boolean;
  writeCell: PasteWriter;
};

/**
 * Parse Excel/Numbers TSV. Rows separated by \n (also \r\n), cells by \t.
 * Empty cells are kept as empty strings; numeric parsing happens per-cell.
 *
 * Exported separately so tests can exercise the parser without React.
 */
export function parseTSV(text: string): string[][] {
  // Strip a single trailing newline that most copy operations append.
  const trimmed = text.replace(/\r\n?/g, "\n").replace(/\n$/, "");
  if (trimmed === "") return [];
  return trimmed.split("\n").map((line) => line.split("\t"));
}

/**
 * Convert a raw cell value (string) to the canonical number-or-null we store.
 * Blank → null. Anything that doesn't parse cleanly → null (caller's choice
 * could differ; for v1 we go conservative).
 */
export function parseCellValue(raw: string): number | null {
  const t = raw.trim();
  if (t === "") return null;
  // Strip thousands separators (commas) for ease of paste-from-spreadsheet.
  const cleaned = t.replace(/,/g, "");
  const n = Number(cleaned);
  if (!Number.isFinite(n)) return null;
  return n;
}

export function useClipboardPaste({
  rowCount,
  columnCount,
  isEnabled,
  writeCell,
}: UsePasteOptions) {
  const handlePaste = useCallback(
    (e: React.ClipboardEvent, anchor: CellCoord) => {
      const text = e.clipboardData.getData("text/plain");
      if (!text) return;
      e.preventDefault();

      const block = parseTSV(text);
      for (let r = 0; r < block.length; r++) {
        for (let c = 0; c < block[r].length; c++) {
          const row = anchor.row + r;
          const col = anchor.col + c;
          if (row < 0 || row >= rowCount) continue;
          if (col < 0 || col >= columnCount) continue;
          if (!isEnabled(row, col)) continue;
          writeCell({ row, col }, parseCellValue(block[r][c]));
        }
      }
    },
    [rowCount, columnCount, isEnabled, writeCell],
  );

  return { handlePaste };
}
