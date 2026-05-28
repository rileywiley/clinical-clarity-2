/**
 * Headless spreadsheet primitive (PRD §7.3).
 *
 * The grid is generic over a row shape; the caller passes:
 *   - rows
 *   - columns (with optional column-group headers like "Projected" / "Actual")
 *   - a function describing each cell's state (editable / disabled)
 *   - a writer for cell changes
 *
 * The grid owns: rendering, keyboard nav, clipboard paste, focus management.
 * It does NOT own: persistence, undo, validation messaging. Those live in the
 * page that uses the grid (ProjectionGrid.tsx for Phase 3).
 */

import { useEffect, useMemo, useRef } from "react";
import type { CellCoord, CellStateFn, ColumnSpec } from "./types";
import { useKeyboardNav } from "./useKeyboardNav";
import { useClipboardPaste } from "./useClipboardPaste";

export type SpreadsheetGridProps<TRow> = {
  rows: TRow[];
  columns: ColumnSpec<TRow>[];
  /** Row header rendered to the left of each row (e.g. the week_start). */
  rowHeader: (row: TRow, rowIndex: number) => React.ReactNode;
  /** Optional CSS class for a row (e.g. "is-current-week"). */
  rowClassName?: (row: TRow, rowIndex: number) => string | undefined;
  cellState: CellStateFn<TRow>;
  /** Called when a cell's value changes (typing or paste). */
  onCellChange: (coord: CellCoord, value: number | null) => void;
  /** Optional horizontal divider row index — drawn after the given row. */
  dividerAfterRow?: number | null;
  /** Test hook: surface the active cell so external assertions can read it. */
  onActiveChange?: (coord: CellCoord) => void;
};

export function SpreadsheetGrid<TRow>({
  rows,
  columns,
  rowHeader,
  rowClassName,
  cellState,
  onCellChange,
  dividerAfterRow,
  onActiveChange,
}: SpreadsheetGridProps<TRow>) {
  const colCount = columns.length;
  const rowCount = rows.length;

  const isEnabled = useMemo(
    () => (r: number, c: number) => {
      if (r < 0 || r >= rowCount || c < 0 || c >= colCount) return false;
      return cellState(rows[r], r, columns[c].id).kind === "editable";
    },
    [rows, columns, rowCount, colCount, cellState],
  );

  // Initial active cell: the first enabled cell, if any.
  const initialActive = useMemo<CellCoord>(() => {
    for (let r = 0; r < rowCount; r++) {
      for (let c = 0; c < colCount; c++) {
        if (isEnabled(r, c)) return { row: r, col: c };
      }
    }
    return { row: 0, col: 0 };
  }, [rowCount, colCount, isEnabled]);

  const { active, setActive, onCellKeyDown } = useKeyboardNav({
    rowCount,
    columnCount: colCount,
    isEnabled,
    initial: initialActive,
  });

  useEffect(() => {
    onActiveChange?.(active);
  }, [active, onActiveChange]);

  const { handlePaste } = useClipboardPaste({
    rowCount,
    columnCount: colCount,
    isEnabled,
    writeCell: onCellChange,
  });

  // Focus management — when `active` changes, focus the corresponding input.
  const cellRefs = useRef<Map<string, HTMLInputElement | null>>(new Map());
  useEffect(() => {
    const key = `${active.row}:${active.col}`;
    const node = cellRefs.current.get(key);
    if (node && document.activeElement !== node) {
      node.focus();
      node.select();
    }
  }, [active]);

  // Build the column-group header row (PRD §7.3 grouped Projected / Actual).
  const groupHeaders = useMemo(() => {
    const groups: { label: string; span: number }[] = [];
    for (const col of columns) {
      const last = groups[groups.length - 1];
      const label = col.group ?? "";
      if (last && last.label === label) last.span += 1;
      else groups.push({ label, span: 1 });
    }
    return groups;
  }, [columns]);

  return (
    <div className="overflow-x-auto rounded border border-slate-200 bg-white">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            <th
              rowSpan={2}
              className="sticky left-0 z-10 border-b border-r border-slate-200 bg-slate-50 px-3 py-2 text-left font-medium text-slate-600"
            >
              Week
            </th>
            {groupHeaders.map((g, i) => (
              <th
                key={`g${i}`}
                colSpan={g.span}
                className="border-b border-slate-200 bg-slate-50 px-3 py-1 text-center text-xs font-semibold uppercase tracking-wide text-slate-500"
              >
                {g.label}
              </th>
            ))}
          </tr>
          <tr>
            {columns.map((c) => (
              <th
                key={c.id}
                className="border-b border-slate-200 bg-slate-50 px-3 py-1 text-left text-xs font-medium text-slate-600"
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rIdx) => {
            const rowCls = rowClassName?.(row, rIdx) ?? "";
            const showDividerBelow = dividerAfterRow === rIdx;
            return (
              <tr
                key={rIdx}
                className={`${rowCls} ${showDividerBelow ? "border-b-2 border-slate-400" : ""}`}
                data-testid={`grid-row-${rIdx}`}
              >
                <th
                  className="sticky left-0 z-10 border-r border-slate-200 bg-white px-3 py-1.5 text-left font-medium text-slate-700"
                  scope="row"
                >
                  {rowHeader(row, rIdx)}
                </th>
                {columns.map((col, cIdx) => {
                  const state = cellState(row, rIdx, col.id);
                  const isActive = active.row === rIdx && active.col === cIdx;
                  const baseCls =
                    "border-b border-slate-100 px-1.5 py-1.5 align-middle";
                  if (state.kind === "disabled") {
                    return (
                      <td
                        key={col.id}
                        className={`${baseCls} bg-slate-50 text-slate-400`}
                        data-testid={`cell-${rIdx}-${col.id}`}
                        data-disabled="true"
                        data-reason={state.reason ?? ""}
                      >
                        <span className="block px-1.5 py-1">
                          {col.accessor(row) ?? "—"}
                        </span>
                      </td>
                    );
                  }
                  const value = state.value;
                  return (
                    <td
                      key={col.id}
                      className={`${baseCls} ${isActive ? "bg-blue-50 ring-1 ring-blue-300" : ""}`}
                      data-testid={`cell-${rIdx}-${col.id}`}
                    >
                      <input
                        ref={(n) => {
                          cellRefs.current.set(`${rIdx}:${cIdx}`, n);
                        }}
                        type="text"
                        inputMode="numeric"
                        className="w-full bg-transparent px-1.5 py-1 text-right outline-none"
                        value={value ?? ""}
                        onFocus={() => setActive({ row: rIdx, col: cIdx })}
                        onChange={(e) => {
                          const raw = e.target.value.trim();
                          if (raw === "") {
                            onCellChange({ row: rIdx, col: cIdx }, null);
                            return;
                          }
                          const n = Number(raw.replace(/,/g, ""));
                          if (Number.isFinite(n)) {
                            onCellChange({ row: rIdx, col: cIdx }, n);
                          }
                        }}
                        onKeyDown={(e) =>
                          onCellKeyDown(e, { row: rIdx, col: cIdx })
                        }
                        onPaste={(e) =>
                          handlePaste(e, { row: rIdx, col: cIdx })
                        }
                        data-testid={`input-${rIdx}-${col.id}`}
                      />
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
