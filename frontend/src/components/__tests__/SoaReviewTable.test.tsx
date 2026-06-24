/**
 * Phase 5 first-class acceptance criteria for the SoA review table:
 *   - confidence bands map green / amber / red correctly
 *   - red rows BLOCK the Confirm button until touched
 *   - touching a red row clears the block
 *   - the user's edits are what gets passed to onConfirm (not the originals)
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { SoaReviewTable } from "../SoaReviewTable";
import type { ParsedVisitOut } from "../../api";

const FIXTURE: ParsedVisitOut[] = [
  {
    name: "Screening",
    visit_type: "screening",
    target_day_offset: -14,
    window_days: 3,
    confidence: 0.95,
    flagged_reason: null,
  },
  {
    name: "Randomization",
    visit_type: "randomization",
    target_day_offset: 0,
    window_days: 0,
    confidence: 0.99,
    flagged_reason: null,
  },
  {
    name: "FU W4",
    visit_type: "follow_up",
    target_day_offset: 28,
    window_days: 3,
    confidence: 0.7, // amber
    flagged_reason: "window inferred from text",
  },
  {
    name: "PK Sub-study",
    visit_type: "other",
    target_day_offset: 14,
    window_days: 2,
    confidence: 0.45, // red
    flagged_reason: "conditional visit",
  },
];

describe("SoaReviewTable", () => {
  it("colors rows by their original confidence band", () => {
    render(<SoaReviewTable initialVisits={FIXTURE} onConfirm={() => {}} />);
    expect(screen.getByTestId("soa-row-0")).toHaveAttribute("data-original-band", "green");
    expect(screen.getByTestId("soa-row-1")).toHaveAttribute("data-original-band", "green");
    expect(screen.getByTestId("soa-row-2")).toHaveAttribute("data-original-band", "amber");
    expect(screen.getByTestId("soa-row-3")).toHaveAttribute("data-original-band", "red");
  });

  it("blocks Confirm while any red row is untouched", () => {
    render(<SoaReviewTable initialVisits={FIXTURE} onConfirm={() => {}} />);
    const btn = screen.getByTestId("soa-confirm-button");
    expect(btn).toBeDisabled();
    expect(screen.getByTestId("soa-review-blocked")).toBeInTheDocument();
  });

  it("unblocks Confirm once every red row has been touched", () => {
    render(<SoaReviewTable initialVisits={FIXTURE} onConfirm={() => {}} />);
    const redName = screen.getByTestId("soa-row-3-name") as HTMLInputElement;
    // "Touch" the row by editing its name.
    fireEvent.change(redName, { target: { value: "PK Visit (confirmed)" } });

    expect(screen.getByTestId("soa-row-3")).toHaveAttribute("data-touched", "true");
    expect(screen.getByTestId("soa-confirm-button")).toBeEnabled();
    expect(screen.queryByTestId("soa-review-blocked")).toBeNull();
  });

  it("passes the user-edited visits (not the originals) to onConfirm", async () => {
    const onConfirm = vi.fn();
    render(<SoaReviewTable initialVisits={FIXTURE} onConfirm={onConfirm} />);

    // Edit the amber row's window.
    const windowInput = screen.getByTestId("soa-row-2-window") as HTMLInputElement;
    fireEvent.change(windowInput, { target: { value: "5" } });
    // Touch the red row so Confirm becomes enabled.
    const redOffset = screen.getByTestId("soa-row-3-offset") as HTMLInputElement;
    fireEvent.change(redOffset, { target: { value: "15" } });

    fireEvent.click(screen.getByTestId("soa-confirm-button"));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    const payload = onConfirm.mock.calls[0][0] as ParsedVisitOut[];
    expect(payload[2].window_days).toBe(5); // user edit, not original 3
    expect(payload[3].target_day_offset).toBe(15); // user edit, not original 14
    // The internal _originalBand / _touched fields are stripped before send.
    expect(Object.keys(payload[0])).not.toContain("_originalBand");
    expect(Object.keys(payload[0])).not.toContain("_touched");
  });

  it("renders the empty state when no visits", () => {
    render(<SoaReviewTable initialVisits={[]} onConfirm={() => {}} />);
    expect(screen.getByText(/Parser returned no visits/i)).toBeInTheDocument();
    expect(screen.getByTestId("soa-confirm-button")).toBeEnabled();
  });

  it("lets the user remove a row", () => {
    render(<SoaReviewTable initialVisits={FIXTURE} onConfirm={() => {}} />);
    expect(screen.getAllByRole("row")).toHaveLength(5); // header + 4 rows
    // Remove the red row (index 3).
    const row = screen.getByTestId("soa-row-3");
    const removeBtn = within(row).getByRole("button", { name: /Remove row 4/i });
    fireEvent.click(removeBtn);
    expect(screen.queryByTestId("soa-row-3")).toBeNull();
    // Confirm is now unblocked because the red row is gone.
    expect(screen.getByTestId("soa-confirm-button")).toBeEnabled();
  });

  it("disables Confirm while saving prop is true", () => {
    render(<SoaReviewTable initialVisits={FIXTURE.slice(0, 2)} onConfirm={() => {}} saving />);
    expect(screen.getByTestId("soa-confirm-button")).toBeDisabled();
    expect(screen.getByTestId("soa-confirm-button")).toHaveTextContent(/Saving/);
  });
});
