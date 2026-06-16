import { describe, expect, it } from "vitest";
import { bandClasses, classifyUtil } from "../utilization";

const THRESHOLDS = { green_max_pct: 70, amber_max_pct: 95 };

describe("classifyUtil", () => {
  it("returns 'none' for null", () => {
    expect(classifyUtil(null, THRESHOLDS)).toBe("none");
  });

  it("returns 'green' when util ≤ green_max", () => {
    expect(classifyUtil(0.5, THRESHOLDS)).toBe("green");
    expect(classifyUtil(0.7, THRESHOLDS)).toBe("green");
  });

  it("returns 'amber' between green_max and amber_max", () => {
    expect(classifyUtil(0.71, THRESHOLDS)).toBe("amber");
    expect(classifyUtil(0.95, THRESHOLDS)).toBe("amber");
  });

  it("returns 'red' between amber_max and 100%", () => {
    expect(classifyUtil(0.96, THRESHOLDS)).toBe("red");
    expect(classifyUtil(1.0, THRESHOLDS)).toBe("red");
  });

  it("returns 'critical' over 100%", () => {
    expect(classifyUtil(1.01, THRESHOLDS)).toBe("critical");
    expect(classifyUtil(2.0, THRESHOLDS)).toBe("critical");
  });
});

describe("bandClasses", () => {
  it("maps every band to a class string", () => {
    expect(bandClasses("green")).toContain("emerald");
    expect(bandClasses("amber")).toContain("amber");
    expect(bandClasses("red")).toContain("red");
    expect(bandClasses("critical")).toContain("red");
    expect(bandClasses("none")).toContain("slate");
  });
});
