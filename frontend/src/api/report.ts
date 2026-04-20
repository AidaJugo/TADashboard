/**
 * API client for GET /api/report.
 *
 * Mirrors the backend ReportResponse Pydantic model exactly.
 * No hardcoded hex values. No CDN references.
 */

// ---------------------------------------------------------------------------
// Types (mirror backend app/report/models.py)
// ---------------------------------------------------------------------------

export interface StatusCounts {
  below: number;
  at_mid: number;
  above: number;
  no_salary: number;
  total: number;
}

export interface TypeSummaryRow {
  hire_type: string; // "WF" | "NonWF" | "Total"
  below: number;
  at_mid: number;
  above: number;
  no_salary: number;
  total: number;
}

export interface HubRow {
  hub: string;
  has_data: boolean;
  total: number;
  rows: TypeSummaryRow[];
  city_note: string;
}

export interface AboveMidpointEntry {
  position: string;
  seniority: string;
  hub: string;
  salary: number | null;
  midpoint: number | null;
  gap_eur: number | null;
  gap_pct: number | null;
  recruiter: string;
  comment: string;
  hire_note: string;
}

export interface KpiBlock {
  total: number;
  wf: number;
  non_wf: number;
  below: number;
  below_pct: number;
  above: number;
  above_pct: number;
  at_mid: number;
  at_mid_pct: number;
  no_salary: number;
  no_salary_pct: number;
}

export interface PeriodData {
  has_data: boolean;
  kpis: KpiBlock | null;
  summary: TypeSummaryRow[];
  hub_rows: HubRow[];
  above_detail: AboveMidpointEntry[];
  hub_totals: Record<string, number>;
  benchmark_note: string;
  unknown_statuses: string[];
  rows_missing_month: number;
}

export interface ReportResponse {
  year: number;
  period: string;
  stale: boolean;
  fetched_at: string;
  data: PeriodData;
  previous_year: number | null;
  previous_year_data: PeriodData | null;
  previous_year_missing: boolean;
}

// ---------------------------------------------------------------------------
// Query params
// ---------------------------------------------------------------------------

export interface ReportParams {
  year: number;
  period: string;
  hub?: string;
  compare_previous?: boolean;
}

// ---------------------------------------------------------------------------
// Fetcher
// ---------------------------------------------------------------------------

export async function fetchReport(params: ReportParams): Promise<ReportResponse> {
  const url = new URL("/api/report", window.location.origin);
  url.searchParams.set("year", String(params.year));
  url.searchParams.set("period", params.period);
  if (params.hub) url.searchParams.set("hub", params.hub);
  if (params.compare_previous) url.searchParams.set("compare_previous", "true");

  const res = await fetch(url.toString(), { credentials: "include" });

  if (res.status === 401) {
    // Session expired — redirect to login.
    window.location.href = "/api/auth/login";
    throw new Error("session_expired");
  }
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API error ${res.status}: ${detail}`);
  }
  return res.json() as Promise<ReportResponse>;
}

export async function postRefresh(): Promise<void> {
  // CSRF double-submit: read token from cookie, send in header.
  const csrfToken = document.cookie
    .split("; ")
    .find((c) => c.startsWith("ta_csrf="))
    ?.split("=")[1];

  const res = await fetch("/api/report/refresh", {
    method: "POST",
    credentials: "include",
    headers: csrfToken ? { "X-CSRF-Token": csrfToken } : {},
  });

  if (!res.ok) {
    throw new Error(`Refresh failed: ${res.status}`);
  }
}
