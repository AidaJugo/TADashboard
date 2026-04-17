/**
 * Symphony design tokens.
 *
 * Source of truth for colour, typography, and spacing.
 * Rules: see .cursor/skills/symphony-design/SKILL.md.
 *
 * - Text is only `black` or `white`.
 * - Secondary palette is for accents, never surfaces or body text.
 * - Never hardcode these values anywhere else in the app.
 */

export const tokens = {
  colors: {
    primary: "#6c69ff",
    red: "#fe7475",
    yellow: "#ffbe3d",
    lightGrey: "#f4f5fb",
    black: "#000000",
    white: "#ffffff",

    navy: "#222453",
    lightBlue: "#91afea",
    blueGrey: "#9fabc0",
    peach: "#f9dfc4",
  },
  typography: {
    fontFamily:
      '"Poppins", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
    heading: {
      h1: { size: 72, weight: 700 },
      h2: { size: 48, weight: 700 },
      h3: { size: 36, weight: 600 },
      h4: { size: 30, weight: 500 },
    },
    body: { size: 16, weight: 400, lineHeight: 23 },
    tag: { size: 20, weight: 700 },
    cta: { size: 30, weight: 700 },
  },
  spacing: {
    xs: 4,
    sm: 8,
    md: 16,
    lg: 24,
    xl: 32,
    xxl: 48,
  },
  radius: {
    sm: 4,
    md: 8,
    lg: 16,
  },
} as const;

export type Tokens = typeof tokens;
