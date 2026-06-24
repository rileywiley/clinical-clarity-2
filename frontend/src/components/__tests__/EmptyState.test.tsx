/**
 * Phase 6 — EmptyState renders title/body and respects the no-print marker.
 * The no-print class is what keeps placeholder cards out of exported PDFs.
 */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { EmptyState } from "../EmptyState";

describe("EmptyState", () => {
  it("renders title and body", () => {
    render(<EmptyState title="No sites yet" body="Add a site to get started." />);
    expect(screen.getByText("No sites yet")).toBeInTheDocument();
    expect(screen.getByText("Add a site to get started.")).toBeInTheDocument();
  });

  it("renders the action when provided", () => {
    render(
      <EmptyState
        title="No trials"
        body="Create one"
        action={<button>+ New trial</button>}
      />,
    );
    expect(screen.getByRole("button", { name: /new trial/i })).toBeInTheDocument();
  });

  it("is marked no-print so it doesn't appear in PDFs", () => {
    const { container } = render(<EmptyState title="x" body="y" />);
    // Root element carries the no-print class.
    expect(container.firstChild).toHaveClass("no-print");
  });
});
