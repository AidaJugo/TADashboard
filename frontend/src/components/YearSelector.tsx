/**
 * YearSelector — dropdown to switch between available report years.
 *
 * FR-REPORT-8: default is the current calendar year. Hub scope is preserved
 * across the switch (the parent passes the same allowed_hubs).
 *
 * Keyboard-navigable native <select>.
 */

import { tokens } from "@/theme/tokens";

interface YearSelectorProps {
  years: number[];
  selected: number;
  onChange: (year: number) => void;
}

export function YearSelector({ years, selected, onChange }: YearSelectorProps) {
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
      }}
    >
      Year
      <select
        value={selected}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label="Select report year"
        style={{
          fontSize: 13,
          fontFamily: tokens.typography.fontFamily,
          color: tokens.colors.black,
          background: tokens.colors.white,
          border: `1px solid ${tokens.colors.blueGrey}`,
          borderRadius: tokens.radius.sm,
          padding: `4px ${tokens.spacing.sm}px`,
          cursor: "pointer",
        }}
      >
        {years.map((y) => (
          <option key={y} value={y}>
            {y}
          </option>
        ))}
      </select>
    </label>
  );
}
