/**
 * Unit tests for the TSV paste parser. These don't touch React — they exercise
 * the pure parsing logic that the paste hook calls.
 */

import { describe, expect, it } from "vitest";
import { parseTSV, parseCellValue } from "../useClipboardPaste";

describe("parseTSV", () => {
  it("parses a 2x3 block", () => {
    const text = "10\t20\t30\n40\t50\t60";
    expect(parseTSV(text)).toEqual([
      ["10", "20", "30"],
      ["40", "50", "60"],
    ]);
  });

  it("strips a single trailing newline", () => {
    expect(parseTSV("1\t2\n3\t4\n")).toEqual([
      ["1", "2"],
      ["3", "4"],
    ]);
  });

  it("normalises CRLF to LF", () => {
    expect(parseTSV("1\t2\r\n3\t4")).toEqual([
      ["1", "2"],
      ["3", "4"],
    ]);
  });

  it("treats empty input as zero rows", () => {
    expect(parseTSV("")).toEqual([]);
  });

  it("preserves empty cells", () => {
    expect(parseTSV("1\t\t3")).toEqual([["1", "", "3"]]);
  });
});

describe("parseCellValue", () => {
  it("returns null for empty", () => {
    expect(parseCellValue("")).toBeNull();
    expect(parseCellValue("  ")).toBeNull();
  });

  it("parses plain integers", () => {
    expect(parseCellValue("42")).toBe(42);
    expect(parseCellValue("0")).toBe(0);
  });

  it("strips thousands commas (Excel default)", () => {
    expect(parseCellValue("1,234")).toBe(1234);
    expect(parseCellValue("12,345,678")).toBe(12345678);
  });

  it("returns null for garbage", () => {
    expect(parseCellValue("abc")).toBeNull();
    expect(parseCellValue("12px")).toBeNull();
  });

  it("trims whitespace", () => {
    expect(parseCellValue("  17  ")).toBe(17);
  });
});
