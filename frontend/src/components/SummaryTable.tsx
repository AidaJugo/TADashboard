/**
 * SummaryTable — WF / NonWF / Total breakdown across all hubs.
 *
 * Mirrors the prototype's .report-tbl layout.
 * Numeric colour coding: column headers and numeric emphasis use black only
 * (FR-BRAND-5).  Status cells use fontWeight for differentiation; borders
 * and backgrounds carry the accent colour so no text uses secondary tokens.
 */

import { tokens } from "@/theme/tokens";
import type { TypeSummaryRow } from "@/api/report";

interface SummaryTableProps {
  summary: TypeSummaryRow[];
  benchmarkNote: string;
}

const tableStyle: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: 13,
  fontFamily: tokens.typography.fontFamily,
};

const th: React.CSSProperties = {
  background: tokens.colors.lightGrey,
  padding: "9px 14px",
  textAlign: "center",
  fontSize: 11,
  fontWeight: 700,
  color: tokens.colors.black,
  textTransform: "uppercase",
  letterSpacing: "0.4px",
  borderBottom: `2px solid ${tokens.colors.lightGrey}`,
};

const thLeft: React.CSSProperties = { ...th, textAlign: "left" };

function tdStyle(isTotal: boolean): React.CSSProperties {
  return {
    padding: "10px 14px",
    textAlign: "center",
    borderBottom: `1px solid ${tokens.colors.lightGrey}`,
    fontWeight: isTotal ? 700 : 400,
    color: tokens.colors.black,
    background: isTotal ? tokens.colors.lightGrey : tokens.colors.white,
  };
}

function tdLeftStyle(isTotal: boolean): React.CSSProperties {
  return { ...tdStyle(isTotal), textAlign: "left", fontWeight: 600 };
}

// Status cells: fontWeight and left-border carry the accent colour so the
// text itself stays black (FR-BRAND-5 + WCAG AA).
const numBelow: React.CSSProperties = {
  color: tokens.colors.black,
  fontWeight: 700,
  borderLeft: `3px solid ${tokens.colors.red}`,
};
const numAbove: React.CSSProperties = {
  color: tokens.colors.black,
  fontWeight: 700,
  borderLeft: `3px solid ${tokens.colors.primary}`,
};
const numAtMid: React.CSSProperties = { color: tokens.colors.black, fontWeight: 700 };
const numNoSal: React.CSSProperties = { color: tokens.colors.black, fontWeight: 600 };

function NumCell({ val, style }: { val: number; style: React.CSSProperties }) {
  return <td style={{ ...tdStyle(false), ...style }}>{val || "—"}</td>;
}

export function SummaryTable({ summary, benchmarkNote }: SummaryTableProps) {
  return (
    <div
      style={{
        background: tokens.colors.white,
        borderRadius: tokens.radius.md,
        border: `1px solid ${tokens.colors.lightGrey}`,
        marginBottom: tokens.spacing.lg,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: `${tokens.spacing.md}px ${tokens.spacing.lg}px`,
          borderBottom: `1px solid ${tokens.colors.lightGrey}`,
        }}
      >
        <span
          style={{
            fontSize: 14,
            fontWeight: 700,
            color: tokens.colors.black,
            fontFamily: tokens.typography.fontFamily,
          }}
        >
          Summary — all contracting hubs
        </span>
      </div>
      <div style={{ padding: tokens.spacing.lg }}>
        <table style={tableStyle}>
          <thead>
            <tr>
              <th style={thLeft}>Segment</th>
              <th style={th}>Below mid-point</th>
              <th style={th}>At mid-point</th>
              <th style={th}>Above mid-point</th>
              <th style={th}>No salary / not benchmarked</th>
              <th style={th}>Total</th>
            </tr>
          </thead>
          <tbody>
            {summary.map((row) => {
              const isTotal = row.hire_type === "Total";
              return (
                <tr key={row.hire_type}>
                  <td style={tdLeftStyle(isTotal)}>{row.hire_type}</td>
                  <NumCell val={row.below} style={isTotal ? {} : numBelow} />
                  <NumCell val={row.at_mid} style={isTotal ? {} : numAtMid} />
                  <NumCell val={row.above} style={isTotal ? {} : numAbove} />
                  <NumCell val={row.no_salary} style={isTotal ? {} : numNoSal} />
                  <td style={tdStyle(isTotal)}>{row.total || "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {benchmarkNote && (
          <div
            style={{
              marginTop: tokens.spacing.md,
              padding: `${tokens.spacing.sm}px 14px`,
              background: tokens.colors.lightGrey,
              borderLeft: `3px solid ${tokens.colors.yellow}`,
              fontSize: 12,
              color: tokens.colors.black,
              fontFamily: tokens.typography.fontFamily,
            }}
          >
            {benchmarkNote}
          </div>
        )}
      </div>
    </div>
  );
}
