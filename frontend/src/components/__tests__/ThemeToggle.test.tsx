/**
 * ThemeToggle — applies the `dark` class on <html> and persists the choice.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { ThemeToggle } from "../ThemeToggle";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});
afterEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});

describe("ThemeToggle", () => {
  it("switches to dark: adds the class and persists", () => {
    render(<ThemeToggle />);
    fireEvent.click(screen.getByTestId("theme-dark"));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("theme")).toBe("dark");
    expect(screen.getByTestId("theme-dark")).toHaveAttribute("aria-pressed", "true");
  });

  it("switches back to light: removes the class and persists", () => {
    localStorage.setItem("theme", "dark");
    render(<ThemeToggle />);
    fireEvent.click(screen.getByTestId("theme-light"));
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem("theme")).toBe("light");
    expect(screen.getByTestId("theme-light")).toHaveAttribute("aria-pressed", "true");
  });
});
