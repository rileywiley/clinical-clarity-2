import { describe, expect, it } from "vitest";
import { paletteSize, trialColor } from "../trialColors";

describe("trialColor", () => {
  it("returns the same color for the same trial_id", () => {
    const id = "11111111-2222-3333-4444-555555555555";
    expect(trialColor(id)).toBe(trialColor(id));
  });

  it("returns a color from the palette", () => {
    const id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
    const c = trialColor(id);
    expect(c).toMatch(/^#[0-9a-f]{6}$/);
  });

  it("distributes across the palette for varied inputs", () => {
    const colors = new Set<string>();
    for (let i = 0; i < 50; i++) {
      colors.add(trialColor(`trial-${i}`));
    }
    // Not perfect uniformity but should hit several distinct slots.
    expect(colors.size).toBeGreaterThan(3);
    expect(colors.size).toBeLessThanOrEqual(paletteSize());
  });
});
