/**
 * Studies dashboard grouping — the Planned status appears as its own section
 * (PRD §6.9 / §7.1), distinct from active/draft/archived.
 */

import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import Studies from "../Studies";
import type { TrialOut, TrialStatus } from "../../api";

function trial(id: string, name: string, status: TrialStatus): TrialOut {
  return {
    id,
    name,
    status,
    fpfv: "2026-01-05",
    lpfv: "2027-01-04",
    lplv: "2028-01-03",
    is_multi_arm: false,
    enrollment_target: 100,
    screening_target: 125,
  } as TrialOut;
}

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    api: {
      listTrials: vi.fn(),
      listSites: vi.fn(),
    },
  };
});

import { api } from "../../api";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Studies />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Studies grouping", () => {
  it("renders a Planned section holding only planned trials", async () => {
    (api.listTrials as ReturnType<typeof vi.fn>).mockResolvedValue([
      trial("t1", "Active One", "active"),
      trial("t2", "Planned One", "planned"),
      trial("t3", "Draft One", "draft"),
    ]);
    (api.listSites as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    renderPage();

    const plannedTable = await waitFor(() => screen.getByTestId("studies-planned-table"));
    expect(within(plannedTable).getByText("Planned One")).toBeInTheDocument();
    // The planned trial is not in the active table.
    const activeTable = screen.getByTestId("studies-active-table");
    expect(within(activeTable).queryByText("Planned One")).not.toBeInTheDocument();
    expect(within(activeTable).getByText("Active One")).toBeInTheDocument();
  });
});
