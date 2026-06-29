/**
 * Breadcrumbs — links every item except the last; last is the current page.
 */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { MemoryRouter } from "react-router-dom";

import { Breadcrumbs } from "../Breadcrumbs";

describe("Breadcrumbs", () => {
  it("renders links for ancestors and plain text for the current page", () => {
    render(
      <MemoryRouter>
        <Breadcrumbs
          items={[
            { label: "Network", to: "/" },
            { label: "Site A", to: "/sites/a" },
            { label: "Projections" },
          ]}
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Network" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Site A" })).toHaveAttribute("href", "/sites/a");
    // The current page is not a link.
    expect(screen.queryByRole("link", { name: "Projections" })).toBeNull();
    expect(screen.getByText("Projections")).toHaveAttribute("aria-current", "page");
  });
});
