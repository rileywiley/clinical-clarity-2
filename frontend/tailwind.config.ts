import type { Config } from "tailwindcss";

export default {
  darkMode: "class", // toggled via `dark` on <html> (lib/theme.ts)
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {},
  },
  plugins: [],
} satisfies Config;
