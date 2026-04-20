/**
 * KpiCardRow — four KPI cards (Total, Below, Above, At Mid + No Salary).
 *
 * Mirrors the prototype's .kpi-grid layout.
 * Colours follow the status mapping in the design skill:
 *   success → primary, warning → yellow, error → red.
 * Text is always tokens.colors.black or white.
 */

import { tokens } from "@/theme/tokens";
import type { KpiBlock } from "@/api/report";

interface KpiCardRowProps {
  kpis: KpiBlock;
  year: number;
  period: string;
}

const grid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(4, 1fr)",
  gap: tokens.spacing.md,
  marginBottom: tokens.spacing.lg,
};

function card(accentColor: string): React.CSSProperties {
  return {
    background: tokens.colors.white,
    borderRadius: tokens.radius.md,
    padding: `${tokens.spacing.md}px ${tokens.spacing.lg}px`,
    border: `1px solid ${tokens.colors.lightGrey}`,
    borderTop: `3px solid ${accentColor}`,
    position: "relative",
  };
}

const label: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: tokens.colors.black,
  textTransform: "uppercase",
  letterSpacing: "0.6px",
  marginBottom: tokens.spacing.sm,
  fontFamily: tokens.typography.fontFamily,
};

const value: React.CSSProperties = {
  fontSize: 34,
  fontWeight: 800,
  color: tokens.colors.black,
  lineHeight: 1,
  fontFamily: tokens.typography.fontFamily,
};

const sub: React.CSSProperties = {
  fontSize: 12,
  color: tokens.colors.black,
  marginTop: tokens.spacing.xs,
  fontFamily: tokens.typography.fontFamily,
};

const split: React.CSSProperties = {
  display: "flex",
  gap: tokens.spacing.md,
  marginTop: tokens.spacing.sm,
};

const splitItem: React.CSSProperties = {
  fontSize: 11,
  color: tokens.colors.black,
  fontFamily: tokens.typography.fontFamily,
};

function Pct({ n }: { n: number }) {
  return (
    <span
      style={{
        fontSize: 13,
        fontWeight: 600,
        marginLeft: 4,
        color: tokens.colors.black,
        fontFamily: tokens.typography.fontFamily,
      }}
    >
      {n}%
    </span>
  );
}

export function KpiCardRow({ kpis }: KpiCardRowProps) {
  return (
    <div style={grid} data-testid="kpi-card-row">
      {/* Total hires */}
      <div style={card(tokens.colors.lightBlue)}>
        <div style={label}>Total new hires</div>
        <div style={value}>{kpis.total}</div>
        <div style={split}>
          <span style={splitItem}>
            WF{" "}
            <strong
              style={{ color: tokens.colors.black, fontFamily: tokens.typography.fontFamily }}
            >
              {kpis.wf}
            </strong>
          </span>
          <span style={splitItem}>
            NonWF{" "}
            <strong
              style={{ color: tokens.colors.black, fontFamily: tokens.typography.fontFamily }}
            >
              {kpis.non_wf}
            </strong>
          </span>
        </div>
      </div>

      {/* Below mid-point */}
      <div style={card(tokens.colors.red)}>
        <div style={label}>Below mid-point</div>
        <div style={value}>
          {kpis.below}
          <Pct n={kpis.below_pct} />
        </div>
        <div style={sub}>of total hires</div>
      </div>

      {/* Above mid-point */}
      <div style={card(tokens.colors.primary)}>
        <div style={label}>Above mid-point</div>
        <div style={value}>
          {kpis.above}
          <Pct n={kpis.above_pct} />
        </div>
        <div style={sub}>of total hires</div>
      </div>

      {/* At mid + No salary */}
      <div style={card(tokens.colors.yellow)}>
        <div style={label}>At mid-point / no data</div>
        <div style={value}>{kpis.at_mid + kpis.no_salary}</div>
        <div style={split}>
          <span style={splitItem}>
            At mid{" "}
            <strong
              style={{ color: tokens.colors.black, fontFamily: tokens.typography.fontFamily }}
            >
              {kpis.at_mid}
            </strong>
          </span>
          <span style={splitItem}>
            No salary{" "}
            <strong
              style={{ color: tokens.colors.black, fontFamily: tokens.typography.fontFamily }}
            >
              {kpis.no_salary}
            </strong>
          </span>
        </div>
      </div>
    </div>
  );
}
