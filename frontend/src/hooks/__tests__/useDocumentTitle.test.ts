/**
 * Phase 6 — useDocumentTitle sets `document.title` with the " · VFP" suffix
 * and restores the previous title on unmount so we don't leak page titles
 * across SPA navigations.
 */

import { afterEach, describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";

import { useDocumentTitle } from "../useDocumentTitle";

afterEach(() => {
  document.title = "";
});

describe("useDocumentTitle", () => {
  it("sets the title with the app suffix", () => {
    renderHook(() => useDocumentTitle("Network forecast"));
    expect(document.title).toBe("Network forecast · VFP");
  });

  it("restores the previous title on unmount", () => {
    document.title = "Original";
    const { unmount } = renderHook(() => useDocumentTitle("Site detail"));
    expect(document.title).toBe("Site detail · VFP");
    unmount();
    expect(document.title).toBe("Original");
  });
});
