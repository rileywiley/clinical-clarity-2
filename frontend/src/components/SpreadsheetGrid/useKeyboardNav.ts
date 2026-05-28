/**
 * Keyboard navigation for the spreadsheet primitive (PRD §7.3).
 *
 * First-class acceptance criteria per the PRD:
 *   - Tab / Shift-Tab move horizontally
 *   - Enter / Shift-Enter move vertically
 *   - Arrow keys move in all four directions
 *   - Disabled cells are SKIPPED during keyboard movement (not just unfocusable —
 *     the cursor lands on the next *enabled* cell beyond the disabled one)
 *
 * The hook is "headless" — it doesn't render anything. It owns the active-cell
 * state, listens for keys, and returns helpers the grid uses to wire up DOM
 * focus and onChange handlers.
 */

import { useCallback, useState } from "react";
import type { CellCoord, CellState } from "./types";

export type NavApi = {
  active: CellCoord;
  setActive: (c: CellCoord) => void;
  /**
   * Compute the next coord in a given direction, skipping disabled cells.
   * Returns null if no enabled cell exists in that direction.
   */
  step: (from: CellCoord, dir: "up" | "down" | "left" | "right") => CellCoord | null;
  /** Bind to a cell's onKeyDown. The cell tells the hook which (row, col) it is. */
  onCellKeyDown: (
    e: React.KeyboardEvent,
    coord: CellCoord,
  ) => void;
};

export type UseKeyboardNavOptions = {
  rowCount: number;
  columnCount: number;
  /**
   * Returns whether a given cell is reachable by keyboard. Disabled cells
   * return false; the nav helpers will skip past them.
   */
  isEnabled: (row: number, col: number) => boolean;
  /** Initial active cell. Defaults to (0, 0). */
  initial?: CellCoord;
};

export function useKeyboardNav({
  rowCount,
  columnCount,
  isEnabled,
  initial = { row: 0, col: 0 },
}: UseKeyboardNavOptions): NavApi {
  const [active, setActive] = useState<CellCoord>(initial);

  const step = useCallback(
    (from: CellCoord, dir: "up" | "down" | "left" | "right"): CellCoord | null => {
      let { row, col } = from;
      // Walk one step at a time. Stop when we land on an enabled cell or
      // run off the edge of the grid.
      while (true) {
        if (dir === "up") row -= 1;
        else if (dir === "down") row += 1;
        else if (dir === "left") col -= 1;
        else col += 1;

        if (row < 0 || row >= rowCount || col < 0 || col >= columnCount) {
          return null;
        }
        if (isEnabled(row, col)) {
          return { row, col };
        }
      }
    },
    [rowCount, columnCount, isEnabled],
  );

  const onCellKeyDown = useCallback(
    (e: React.KeyboardEvent, coord: CellCoord) => {
      let next: CellCoord | null = null;

      switch (e.key) {
        case "Tab":
          next = step(coord, e.shiftKey ? "left" : "right");
          break;
        case "Enter":
          next = step(coord, e.shiftKey ? "up" : "down");
          break;
        case "ArrowUp":
          next = step(coord, "up");
          break;
        case "ArrowDown":
          next = step(coord, "down");
          break;
        case "ArrowLeft":
          next = step(coord, "left");
          break;
        case "ArrowRight":
          next = step(coord, "right");
          break;
        default:
          return; // let the keystroke through (typing, etc.)
      }

      // We handled it (whether or not we found a next cell). Prevent the
      // browser default — for Tab specifically, this stops focus from
      // escaping the grid.
      e.preventDefault();
      if (next) setActive(next);
    },
    [step],
  );

  return { active, setActive, step, onCellKeyDown };
}

/**
 * Convert a `CellState` to a simple boolean for nav purposes. Exported so
 * tests can use the same logic.
 */
export function cellStateEnabled(state: CellState): boolean {
  return state.kind === "editable";
}
