import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        accent: "rgb(var(--color-accent) / <alpha-value>)",
        "accent-bright": "rgb(var(--color-accent-bright) / <alpha-value>)",
        "on-accent": "rgb(var(--color-on-accent) / <alpha-value>)",
        secondary: "rgb(var(--color-secondary) / <alpha-value>)",
        ink: "rgb(var(--color-ink) / <alpha-value>)",
        bg: "rgb(var(--color-bg) / <alpha-value>)",
        surface: "rgb(var(--color-surface) / <alpha-value>)",
        panel: "rgb(var(--color-panel) / <alpha-value>)",
        muted: "rgb(var(--color-muted) / <alpha-value>)",
        line: "rgb(var(--color-line) / <alpha-value>)",
        outline: "rgb(var(--color-outline) / <alpha-value>)",
        success: "rgb(var(--color-success) / <alpha-value>)",
        danger: "rgb(var(--color-danger) / <alpha-value>)",
        warn: "rgb(var(--color-warn) / <alpha-value>)",
        info: "rgb(var(--color-info) / <alpha-value>)",
      },
      fontFamily: {
        // Headings — Clash Display (self-hosted). `display` is the explicit utility;
        // h1–h6 default to it via the base layer in index.css.
        display: ['"Clash Display"', "ui-sans-serif", "system-ui", "sans-serif"],
        // Body — Instrument Sans (also the default body font, set in index.css).
        sans: ['"Instrument Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
        // Technical labels — JetBrains Mono (IDs, serials, status chips, quantities).
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        // The "sticker" effect — a hard, solid offset block (no blur). The block colour
        // is theme-driven (--shadow-color): near-black on light, light outline on dark.
        brutal: "4px 4px 0 0 rgb(var(--shadow-color))",
        "brutal-sm": "2px 2px 0 0 rgb(var(--shadow-color))",
        "brutal-lg": "6px 6px 0 0 rgb(var(--shadow-color))",
      },
      borderRadius: {
        // Soft (0.25rem default) — friendly but blocky, per the design system.
        sm: "0.125rem",
        DEFAULT: "0.25rem",
        md: "0.375rem",
        lg: "0.5rem",
        xl: "0.75rem",
      },
      backgroundSize: {
        blueprint: "32px 32px",
      },
    },
  },
  plugins: [],
} satisfies Config;
