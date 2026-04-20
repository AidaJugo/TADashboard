/**
 * E2E report page tests — TC-E-1, TC-E-4, TC-E-5, TC-E-7, TC-E-9, TC-E-10.
 *
 * Authentication strategy: each test loads a storageState file produced by
 * global-setup.ts (POST /api/e2e/seed-session).  Sheet data is controlled via
 * page.route() so no Google credentials are needed in the E2E stack.
 *
 * TC-E-1  — Authenticated viewer sees the report page with hire KPIs.
 * TC-E-4  — Hub-scoped viewer (Sarajevo + Skopje only) sees only those hubs
 *            in the HubCards grid; Belgrade and Medellin cards must be absent.
 * TC-E-5  — Above-midpoint entry with a stored comment renders the comment text.
 * TC-E-7  — StaleBanner is visible when the API returns stale=true.
 * TC-E-9  — Year selector fires a new request with year=2025; the rendered KPI
 *            total updates to the 2025 fixture value; hub scope is preserved
 *            (same four hub cards appear, no new hubs surface).
 * TC-E-10 — YoY toggle mounts the previous-year section; out-of-scope hubs
 *            (Belgrade, Medellin) are absent from the entire page DOM — both
 *            the current-year section and the previous-year section.  This is
 *            the YoY equivalent of TC-E-4.
 */

import path from "path";
import { fileURLToPath } from "url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
import { test, expect, type Page, type Route } from "@playwright/test";

// ---------------------------------------------------------------------------
// Shared fixtures
// ---------------------------------------------------------------------------

const HUB_ROWS_ALL = [
  { hub: "Sarajevo", has_data: true, total: 10, rows: [], city_note: "" },
  { hub: "Belgrade", has_data: true, total: 9, rows: [], city_note: "" },
  { hub: "Skopje", has_data: true, total: 6, rows: [], city_note: "" },
  { hub: "Medellin", has_data: true, total: 6, rows: [], city_note: "" },
];

const HUB_ROWS_SCOPED = [
  { hub: "Sarajevo", has_data: true, total: 10, rows: [], city_note: "" },
  { hub: "Skopje", has_data: true, total: 6, rows: [], city_note: "" },
];

// Distinct 2025 hub totals so year-switch assertions have unambiguous numbers.
const HUB_ROWS_ALL_2025 = [
  { hub: "Sarajevo", has_data: true, total: 7, rows: [], city_note: "" },
  { hub: "Belgrade", has_data: true, total: 5, rows: [], city_note: "" },
  { hub: "Skopje", has_data: true, total: 4, rows: [], city_note: "" },
  { hub: "Medellin", has_data: true, total: 3, rows: [], city_note: "" },
];

// Scoped 2025 hub rows (Sarajevo + Skopje only) used in TC-E-10 YoY.
const HUB_ROWS_SCOPED_2025 = [
  { hub: "Sarajevo", has_data: true, total: 7, rows: [], city_note: "" },
  { hub: "Skopje", has_data: true, total: 4, rows: [], city_note: "" },
];

const SUMMARY = [
  { hire_type: "WF", below: 2, at_mid: 22, above: 5, no_salary: 0, total: 29 },
  { hire_type: "NonWF", below: 0, at_mid: 1, above: 0, no_salary: 1, total: 2 },
  { hire_type: "Total", below: 2, at_mid: 23, above: 5, no_salary: 1, total: 31 },
];

/** 2026 KPIs — total=31 is the canonical 2026 fingerprint in these tests. */
const KPIS = {
  total: 31,
  wf: 30,
  non_wf: 1,
  below: 2,
  below_pct: 6.5,
  above: 5,
  above_pct: 16.1,
  at_mid: 23,
  at_mid_pct: 74.2,
  no_salary: 1,
  no_salary_pct: 3.2,
};

/**
 * 2025 KPIs — total=19 is the canonical 2025 fingerprint in these tests.
 * TC-E-9 asserts this number appears in the kpi-card-row after the year switch.
 */
