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
      // DangerZone (post-P6) fans out to list sites + trials.
      listSites: vi.fn(),
      listTrials: vi.fn(),
      getSiteDeleteImpact: vi.fn(),
      getTrialDeleteImpact: vi.fn(),
      archiveTrial: vi.fn(),
      deleteSite: vi.fn(),
      deleteTrial: vi.fn(),
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
  (api.listSites as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (api.listTrials as ReturnType<typeof vi.fn>).mockResolvedValue([]);
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

  it("danger zone: opening a trial delete shows the active-block when status=active", async () => {
    // Active trials must not be deletable — the modal renders an Archive
    // affordance instead of the type-to-confirm flow.
    (api.listTrials as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "t1",
        name: "ACTIVE-T",
        status: "active",
        fpfv: "2026-09-07",
        lpfv: "2027-09-06",
        lplv: "2028-09-04",
        is_multi_arm: false,
        enrollment_target: 100,
        screening_target: 125,
        attrition_curve_id: null,
      },
    ]);
    (api.getTrialDeleteImpact as ReturnType<typeof vi.fn>).mockResolvedValue({
      trial_name: "ACTIVE-T",
      status: "active",
      arms: 1,
      visits: 5,
      site_assignments: 2,
      enrollment_weeks: 10,
      soa_snapshots: 1,
    });

    renderPage(ADMIN);
    const deleteBtn = await screen.findByTestId("danger-trial-delete-t1");
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(screen.getByTestId("danger-trial-modal")).toBeInTheDocument();
    });
    // Active block visible.
    expect(
      await screen.findByTestId("danger-trial-active-block"),
    ).toBeInTheDocument();
    // Confirm button stays disabled (no type-to-confirm input rendered).
    expect(screen.queryByTestId("danger-trial-type-confirm")).toBeNull();
    // The Archive affordance is present.
    expect(screen.getByTestId("danger-trial-archive")).toBeInTheDocument();
  });

  it("danger zone: deleting a site requires typing the site name", async () => {
    (api.listSites as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "s1", name: "Alpha Site", timezone: "UTC", operating_weekdays: [0], hours_per_day: 10, rooms: 1 },
    ]);
    (api.getSiteDeleteImpact as ReturnType<typeof vi.fn>).mockResolvedValue({
      site_name: "Alpha Site",
      trial_assignments: 0,
      enrollment_weeks: 0,
      user_assignments: 0,
    });

    renderPage(ADMIN);
    const deleteBtn = await screen.findByTestId("danger-site-delete-s1");
    fireEvent.click(deleteBtn);

    const confirm = await screen.findByTestId("confirm-delete-button");
    expect(confirm).toBeDisabled();

    const input = screen.getByTestId("danger-site-type-confirm");
    fireEvent.change(input, { target: { value: "Alpha Site" } });
    await waitFor(() => {
      expect(screen.getByTestId("confirm-delete-button")).not.toBeDisabled();
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
