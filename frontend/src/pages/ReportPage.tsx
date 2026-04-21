/**
 * ReportPage — the root report view.
 *
 * Layout:
 *   Header (title, year selector, yoy toggle, refresh button)
 *   StaleBanner (conditional)
 *   PeriodNav
 *   Content area (KpiCardRow, SummaryTable, HubCards, AboveMidpointTable)
 *
 * State:
 *   year        — selected calendar year (default: current)
 *   period      — selected period code (default: "Annual")
 *   group       — active tab group (monthly | quarterly | halfyear | annual)
 *   comparePrev — YoY toggle
 *
 * The report data is loaded via useReport, which uses @tanstack/react-query.
 * Hub scope is enforced server-side; the UI never supplies a hub param
 * directly — it always lets the session determine scope.
 */

import { useState } from "react";
import type React from "react";

import { tokens } from "@/theme/tokens";
import { useReport, useRefresh } from "@/hooks/useReport";
import { useCurrentUser } from "@/hooks/useAuth";
import { PeriodNav, PERIOD_GROUPS } from "@/components/PeriodNav";
import { YearSelector } from "@/components/YearSelector";
import { YoYToggle } from "@/components/YoYToggle";
import { StaleBanner } from "@/components/StaleBanner";
import { KpiCardRow } from "@/components/KpiCardRow";
import { SummaryTable } from "@/components/SummaryTable";
import { HubCards } from "@/components/HubCards";
import { AboveMidpointTable } from "@/components/AboveMidpointTable";
import { ExportPdfButton } from "@/components/ExportPdfButton";
import type { PeriodGroup } from "@/components/PeriodNav";

// ---------------------------------------------------------------------------
// Available years. FR-REPORT-8 / PRD §5: "more years added as data lands".
// Range is 2024 (earliest synthetic dataset) through the current calendar year.
// A new year becomes selectable automatically on 1 Jan without a code change.
// Selecting a year with no Sheet rows shows the FR-REPORT-6 empty state.
// ---------------------------------------------------------------------------

const CURRENT_YEAR = new Date().getFullYear();
const FIRST_DATA_YEAR = 2024;
const AVAILABLE_YEARS = Array.from(
  { length: CURRENT_YEAR - FIRST_DATA_YEAR + 1 },
  (_, i) => FIRST_DATA_YEAR + i,
);

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const headerStyle: React.CSSProperties = {
  background: tokens.colors.navy,
  padding: `0 ${tokens.spacing.xl}px`,
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  height: 68,
};

const titleStyle: React.CSSProperties = {
  color: tokens.colors.white,
  fontSize: tokens.typography.heading.h4.size,
  fontWeight: tokens.typography.heading.h4.weight,
  fontFamily: tokens.typography.fontFamily,
  margin: 0,
};

const subtitleStyle: React.CSSProperties = {
  color: tokens.colors.white,
  fontSize: 12,
  fontFamily: tokens.typography.fontFamily,
  marginTop: 2,
};

const controlsStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: tokens.spacing.lg,
};

const refreshBtnStyle: React.CSSProperties = {
  padding: `6px ${tokens.spacing.md}px`,
  fontSize: 13,
  fontWeight: 600,
  fontFamily: tokens.typography.fontFamily,
  color: tokens.colors.white,
  background: tokens.colors.primary,
  border: "none",
  borderRadius: tokens.radius.sm,
  cursor: "pointer",
};

const mainStyle: React.CSSProperties = {
  maxWidth: 1320,
  margin: "0 auto",
  padding: `${tokens.spacing.lg}px ${tokens.spacing.lg}px`,
};

const emptyStyle: React.CSSProperties = {
  textAlign: "center",
  padding: `80px ${tokens.spacing.xxl}px`,
  background: tokens.colors.white,
  borderRadius: tokens.radius.lg,
  border: `1px solid ${tokens.colors.lightGrey}`,
};

// ---------------------------------------------------------------------------
// Inner page (needs QueryClient to be in scope)
// ---------------------------------------------------------------------------

