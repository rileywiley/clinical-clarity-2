import { describe, expect, it } from "vitest";
import { fmtCount, fmtHours, fmtMonDay, fmtPct, fmtUsd } from "../formatters";

describe("formatters", () => {
  it("fmtUsd handles whole and null", () => {
    expect(fmtUsd(1500)).toBe("$1,500");
    expect(fmtUsd(null)).toBe("—");
    expect(fmtUsd(undefined)).toBe("—");
  });

  it("fmtPct rounds to whole percent", () => {
    expect(fmtPct(0.5)).toBe("50%");
    expect(fmtPct(null)).toBe("—");
  });

  it("fmtHours one-decimal", () => {
    expect(fmtHours(40)).toBe("40.0 hr");
    expect(fmtHours(null)).toBe("—");
  });

  it("fmtCount keeps integers as-is", () => {
    expect(fmtCount(10)).toBe("10");
    expect(fmtCount(10.5)).toBe("10.5");
    expect(fmtCount(null)).toBe("—");
  });

  it("fmtMonDay renders en-US short date", () => {
    expect(fmtMonDay("2026-06-08")).toBe("Jun 8");
  });
});
