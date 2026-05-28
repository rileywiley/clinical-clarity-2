/**
 * Phase 3 first-class acceptance criteria (PRD §7.3).
 *
 * Each behavior gets its own test:
 *   - Tab / Shift-Tab horizontal nav
 *   - Enter / Shift-Enter vertical nav
 *   - Arrow keys in all four directions
 *   - Disabled cells skipped during keyboard movement
 *   - Clipboard paste fills a block from the active cell
 *   - Disabled cells skipped during paste too
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { SpreadsheetGrid } from "../SpreadsheetGrid";
import type { CellCoord, CellState, ColumnSpec } from "../types";

type Row = {
  key: string;
  a: number | null;
  b: number | null;
  c: number | null;
  d: number | null;
};

const COLUMNS: ColumnSpec<Row>[] = [
  { id: "a", header: "A", group: "Left", accessor: (r) => r.a },
  { id: "b", header: "B", group: "Left", accessor: (r) => r.b },
  { id: "c", header: "C", group: "Right", accessor: (r) => r.c },
  { id: "d", header: "D", group: "Right", accessor: (r) => r.d },
];

const ROWS: Row[] = [
  { key: "r0", a: 1, b: 2, c: 3, d: 4 },
  { key: "r1", a: 5, b: 6, c: 7, d: 8 },
  { key: "r2", a: 9, b: 10, c: 11, d: 12 },
];

function allEnabled(_row: Row, _ri: number, columnId: string): CellState {
  const accessor = COLUMNS.find((c) => c.id === columnId)!.accessor;
  return { kind: "editable", value: accessor(_row) };
}

function activeCoord(): CellCoord {
  // The grid surfaces the active cell via the input that has focus.
  const focused = document.activeElement;
  if (!focused || focused.tagName !== "INPUT") {
    throw new Error("no input focused");
  }
  const id = focused.getAttribute("data-testid") ?? "";
  // input-<row>-<colId>
  const m = id.match(/^input-(\d+)-([a-z_]+)$/);
  if (!m) throw new Error(`unexpected testid: ${id}`);
  const row = parseInt(m[1], 10);
  const col = COLUMNS.findIndex((c) => c.id === m[2]);
  return { row, col };
}

function renderGrid(opts?: {
  cellState?: (r: Row, i: number, col: string) => CellState;
  onCellChange?: (c: CellCoord, v: number | null) => void;
}) {
  return render(
    <SpreadsheetGrid
      rows={ROWS}
      columns={COLUMNS}
      rowHeader={(r) => r.key}
      cellState={opts?.cellState ?? allEnabled}
      onCellChange={opts?.onCellChange ?? (() => {})}
    />,
  );
}

describe("SpreadsheetGrid keyboard nav", () => {
  it("Tab moves right; Shift-Tab moves left", () => {
    renderGrid();
    const start = screen.getByTestId("input-0-a") as HTMLInputElement;
    start.focus();
    expect(activeCoord()).toEqual({ row: 0, col: 0 });

    fireEvent.keyDown(start, { key: "Tab" });
    expect(activeCoord()).toEqual({ row: 0, col: 1 });

    const next = document.activeElement as HTMLInputElement;
    fireEvent.keyDown(next, { key: "Tab", shiftKey: true });
    expect(activeCoord()).toEqual({ row: 0, col: 0 });
  });

  it("Enter moves down; Shift-Enter moves up", () => {
    renderGrid();
    const start = screen.getByTestId("input-1-b") as HTMLInputElement;
    start.focus();
    fireEvent.keyDown(start, { key: "Enter" });
    expect(activeCoord()).toEqual({ row: 2, col: 1 });

    fireEvent.keyDown(document.activeElement!, { key: "Enter", shiftKey: true });
    expect(activeCoord()).toEqual({ row: 1, col: 1 });
  });

  it("Arrow keys move in all four directions", () => {
    renderGrid();
    const start = screen.getByTestId("input-1-b") as HTMLInputElement;
    start.focus();

    fireEvent.keyDown(start, { key: "ArrowRight" });
    expect(activeCoord()).toEqual({ row: 1, col: 2 });

    fireEvent.keyDown(document.activeElement!, { key: "ArrowDown" });
    expect(activeCoord()).toEqual({ row: 2, col: 2 });

    fireEvent.keyDown(document.activeElement!, { key: "ArrowLeft" });
    expect(activeCoord()).toEqual({ row: 2, col: 1 });

    fireEvent.keyDown(document.activeElement!, { key: "ArrowUp" });
    expect(activeCoord()).toEqual({ row: 1, col: 1 });
  });

  it("skips disabled cells during keyboard movement", () => {
    // Disable column 'b' on row 0 only.
    const cellState = (r: Row, ri: number, col: string): CellState => {
      if (ri === 0 && col === "b") return { kind: "disabled", reason: "out-of-range" };
      const accessor = COLUMNS.find((c) => c.id === col)!.accessor;
      return { kind: "editable", value: accessor(r) };
    };
    renderGrid({ cellState });

    const start = screen.getByTestId("input-0-a") as HTMLInputElement;
    start.focus();
    fireEvent.keyDown(start, { key: "Tab" });
    // Should hop OVER (0,b) directly to (0,c).
    expect(activeCoord()).toEqual({ row: 0, col: 2 });
  });

  it("stops at the grid edge instead of wrapping", () => {
    renderGrid();
    const last = screen.getByTestId("input-2-d") as HTMLInputElement;
    last.focus();
    fireEvent.keyDown(last, { key: "ArrowRight" });
    expect(activeCoord()).toEqual({ row: 2, col: 3 }); // unchanged — no enabled cell to the right
  });
});

describe("SpreadsheetGrid clipboard paste", () => {
  it("fills a 2x3 block from the active cell", () => {
    const writes: { coord: CellCoord; value: number | null }[] = [];
    renderGrid({ onCellChange: (c, v) => writes.push({ coord: c, value: v }) });
    const start = screen.getByTestId("input-0-b") as HTMLInputElement;
    start.focus();

    fireEvent.paste(start, {
      clipboardData: { getData: () => "100\t200\n300\t400" },
    });

    expect(writes).toEqual([
      { coord: { row: 0, col: 1 }, value: 100 },
      { coord: { row: 0, col: 2 }, value: 200 },
      { coord: { row: 1, col: 1 }, value: 300 },
      { coord: { row: 1, col: 2 }, value: 400 },
    ]);
  });

  it("skips disabled cells during paste", () => {
    const writes: { coord: CellCoord; value: number | null }[] = [];
    const cellState = (r: Row, ri: number, col: string): CellState => {
      if (ri === 0 && col === "c") return { kind: "disabled", reason: "out-of-range" };
      const accessor = COLUMNS.find((c) => c.id === col)!.accessor;
      return { kind: "editable", value: accessor(r) };
    };
    renderGrid({
      cellState,
      onCellChange: (c, v) => writes.push({ coord: c, value: v }),
    });
    const start = screen.getByTestId("input-0-b") as HTMLInputElement;
    start.focus();

    fireEvent.paste(start, {
      clipboardData: { getData: () => "100\t200" },
    });

    // (0,b) gets 100; (0,c) is disabled and gets skipped.
    expect(writes).toEqual([{ coord: { row: 0, col: 1 }, value: 100 }]);
  });
});

describe("SpreadsheetGrid rendering", () => {
  it("renders the column-group header above grouped columns", () => {
    renderGrid();
    // Two groups: Left (spans A+B), Right (spans C+D).
    expect(screen.getByText("Left")).toBeInTheDocument();
    expect(screen.getByText("Right")).toBeInTheDocument();
  });

  it("renders disabled cells without an input element", () => {
    const cellState = (r: Row, ri: number, col: string): CellState => {
      if (ri === 0 && col === "a") return { kind: "disabled", reason: "past-locked" };
      const accessor = COLUMNS.find((c) => c.id === col)!.accessor;
      return { kind: "editable", value: accessor(r) };
    };
    renderGrid({ cellState });

    const cell = screen.getByTestId("cell-0-a");
    expect(cell).toHaveAttribute("data-disabled", "true");
    expect(within(cell).queryByRole("textbox")).toBeNull();
  });

  it("calls onCellChange on input", () => {
    const onCellChange = vi.fn();
    renderGrid({ onCellChange });
    const input = screen.getByTestId("input-1-c") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "42" } });
    expect(onCellChange).toHaveBeenCalledWith({ row: 1, col: 2 }, 42);
  });

  it("draws a divider after the given row index", () => {
    render(
      <SpreadsheetGrid
        rows={ROWS}
        columns={COLUMNS}
        rowHeader={(r) => r.key}
        cellState={allEnabled}
        onCellChange={() => {}}
        dividerAfterRow={1}
      />,
    );
    expect(screen.getByTestId("grid-row-1").className).toMatch(/border-b-2/);
  });
});