function ReportPageInner() {
  const [year, setYear] = useState(CURRENT_YEAR);
  const [period, setPeriod] = useState("Annual");
  const [group, setGroup] = useState<PeriodGroup>("annual");
  const [comparePrev, setComparePrev] = useState(false);

  const { data, isLoading, isError, error } = useReport({
    year,
    period,
    compare_previous: comparePrev,
  });

  const refresh = useRefresh();
  const { data: me } = useCurrentUser();

  const canEdit = me?.role === "admin" || me?.role === "editor";
  const isAdmin = me?.role === "admin";

  // When the user switches group, default to the first key in that group.
  function handleGroupChange(g: PeriodGroup) {
    setGroup(g);
    setPeriod(PERIOD_GROUPS[g].keys[0]);
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        background: tokens.colors.lightGrey,
        fontFamily: tokens.typography.fontFamily,
        color: tokens.colors.black,
      }}
    >
      {/* Header */}
      <header style={headerStyle}>
        <div>
          <h1 style={titleStyle}>Talent Acquisition</h1>
          <p style={subtitleStyle}>Hiring Performance Report</p>
        </div>
        <div style={controlsStyle}>
          <YearSelector years={AVAILABLE_YEARS} selected={year} onChange={(y) => setYear(y)} />
          <YoYToggle
            enabled={comparePrev}
            previousYearMissing={data?.previous_year_missing ?? false}
            onChange={setComparePrev}
          />
          <ExportPdfButton
            year={year}
            period={period}
            comparePrevious={comparePrev}
            disabled={!data?.data.has_data}
          />
          <button
            style={refreshBtnStyle}
            disabled={refresh.isPending}
            onClick={() => refresh.mutate()}
            aria-label="Refresh data from Google Sheets"
          >
            {refresh.isPending ? "Refreshing…" : "Refresh"}
          </button>
          {isAdmin && (
            <a
              href="/admin/users"
              style={{
                ...refreshBtnStyle,
                background: "transparent",
                border: `1px solid ${tokens.colors.white}`,
                textDecoration: "none",
                display: "inline-block",
                lineHeight: "1.5",
              }}
              aria-label="Admin panel"
            >
              Admin
            </a>
          )}
        </div>
      </header>

      {/* Stale banner (TC-E-7) */}
      {data?.stale && <StaleBanner fetchedAt={data.fetched_at} />}

      {/* Period navigation */}
      <PeriodNav
        group={group}
        period={period}
        onGroupChange={handleGroupChange}
        onPeriodChange={setPeriod}
      />

      {/* Main content */}
      <main style={mainStyle}>
        {isLoading && <p style={{ color: tokens.colors.black }}>Loading report…</p>}

        {isError && (
          <p style={{ color: tokens.colors.black }}>
            We could not load the report. {error?.message ?? "Please try again."}
          </p>
        )}

        {data && !data.data.has_data && (
          <div style={emptyStyle}>
            <p
              style={{
                fontSize: 18,
                fontWeight: 700,
                color: tokens.colors.black,
                marginBottom: tokens.spacing.sm,
              }}
            >
              No hires yet for this period.
            </p>
            <p style={{ fontSize: 13, color: tokens.colors.black }}>
              Add hires to the Google Sheet to populate this period.
            </p>
          </div>
        )}

        {data?.data.has_data && (
          <>
            {data.data.kpis && <KpiCardRow kpis={data.data.kpis} year={year} period={period} />}
            <SummaryTable summary={data.data.summary} benchmarkNote={data.data.benchmark_note} />
            <HubCards hubRows={data.data.hub_rows} />
            {data.data.above_detail.length > 0 && (
              <AboveMidpointTable entries={data.data.above_detail} canEdit={canEdit} />
            )}

            {/* Year-over-year panel (FR-REPORT-9) */}
            {comparePrev && data.previous_year_data && (
              <section aria-label={`${data.previous_year ?? "Previous year"} comparison`}>
                <h2
                  style={{
                    fontSize: 15,
                    fontWeight: 700,
                    color: tokens.colors.black,
                    margin: `${tokens.spacing.xl}px 0 ${tokens.spacing.md}px`,
                    display: "flex",
                    alignItems: "center",
                    gap: tokens.spacing.sm,
                  }}
                >
                  {data.previous_year} — same period
                </h2>
                {data.previous_year_data.has_data ? (
                  <>
                    {data.previous_year_data.kpis && (
                      <KpiCardRow
                        kpis={data.previous_year_data.kpis}
                        year={data.previous_year ?? year - 1}
                        period={period}
                      />
                    )}
                    <HubCards hubRows={data.previous_year_data.hub_rows} />
                  </>
                ) : (
                  <div style={emptyStyle}>
                    <p
                      style={{
                        fontSize: 16,
                        fontWeight: 700,
                        color: tokens.colors.black,
                      }}
                    >
                      No data for {data.previous_year} {period}.
                    </p>
                  </div>
                )}
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Exported component
// ---------------------------------------------------------------------------

export function ReportPage() {
  return <ReportPageInner />;
}
