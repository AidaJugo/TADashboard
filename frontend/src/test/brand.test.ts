/**
 * Brand design-system conformance tests (TC-U-BRAND-1..5).
 *
 * These tests assert invariants over the token file and the component source
 * files themselves so design-system constraints are caught at CI time, not
 * in visual review.
 *
 * TC-U-BRAND-1: No hardcoded hex literals in component files.
 * TC-U-BRAND-2: All colour references in components resolve to token paths.
 * TC-U-BRAND-3: No Google Fonts or CDN references in frontend/.
 * TC-U-BRAND-4: tokens.ts matches the PRD palette and typography scale.
 * TC-U-BRAND-5: Colour contrast of token combinations meets WCAG AA.
 */

import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "fs";
import { join } from "path";
import { tokens } from "@/theme/tokens";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SRC = join(__dirname, "..");

function globComponents(): string[] {
  const files: string[] = [];
  function walk(dir: string) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (/\.(tsx|ts|css|scss)$/.test(entry.name) && !entry.name.includes(".test.")) {
        files.push(full);
      }
    }
  }
  walk(SRC);
  return files;
}

function readAll(): Array<{ path: string; content: string }> {
  return globComponents().map((p) => ({ path: p, content: readFileSync(p, "utf-8") }));
}

/**
 * WCAG relative luminance for a hex colour (IEC 61966-2-1).
 */
function relativeLuminance(hex: string): number {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16) / 255;
  const g = parseInt(h.slice(2, 4), 16) / 255;
  const b = parseInt(h.slice(4, 6), 16) / 255;
  function linearise(c: number) {
    return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  }
  return 0.2126 * linearise(r) + 0.7152 * linearise(g) + 0.0722 * linearise(b);
}

