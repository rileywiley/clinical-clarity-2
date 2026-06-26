/**
 * Light / Dark theme toggle — a small segmented control (same shape as
 * ScopeToggle). Drives lib/theme.ts; the choice persists per browser.
 */

import { useTheme, type Theme } from "../lib/theme";

const OPTIONS: { value: Theme; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  return (
    <div
      className="inline-flex overflow-hidden rounded border border-slate-300"
      role="group"
      aria-label="Theme"
      data-testid="theme-toggle"
    >
      {OPTIONS.map((o) => {
        const selected = theme === o.value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={selected}
            data-testid={`theme-${o.value}`}
            onClick={() => setTheme(o.value)}
            className={
              "px-3 py-1.5 text-sm " +
              (selected
                ? "bg-slate-900 text-white"
                : "bg-white text-slate-600 hover:bg-slate-50")
            }
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
