/**
 * YoYToggle — toggle for the year-over-year comparison overlay (FR-REPORT-9).
 *
 * When compare_previous_year_missing is true, a "(previous year missing)"
 * marker is displayed alongside the toggle (TC-U-REP-12).
 */

import { tokens } from "@/theme/tokens";

interface YoYToggleProps {
  enabled: boolean;
  previousYearMissing: boolean;
  onChange: (enabled: boolean) => void;
}

export function YoYToggle({ enabled, previousYearMissing, onChange }: YoYToggleProps) {
  return (
    <label
      style={{
        display: "flex",
        alignItems: "center",
        gap: tokens.spacing.sm,
        fontSize: 13,
        fontFamily: tokens.typography.fontFamily,
        color: tokens.colors.white,
        fontWeight: 500,
        cursor: "pointer",
        userSelect: "none",
      }}
    >
      <input
        type="checkbox"
        checked={enabled}
        onChange={(e) => onChange(e.target.checked)}
        aria-label="Compare with previous year"
        style={{ cursor: "pointer" }}
      />
      vs previous year
      {enabled && previousYearMissing && (
        <span
          data-testid="previous-year-missing"
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: tokens.colors.black,
            background: tokens.colors.yellow,
            borderRadius: tokens.radius.sm,
            padding: `2px ${tokens.spacing.sm}px`,
          }}
        >
          previous year missing
        </span>
      )}
    </label>
  );
}