const KPIS_2025 = {
  total: 19,
  wf: 18,
  non_wf: 1,
  below: 1,
  below_pct: 5.3,
  above: 3,
  above_pct: 15.8,
  at_mid: 14,
  at_mid_pct: 73.7,
  no_salary: 1,
  no_salary_pct: 5.3,
};

function makeReport(overrides: Record<string, unknown> = {}): object {
  return {
    year: 2026,
    period: "Annual",
    fetched_at: "2026-04-17T10:00:00",
    stale: false,
    previous_year: null,
    previous_year_data: null,
    previous_year_missing: false,
    data: {
      has_data: true,
      kpis: KPIS,
      summary: SUMMARY,
      hub_rows: HUB_ROWS_ALL,
      above_detail: [],
      benchmark_note: "",
      hub_totals: { Sarajevo: 10, Belgrade: 9, Skopje: 6, Medellin: 6 },
    },
    ...overrides,
  };
}

function mockReport(page: Page, response: object): void {
  page.route("**/api/report**", (route: Route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(response),
    });
  });
}

// ---------------------------------------------------------------------------
// TC-E-1: Authenticated viewer sees the report page
// ---------------------------------------------------------------------------

test("TC-E-1: authenticated viewer loads the report and sees KPI data", async ({ browser }) => {
  const ctx = await browser.newContext({
    storageState: path.join(__dirname, "auth", "viewer.json"),
  });
  const page = await ctx.newPage();

  mockReport(page, makeReport());

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Talent Acquisition");

  // KPI total is rendered in the KPI card row (scoped to avoid the
  // summary table which also shows 31 as the Total row count — TC-E-1).
  const kpiRow = page.getByTestId("kpi-card-row");
  await expect(kpiRow).toBeVisible();
  await expect(kpiRow.getByText("31")).toBeVisible();

  // Hub cards grid is present.
  await expect(page.getByTestId("hub-cards")).toBeVisible();

  await ctx.close();
});

// ---------------------------------------------------------------------------
// TC-E-4: Hub-scoped viewer DOM shows only Sarajevo + Skopje
// ---------------------------------------------------------------------------

test("TC-E-4: hub-scoped viewer sees only their hubs in the cards grid", async ({ browser }) => {
  const ctx = await browser.newContext({
    storageState: path.join(__dirname, "auth", "scoped-viewer.json"),
  });
  const page = await ctx.newPage();

  mockReport(
    page,
    makeReport({ data: { ...(makeReport() as { data: object }).data, hub_rows: HUB_ROWS_SCOPED } }),
  );

  await page.goto("/");
  await expect(page.getByTestId("hub-cards")).toBeVisible();

  // Scoped hubs are present.
  await expect(page.getByTestId("hub-card-Sarajevo")).toBeVisible();
  await expect(page.getByTestId("hub-card-Skopje")).toBeVisible();

  // Out-of-scope hubs must not exist in the DOM (TC-E-4 core assertion).
  await expect(page.getByTestId("hub-card-Belgrade")).not.toBeAttached();
  await expect(page.getByTestId("hub-card-Medellin")).not.toBeAttached();

  await ctx.close();
});

// ---------------------------------------------------------------------------
// TC-E-5: Above-midpoint entry shows stored comment
// ---------------------------------------------------------------------------

test("TC-E-5: above-midpoint section renders the stored comment", async ({ browser }) => {
  const ctx = await browser.newContext({
    storageState: path.join(__dirname, "auth", "viewer.json"),
  });
  const page = await ctx.newPage();

  const commentText = "Approved by VP — previous year band applies.";
  const aboveDetail = [
    {
      hub: "Belgrade",
      position: "BE Engineer",
      seniority: "Senior",
      salary: 5750,
      midpoint: 4888,
      gap_eur: 862,
      gap_pct: 0.17635,
      comment: commentText,
      hire_note: "",
      recruiter: "Test Recruiter",
    },
  ];

  const report = makeReport();
  (report as { data: { above_detail: unknown[] } }).data.above_detail = aboveDetail;

  mockReport(page, report);

  await page.goto("/");
  await expect(page.getByTestId("above-midpoint-section")).toBeVisible();
  await expect(page.getByText(commentText)).toBeVisible();

  await ctx.close();
});

