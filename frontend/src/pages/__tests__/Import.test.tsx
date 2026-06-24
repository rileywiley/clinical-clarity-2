/**
 * Bulk CSV import page — minimum-viable coverage:
 *   - non-admin sees a polite refusal
 *   - preview errors disable the Commit button
 *   - preview-ok then commit calls api.commitImport and shows the success panel
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import Import from "../Import";
import type { Me } from "../../api";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    api: {
      importTemplateUrl: (k: string) => `/api/imports/templates/${k}.csv`,
      previewImport: vi.fn(),
      commitImport: vi.fn(),
    },
  };
});

import { api } from "../../api";

const ADMIN: Me = {
  user_id: "u1",
  email: "a@a.example.com",
  name: "Admin",
  role: "org_admin",
  org_id: "o1",
};
const VIEWER: Me = { ...ADMIN, role: "viewer" };

function renderPage(me: Me) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Import me={me} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function pickFile(testid: string) {
  const input = screen.getByTestId(testid) as HTMLInputElement;
  const file = new File(["name,timezone\nFoo,UTC\n"], "sites.csv", {
    type: "text/csv",
  });
  fireEvent.change(input, { target: { files: [file] } });
}

beforeEach(() => {
  (api.previewImport as ReturnType<typeof vi.fn>).mockReset();
  (api.commitImport as ReturnType<typeof vi.fn>).mockReset();
});
afterEach(() => vi.clearAllMocks());

describe("Import page", () => {
  it("shows polite refusal to non-admins", () => {
    renderPage(VIEWER);
    expect(screen.getByText(/only org admins/i)).toBeInTheDocument();
  });

  it("disables Commit when the preview returns errors", async () => {
    (api.previewImport as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      actions: ["Create site 'Foo'"],
      errors: [{ row: 3, message: "hours_per_day: not an integer" }],
    });
    renderPage(ADMIN);
    pickFile("import-sites-file");
    fireEvent.click(screen.getByTestId("import-sites-preview"));

    await waitFor(() => {
      expect(screen.getByTestId("import-sites-errors")).toBeInTheDocument();
    });
    expect(screen.getByTestId("import-sites-commit")).toBeDisabled();
    // The single parseable row is still shown for context.
    expect(screen.getByText(/Create site 'Foo'/)).toBeInTheDocument();
  });

  it("commits when the preview is clean and shows the success panel", async () => {
    (api.previewImport as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      actions: ["Create site 'Foo' (1 rooms × 10h)"],
      errors: [],
    });
    (api.commitImport as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      actions: ["Created site 'Foo'"],
    });
    renderPage(ADMIN);
    pickFile("import-sites-file");
    fireEvent.click(screen.getByTestId("import-sites-preview"));
    await waitFor(() => {
      expect(screen.getByTestId("import-sites-commit")).not.toBeDisabled();
    });
    fireEvent.click(screen.getByTestId("import-sites-commit"));
    await waitFor(() => {
      expect(screen.getByTestId("import-sites-success")).toBeInTheDocument();
    });
    expect(api.commitImport).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Created site 'Foo'/)).toBeInTheDocument();
  });
});
