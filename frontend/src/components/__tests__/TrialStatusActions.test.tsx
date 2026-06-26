/**
 * TrialStatusActions — inline draft→planned/active transitions (PRD §7.1).
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { TrialStatusActions } from "../TrialStatusActions";
import type { Me } from "../../api";

const ADMIN: Me = {
  user_id: "u1",
  email: "a@a.example.com",
  name: "Admin",
  role: "org_admin",
  org_id: "o1",
};
const VIEWER: Me = { ...ADMIN, role: "viewer" };

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    api: {
      me: vi.fn(),
      activateTrial: vi.fn(),
      planTrial: vi.fn(),
    },
  };
});

import { api } from "../../api";

function renderActions(
  status: "draft" | "planned" | "active",
  me: Me = ADMIN,
) {
  (api.me as ReturnType<typeof vi.fn>).mockResolvedValue(me);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TrialStatusActions trialId="t1" status={status} variant="panel" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("TrialStatusActions", () => {
  it("offers Activate + Mark planned for a draft trial (admin)", async () => {
    renderActions("draft");
    expect(await screen.findByTestId("trial-activate-t1")).toBeInTheDocument();
    expect(screen.getByTestId("trial-plan-t1")).toBeInTheDocument();
  });

  it("offers only Activate for a planned trial", async () => {
    renderActions("planned");
    expect(await screen.findByTestId("trial-activate-t1")).toBeInTheDocument();
    expect(screen.queryByTestId("trial-plan-t1")).not.toBeInTheDocument();
  });

  it("renders nothing for an active trial", async () => {
    const { container } = renderActions("active");
    // Give the me query a tick to resolve, then assert empty.
    await waitFor(() => expect(api.me).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing for a viewer", async () => {
    const { container } = renderActions("draft", VIEWER);
    await waitFor(() => expect(api.me).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("calls planTrial when Mark planned is clicked", async () => {
    (api.planTrial as ReturnType<typeof vi.fn>).mockResolvedValue({});
    renderActions("draft");
    fireEvent.click(await screen.findByTestId("trial-plan-t1"));
    await waitFor(() => expect(api.planTrial).toHaveBeenCalledWith("t1"));
  });
});
