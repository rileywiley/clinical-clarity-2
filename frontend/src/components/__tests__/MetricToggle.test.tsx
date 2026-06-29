/**
 * MetricToggle — the Hours / Visits chart switch.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { MetricToggle } from "../MetricToggle";

describe("MetricToggle", () => {
  it("marks the active metric and fires onChange for each option", () => {
    const onChange = vi.fn();
    render(<MetricToggle value="hours" onChange={onChange} />);
    expect(screen.getByTestId("metric-hours")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("metric-visits")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("metric-revenue")).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(screen.getByTestId("metric-visits"));
    expect(onChange).toHaveBeenCalledWith("visits");
    fireEvent.click(screen.getByTestId("metric-revenue"));
    expect(onChange).toHaveBeenCalledWith("revenue");
  });
});
