/**
 * Phase 6 — AdminSettings PATCH flow.
 *
 * Mocks `api` end-to-end and verifies:
 *   - Non-admins see the polite refusal (never read settings)
 *   - Admins see the form pre-filled from /org-settings
 *   - Saving forecasting defaults calls patchOrgSettings with the edited fields
 *   - Display defaults block save when green ≥ amber (load-bearing UX guard)
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import AdminSettings from "../AdminSettings";
import type { Me } from "../../api";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    api: {
      getOrgSettings: vi.fn(),
      patchOrgSettings: vi.fn(),
      listAttritionCurves: vi.fn(),
      listUsers: vi.fn(),
      createUser: vi.fn(),
      patchUser: vi.fn(),
    },
  };
});

import { api } from "../../api";

const ADMIN: Me = {
  id: "u1",
  email: "a@a.com",
  name: "Admin",
  role: "org_admin",
  org_id: "o1",
};
const VIEWER: Me = { ...ADMIN, role: "viewer" };

const SETTINGS = {
  id: "s1",
  dur_screening_hours: 1.0,
  dur_randomization_hours: 2.0,
  dur_follow_up_hours: 1.5,
  dur_other_hours: 1.0,
  util_threshold_green_max: 70,
  util_threshold_amber_max: 90,
  default_grid_weeks_visible: 12,
  default_horizon_months: 24,
  default_site_hours_per_day: 10,
  default_attrition_curve_id: null,
  currency: "USD",
};

function renderPage(me: Me) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AdminSettings me={me} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  (api.getOrgSettings as ReturnType<typeof vi.fn>).mockResolvedValue(SETTINGS);
  (api.listAttritionCurves as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (api.listUsers as ReturnType<typeof vi.fn>).mockResolvedValue([
    { id: "u1", email: "a@a.com", name: "Admin", role: "org_admin", active: true },
  ]);
  (api.patchOrgSettings as ReturnType<typeof vi.fn>).mockResolvedValue({ id: "s1" });
});
afterEach(() => vi.clearAllMocks());

describe("AdminSettings", () => {
  it("shows polite refusal to non-admins", () => {
    renderPage(VIEWER);
    expect(screen.getByText(/only org admins/i)).toBeInTheDocument();
    expect(api.getOrgSettings).not.toHaveBeenCalled();
  });

  it("loads settings and saves forecasting defaults via PATCH", async () => {
    renderPage(ADMIN);
    const screeningInput = await screen.findByTestId("dur-screening");
    // Pre-filled from getOrgSettings.
    expect((screeningInput as HTMLInputElement).value).toBe("1");
    fireEvent.change(screeningInput, { target: { value: "1.25" } });
    fireEvent.click(screen.getByTestId("forecasting-save"));
    await waitFor(() => {
      expect(api.patchOrgSettings).toHaveBeenCalledWith(
        expect.objectContaining({ dur_screening_hours: 1.25 }),
      );
    });
  });

  it("blocks display-defaults save when green >= amber", async () => {
    renderPage(ADMIN);
    const green = await screen.findByTestId("util-green");
    const amber = await screen.findByTestId("util-amber");
    fireEvent.change(green, { target: { value: "95" } });
    fireEvent.change(amber, { target: { value: "90" } });
    fireEvent.click(screen.getByTestId("display-save"));
    // patchOrgSettings was not called for the display section.
    await waitFor(() => {
      expect(screen.getByText(/green threshold must be lower/i)).toBeInTheDocument();
    });
    // It may have been called by ForecastingDefaults? No — separate button.
    // We assert it was NOT called for {util_threshold_green_max: 95, ...}.
    const calls = (api.patchOrgSettings as ReturnType<typeof vi.fn>).mock.calls;
    for (const [arg] of calls) {
      expect(arg.util_threshold_green_max).not.toBe(95);
    }
  });
});
