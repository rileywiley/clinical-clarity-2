/**
 * Types for the headless spreadsheet primitive. Generic over the row shape so
 * Phase 4's network grid can reuse the same component with a different row.
 */

export type CellCoord = { row: number; col: number };

export type CellState =
  | { kind: "editable"; value: number | null }
  | { kind: "disabled"; reason?: "past-locked" | "future-greyed" | "out-of-range" };

/**
 * A function that returns the state of a cell at the given (row, col). The
 * grid consults this for both rendering and keyboard navigation — disabled
 * cells are skipped during nav.
 */
export type CellStateFn<TRow> = (row: TRow, rowIndex: number, columnId: string) => CellState;

export type ColumnSpec<TRow> = {
  /** Stable id used for paste targeting and `cellState` lookup. */
  id: string;
  /** Header label rendered above the column. */
  header: string;
  /** Optional column group header (the "Projected" / "Actual" banner). */
  group?: string;
  /** Pull the current value out of the row. */
  accessor: (row: TRow) => number | null;
};
