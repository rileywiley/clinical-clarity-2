/**
 * ScopeToggle — the active/planned/combined reporting selector (PRD §6.9).
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { ScopeToggle } from "../ScopeToggle";

describe("ScopeToggle", () => {
  it("renders all three scopes and marks the selected one pressed", () => {
    render(<ScopeToggle value="active" onChange={() => {}} />);
    expect(screen.getByTestId("scope-active")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("scope-planned")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("scope-combined")).toHaveAttribute("aria-pressed", "false");
  });

  it("fires onChange with the clicked scope", () => {
    const onChange = vi.fn();
    render(<ScopeToggle value="active" onChange={onChange} />);
    fireEvent.click(screen.getByTestId("scope-planned"));
    expect(onChange).toHaveBeenCalledWith("planned");
    fireEvent.click(screen.getByTestId("scope-combined"));
    expect(onChange).toHaveBeenCalledWith("combined");
  });
});
