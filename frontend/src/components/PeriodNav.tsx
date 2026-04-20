/**
 * PeriodNav — period group (Monthly / Quarterly / Half-Year / Annual) and
 * sub-period selector (Jan, Q1, H1, Annual, etc.).
 *
 * Design: tokens only. No hardcoded hex. Text is tokens.colors.black or white.
 * Keyboard-navigable: all buttons are focusable; active button has aria-pressed.
 */

import { tokens } from "@/theme/tokens";
import { PERIOD_GROUPS } from "./periodConstants";
import type { PeriodGroup } from "./periodConstants";
export type { PeriodGroup } from "./periodConstants";
export { PERIOD_GROUPS };

// ---------------------------------------------------------------------------
// Styles (inline, no hardcoded hex)
// ---------------------------------------------------------------------------

const nav: React.CSSProperties = {
  background: tokens.colors.white,
  borderBottom: `1px solid ${tokens.colors.lightGrey}`,
};

const groupRow: React.CSSProperties = {
  display: "flex",
  gap: 0,
  padding: `0 ${tokens.spacing.xl}px`,
  borderBottom: `1px solid ${tokens.colors.lightGrey}`,
};

const subRow: React.CSSProperties = {
  display: "flex",
  gap: tokens.spacing.xs,
  padding: `${tokens.spacing.sm}px ${tokens.spacing.xl}px`,
  flexWrap: "wrap",
};

function groupBtnStyle(active: boolean): React.CSSProperties {
  return {
    padding: `13px ${tokens.spacing.lg}px`,
    fontSize: 13,
    fontWeight: active ? 600 : 400,
    fontFamily: tokens.typography.fontFamily,
    color: tokens.colors.black,
    background: "none",
    border: "none",
    borderBottom: active ? `2px solid ${tokens.colors.primary}` : "2px solid transparent",
    marginBottom: -1,
    cursor: "pointer",
  };
}

function subBtnStyle(active: boolean, hasData: boolean): React.CSSProperties {
  return {
    padding: `5px 14px`,
    fontSize: 12,
    fontWeight: 500,
    fontFamily: tokens.typography.fontFamily,
    color: active ? tokens.colors.white : tokens.colors.black,
    background: active ? tokens.colors.navy : tokens.colors.lightGrey,
    border: `1px solid ${active ? tokens.colors.navy : tokens.colors.blueGrey}`,
    borderRadius: tokens.radius.lg,
    cursor: hasData ? "pointer" : "default",
    opacity: hasData ? 1 : 0.45,
  };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface PeriodNavProps {
  group: PeriodGroup;
  period: string;
  /** Set of period keys that have data (sub-buttons without data are dimmed). */
  periodsWithData?: Set<string>;
  onGroupChange: (g: PeriodGroup) => void;
  onPeriodChange: (p: string) => void;
}

export function PeriodNav({
  group,
  period,
  periodsWithData,
  onGroupChange,
  onPeriodChange,
}: PeriodNavProps) {
  const current = PERIOD_GROUPS[group];

  return (
    <nav style={nav} aria-label="Period navigation">
      <div style={groupRow} role="tablist">
        {(
          Object.entries(PERIOD_GROUPS) as [PeriodGroup, (typeof PERIOD_GROUPS)[PeriodGroup]][]
        ).map(([key, g]) => (
          <button
            key={key}
            role="tab"
            aria-selected={group === key}
            aria-pressed={group === key}
            style={groupBtnStyle(group === key)}
            onClick={() => onGroupChange(key)}
          >
            {g.label}
          </button>
        ))}
      </div>
      <div style={subRow} role="tabpanel">
        {current.keys.map((k) => {
          const hasData = periodsWithData ? periodsWithData.has(k) : true;
          return (
            <button
              key={k}
              aria-pressed={period === k}
              aria-disabled={!hasData}
              disabled={!hasData}
              style={subBtnStyle(period === k, hasData)}
              onClick={() => hasData && onPeriodChange(k)}
            >
              {current.labels[k]}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