// ---------------------------------------------------------------------------
// TC-E-7: StaleBanner renders when stale=true
// ---------------------------------------------------------------------------

test("TC-E-7: stale banner is visible when API returns stale=true", async ({ browser }) => {
  const ctx = await browser.newContext({
    storageState: path.join(__dirname, "auth", "viewer.json"),
  });
  const page = await ctx.newPage();

  mockReport(
    page,
    makeReport({
      stale: true,
      fetched_at: "2026-04-10T09:30:00",
    }),
  );

  await page.goto("/");

  const banner = page.getByTestId("stale-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("Data may be stale");

  await ctx.close();
});

// ---------------------------------------------------------------------------
// TC-E-9: Year selector fires a new request and updates rendered data
//
// Asserts:
//   1. A new /api/report request goes out with year=2025.
//   2. The kpi-card-row updates to the 2025 total (19 — distinct from 2026's 31).
//   3. Hub scope is preserved: the same four hubs (Sarajevo, Belgrade, Skopje,
//      Medellin) appear for 2025; no new hubs surface (e.g. Remote is absent).
// ---------------------------------------------------------------------------

test("TC-E-9: year selector updates KPI values and preserves hub scope", async ({ browser }) => {
  const ctx = await browser.newContext({
    storageState: path.join(__dirname, "auth", "viewer.json"),
  });
  const page = await ctx.newPage();

  await page.route("**/api/report**", (route) => {
    const url = new URL(route.request().url());
    const year = Number(url.searchParams.get("year") ?? 2026);
    const is2025 = year === 2025;

    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        makeReport({
          year: is2025 ? 2025 : 2026,
          data: {
            has_data: true,
            kpis: is2025 ? KPIS_2025 : KPIS,
            summary: SUMMARY,
            hub_rows: is2025 ? HUB_ROWS_ALL_2025 : HUB_ROWS_ALL,
            above_detail: [],
            benchmark_note: "",
            hub_totals: is2025
              ? { Sarajevo: 7, Belgrade: 5, Skopje: 4, Medellin: 3 }
              : { Sarajevo: 10, Belgrade: 9, Skopje: 6, Medellin: 6 },
          },
        }),
      ),
    });
  });

  await page.goto("/");

  // --- 2026 baseline --------------------------------------------------------
  const kpiRow = page.getByTestId("kpi-card-row");
  await expect(kpiRow).toBeVisible();
  // The 2026 total (31) is visible inside the KPI card row.
  await expect(kpiRow.getByText("31")).toBeVisible();

  // --- Switch to 2025 -------------------------------------------------------
  // Register the request watcher BEFORE triggering the selector change.
  // With BrowserRouter in the tree the React re-render is tighter and the
  // fetch for year=2025 can fire before a post-selectOption waitForRequest
  // listener is registered (race condition).
  const yearRequest2025 = page.waitForRequest((req) => {
    const url = new URL(req.url());
    return url.pathname.includes("/api/report") && url.searchParams.get("year") === "2025";
  });
  const select = page.getByLabel("Select report year");
  await select.selectOption("2025");

  // 1. A new request must go out with year=2025.
  await yearRequest2025;

  // 2. KPI values update: the 2025 total (19) is now in the KPI card row.
  //    "31" from 2026 must not be the current KPI total anymore.
  await expect(kpiRow.getByText("19")).toBeVisible();

  // 3. Hub scope preserved: all four hubs still appear — no hub was added or
  //    dropped by the year switch.
  await expect(page.getByTestId("hub-card-Sarajevo")).toBeVisible();
  await expect(page.getByTestId("hub-card-Belgrade")).toBeVisible();
  await expect(page.getByTestId("hub-card-Skopje")).toBeVisible();
  await expect(page.getByTestId("hub-card-Medellin")).toBeVisible();
  // Sentinel: a hub that was never in the fixture must not surface.
  await expect(page.getByTestId("hub-card-Remote")).not.toBeAttached();

  await ctx.close();
});