function contrastRatio(hex1: string, hex2: string): number {
  const l1 = relativeLuminance(hex1);
  const l2 = relativeLuminance(hex2);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

// ---------------------------------------------------------------------------
// TC-U-BRAND-1: no hardcoded hex literals in component/page/hook files
// ---------------------------------------------------------------------------

describe("TC-U-BRAND-1: no hardcoded hex literals in component files", () => {
  it("finds no #rrggbb or #rrggbbaa literals outside theme/", () => {
    const HEX_RE = /#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?\b/g;

    const violations: string[] = [];
    for (const { path, content } of readAll()) {
      // The theme files are allowed to define the values; only components/pages/hooks/api are checked.
      if (path.includes("/theme/")) continue;

      const matches = content.match(HEX_RE) ?? [];
      for (const m of matches) {
        violations.push(`${path}: ${m}`);
      }
    }

    expect(violations, `Hardcoded hex literals found:\n${violations.join("\n")}`).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// TC-U-BRAND-2: text colour only tokens.colors.black or tokens.colors.white
// ---------------------------------------------------------------------------

describe("TC-U-BRAND-2: text colour resolves to black or white tokens only", () => {
  it("tokens.colors.black and tokens.colors.white are pure black/white", () => {
    expect(tokens.colors.black).toBe("#000000");
    expect(tokens.colors.white).toBe("#ffffff");
  });

  it("no component file uses a secondary token as the CSS `color` property", () => {
    /**
     * Scans all component/page/hook TSX files for inline `color:` assignments
     * that reference any token other than tokens.colors.black or tokens.colors.white.
     *
     * Pattern: `\bcolor:\s*tokens\.colors\.` followed by anything that is NOT
     * `black` or `white`.  Uses a word-boundary before `color` so `borderColor`
     * and `backgroundColor` are not flagged.
     *
     * Exempt: theme/ files (they define the values), test files.
     */
    const SECONDARY_AS_TEXT = /\bcolor:\s*tokens\.colors\.(?!black\b|white\b)/g;
    const violations: string[] = [];

    for (const { path, content } of readAll()) {
      if (path.includes("/theme/")) continue;
      const matches = content.match(SECONDARY_AS_TEXT) ?? [];
      for (const m of matches) {
        violations.push(`${path}: ${m.trim()}`);
      }
    }

    expect(
      violations,
      `Secondary token used as text colour (FR-BRAND-5):\n${violations.join("\n")}`,
    ).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// TC-U-BRAND-3: no CDN font references
// ---------------------------------------------------------------------------

describe("TC-U-BRAND-3: no Google Fonts or CDN references in frontend source", () => {
  const CDN_RE = /fonts\.googleapis\.com|cdn\.jsdelivr\.net|fonts\.gstatic\.com/;

  it("finds no CDN font URLs in any source file", () => {
    const violations: string[] = [];
    for (const { path, content } of readAll()) {
      if (CDN_RE.test(content)) {
        violations.push(path);
      }
    }
    expect(violations, `CDN font references found:\n${violations.join("\n")}`).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// TC-U-BRAND-4: token snapshot matches PRD palette and typography scale
// ---------------------------------------------------------------------------

describe("TC-U-BRAND-4: design token snapshot", () => {
  it("core palette matches PRD §7.7", () => {
    expect(tokens.colors.primary).toBe("#6c69ff");
    expect(tokens.colors.red).toBe("#fe7475");
    expect(tokens.colors.yellow).toBe("#ffbe3d");
    expect(tokens.colors.lightGrey).toBe("#f4f5fb");
    expect(tokens.colors.black).toBe("#000000");
    expect(tokens.colors.white).toBe("#ffffff");
  });

  it("secondary palette matches PRD §7.7", () => {
    expect(tokens.colors.navy).toBe("#222453");
    expect(tokens.colors.lightBlue).toBe("#91afea");
    expect(tokens.colors.blueGrey).toBe("#9fabc0");
    expect(tokens.colors.peach).toBe("#f9dfc4");
  });

  it("typography scale matches PRD §7.7", () => {
    expect(tokens.typography.heading.h1).toMatchObject({ size: 72, weight: 700 });
    expect(tokens.typography.heading.h2).toMatchObject({ size: 48, weight: 700 });
    expect(tokens.typography.heading.h3).toMatchObject({ size: 36, weight: 600 });
    expect(tokens.typography.heading.h4).toMatchObject({ size: 30, weight: 500 });
    expect(tokens.typography.body).toMatchObject({ size: 16, weight: 400, lineHeight: 23 });
    expect(tokens.typography.tag).toMatchObject({ size: 20, weight: 700 });
    expect(tokens.typography.cta).toMatchObject({ size: 30, weight: 700 });
  });

  it("font family includes Poppins as first choice", () => {
    expect(tokens.typography.fontFamily).toMatch(/^"Poppins"/);
  });
});

// ---------------------------------------------------------------------------
// TC-U-BRAND-5: WCAG AA contrast for primary text-on-background token combos
// ---------------------------------------------------------------------------

describe("TC-U-BRAND-5: WCAG AA colour contrast", () => {
  const WCAG_AA_NORMAL = 4.5;
  const WCAG_AA_LARGE = 3.0;

  it("black text on white surface meets AA (≥4.5:1)", () => {
    const ratio = contrastRatio(tokens.colors.black, tokens.colors.white);
    expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_NORMAL);
  });

  it("white text on navy meets AA large text (≥3:1)", () => {
    const ratio = contrastRatio(tokens.colors.white, tokens.colors.navy);
    expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_LARGE);
  });

  it("black text on lightGrey meets AA (≥4.5:1)", () => {
    const ratio = contrastRatio(tokens.colors.black, tokens.colors.lightGrey);
    expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_NORMAL);
  });

  it("white text on primary purple meets AA large text (≥3:1)", () => {
    const ratio = contrastRatio(tokens.colors.white, tokens.colors.primary);
    expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_LARGE);
  });

  it("black text on yellow meets AA (≥4.5:1)", () => {
    const ratio = contrastRatio(tokens.colors.black, tokens.colors.yellow);
    expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_NORMAL);
  });
});
