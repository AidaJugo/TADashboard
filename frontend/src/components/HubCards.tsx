/**
 * HubCards — per-hub breakdown grid.
 *
 * Each hub pair renders as a card with WF / NonWF / Total rows.
 * Empty hubs show a "No hires this period" message.
 * City note (if present) is shown below the table.
 */

import { tokens } from "@/theme/tokens";
import type { HubRow } from "@/api/report";

interface HubCardsProps {
  hubRows: HubRow[];
}

const grid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  gap: tokens.spacing.md,
  marginBottom: tokens.spacing.lg,
};

function HubCard({ hub }: { hub: HubRow }) {
  return (
    <div
      style={{
        background: tokens.colors.white,
        borderRadius: tokens.radius.md,
        border: `1px solid ${tokens.colors.lightGrey}`,
        overflow: "hidden",
      }}
      data-testid={`hub-card-${hub.hub}`}
    >
      <div
        style={{
          background: tokens.colors.lightGrey,
          padding: `${tokens.spacing.sm}px 14px`,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: `1px solid ${tokens.colors.lightGrey}`,
        }}
      >
        <span
          style={{
            fontSize: 13,
            fontWeight: 700,
            color: tokens.colors.black,
            fontFamily: tokens.typography.fontFamily,
          }}
        >
          {hub.hub}
        </span>
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            background: hub.has_data ? tokens.colors.navy : tokens.colors.lightGrey,
            color: hub.has_data ? tokens.colors.white : tokens.colors.black,
            padding: `2px ${tokens.spacing.sm}px`,
            borderRadius: tokens.radius.md,
            fontFamily: tokens.typography.fontFamily,
          }}
        >
          {hub.total}
        </span>
      </div>

      {!hub.has_data ? (
        <div
          style={{
            padding: tokens.spacing.lg,
            textAlign: "center",
            fontSize: 12,
            color: tokens.colors.black,
            fontStyle: "italic",
            fontFamily: tokens.typography.fontFamily,
          }}
        >
          No hires this period
        </div>
      ) : (
        <>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: 11.5,
              fontFamily: tokens.typography.fontFamily,
            }}
          >
            <thead>
              <tr>
                <th
                  style={{
                    background: tokens.colors.lightGrey,
                    padding: "6px 10px",
                    textAlign: "left",
                    fontSize: 10,
                    fontWeight: 700,
                    color: tokens.colors.black,
                    textTransform: "uppercase",
                  }}
                />
                {["Below", "At mid", "Above", "No sal.", "Total"].map((h) => (
                  <th
                    key={h}
                    style={{
                      background: tokens.colors.lightGrey,
                      padding: "6px 10px",
                      textAlign: "center",
                      fontSize: 10,
                      fontWeight: 700,
                      color: tokens.colors.black,
                      textTransform: "uppercase",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {hub.rows.map((row) => {
                const isTotal = row.hire_type === "Total";
                return (
                  <tr key={row.hire_type}>
                    <td
                      style={{
                        padding: "6px 10px",
                        fontWeight: 600,
                        fontSize: 11,
                        color: tokens.colors.black,
                        background: isTotal ? tokens.colors.lightGrey : tokens.colors.white,
                        borderTop: `1px solid ${tokens.colors.lightGrey}`,
                      }}
                    >
                      {row.hire_type}
                    </td>
                    {[row.below, row.at_mid, row.above, row.no_salary, row.total].map((v, i) => (
                      <td
                        key={i}
                        style={{
                          padding: "6px 10px",
                          textAlign: "center",
                          color: tokens.colors.black,
                          background: isTotal ? tokens.colors.lightGrey : tokens.colors.white,
                          borderTop: `1px solid ${tokens.colors.lightGrey}`,
                          fontWeight: isTotal ? 700 : 400,
                        }}
                      >
                        {v || "—"}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
          {hub.city_note && (
            <div
              style={{
                padding: `6px 12px`,
                fontSize: 11,
                color: tokens.colors.black,
                background: tokens.colors.lightGrey,
                borderTop: `1px solid ${tokens.colors.peach}`,
                fontFamily: tokens.typography.fontFamily,
              }}
            >
              ⓘ {hub.city_note}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function HubCards({ hubRows }: HubCardsProps) {
  if (hubRows.length === 0) return null;

  return (
    <>
      <div
        style={{
          fontSize: 15,
          fontWeight: 700,
          color: tokens.colors.black,
          marginBottom: tokens.spacing.md,
          fontFamily: tokens.typography.fontFamily,
        }}
      >
        Breakdown by contracting hub
      </div>
      <div style={grid} data-testid="hub-cards">
        {hubRows.map((h) => (
          <HubCard key={h.hub} hub={h} />
        ))}
      </div>
    </>
  );
}