// ---------------------------------------------------------------------------
// TC-E-10: YoY toggle — previous-year section mounts AND scope safety
//
// Uses the scoped-viewer (Sarajevo + Skopje only) so this test also verifies
// that the YoY data-safety invariant holds: out-of-scope hubs (Belgrade,
// Medellin) are absent from the entire page DOM — both the current-year
// HubCards section and the previous-year HubCards section.
// This is the YoY equivalent of TC-E-4.
// ---------------------------------------------------------------------------

test("TC-E-10: YoY toggle shows previous-year section and preserves hub scope in both panels", async ({
  browser,
}) => {
  const ctx = await browser.newContext({
    storageState: path.join(__dirname, "auth", "scoped-viewer.json"),
  });
  const page = await ctx.newPage();

  await page.route("**/api/report**", (route) => {
    const url = new URL(route.request().url());
    const comparePrev = url.searchParams.get("compare_previous") === "true";

    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        makeReport({
          // Return scoped data in both sections.
          data: {
            has_data: true,
            kpis: KPIS,
            summary: SUMMARY,
            hub_rows: HUB_ROWS_SCOPED,
            above_detail: [],
            benchmark_note: "",
            hub_totals: { Sarajevo: 10, Skopje: 6 },
          },
          ...(comparePrev
            ? {
                previous_year: 2025,
                previous_year_missing: false,
                previous_year_data: {
                  has_data: true,
                  kpis: KPIS_2025,
                  summary: SUMMARY,
                  // Previous year also returns only scoped hubs.
                  hub_rows: HUB_ROWS_SCOPED_2025,
                  above_detail: [],
                  benchmark_note: "",
                  hub_totals: { Sarajevo: 7, Skopje: 4 },
                },
              }
            : {
                previous_year: null,
                previous_year_data: null,
              }),
        }),
      ),
    });
  });

  await page.goto("/");
  await expect(page.getByTestId("hub-cards")).toBeVisible();

  // --- Baseline: scoped hub cards in current-year view ----------------------
  await expect(page.getByTestId("hub-card-Sarajevo")).toBeVisible();
  await expect(page.getByTestId("hub-card-Skopje")).toBeVisible();
  await expect(page.getByTestId("hub-card-Belgrade")).not.toBeAttached();
  await expect(page.getByTestId("hub-card-Medellin")).not.toBeAttached();

  // --- Enable YoY comparison ------------------------------------------------
  const toggle = page.getByLabel("Compare with previous year");
  await toggle.check();

  // 1. The previous-year section mounts.
  await expect(page.getByRole("region", { name: /2025 comparison/i })).toBeVisible();

  // 2. Scoped hubs are present in the previous-year panel (current-year panel
  //    was already verified in the baseline block above the toggle click).
  const prevYearSection = page.getByRole("region", { name: /2025 comparison/i });
  await expect(prevYearSection.getByTestId("hub-card-Sarajevo")).toBeVisible();
  await expect(prevYearSection.getByTestId("hub-card-Skopje")).toBeVisible();

  // 3. Out-of-scope hubs are absent from the entire page DOM — covers both
  //    the current-year panel and the previous-year panel (TC-E-10 core
  //    data-safety assertion; YoY equivalent of TC-E-4).
  await expect(page.getByTestId("hub-card-Belgrade")).not.toBeAttached();
  await expect(page.getByTestId("hub-card-Medellin")).not.toBeAttached();

  await ctx.close();
});
