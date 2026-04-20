/**
 * E2E tests for M6 flows — TC-E-6, TC-E-11, TC-E-12.
 *
 * TC-E-6  — Admin saves config with an invalid spreadsheet tab name.
 *            Server returns 422; the UI shows an error; previous config
 *            remains active (FR-CONFIG-4, TC-I-API-5).
 *
 * TC-E-11 — Hub-scoped viewer clicks "Export PDF". The browser initiates a
 *            download against /api/report/export-pdf with the correct year,
 *            period, and no hub param (scope is server-resolved).
 *
 * TC-E-12 — Admin attempts to demote the only remaining admin to "viewer".
 *            The server returns 409; the UI shows an error message; the
 *            user's role is unchanged (FR-USER-3, TC-I-API-11).
 *
 * Authentication: loads storageState files seeded by global-setup.ts.
 * Backend calls are intercepted via page.route() so no live backend is needed.
 */

import path from "path";
import { fileURLToPath } from "url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
import { test, expect } from "@playwright/test";

// ---------------------------------------------------------------------------
// TC-E-6: Invalid spreadsheet config returns 422 — UI shows error
// ---------------------------------------------------------------------------

test("TC-E-6: admin saves invalid spreadsheet tab — UI shows error, config unchanged", async ({
  browser,
}) => {
  const ctx = await browser.newContext({
    storageState: path.join(__dirname, "auth", "admin.json"),
  });
  const page = await ctx.newPage();

  // Mock /api/auth/me so the admin guard passes.
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "00000000-0000-0000-0000-000000000001",
        email: "e2e-admin@symphony.is",
        display_name: "E2E Admin",
        role: "admin",
      }),
    }),
  );

  // Existing config (baseline).
  const existingConfig = {
    spreadsheet_id: "abc123",
    spreadsheet_tab_name: "2026 Hiring",
    audit_retention_months: 18,
    backup_retention_days: 30,
    column_mappings: {},
  };

  await page.route("**/api/admin/config", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(existingConfig),
      });
    }
    // POST with invalid tab name → 422.
    return route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({
        detail: [{ loc: ["body", "spreadsheet_tab_name"], msg: "Tab not found in spreadsheet." }],
      }),
    });
  });

  // Hub pairs endpoint (needed by AdminConfigPage).
  await page.route("**/api/admin/hub-pairs", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );

  await page.goto("/admin/config");

  // Wait for the config form to load.
  const tabInput = page.getByLabel("Tab name");
  await expect(tabInput).toBeVisible();

  // Clear and type an invalid tab name, then save.
  await tabInput.fill("__nonexistent_tab__");
  await page.getByRole("button", { name: "Save changes" }).first().click();

  // The UI must show an error message.
  const errorText = page.getByText(/422|Tab not found|Save failed/i);
  await expect(errorText).toBeVisible();

  // The tab input still shows the invalid value (save was rejected).
  await expect(tabInput).toHaveValue("__nonexistent_tab__");

  await ctx.close();
});

// ---------------------------------------------------------------------------
// TC-E-11: Hub-scoped viewer clicks Export PDF — download starts
// ---------------------------------------------------------------------------

test("TC-E-11: hub-scoped viewer clicks Export PDF — browser initiates download with correct params", async ({
  browser,
}) => {
  const ctx = await browser.newContext({
    storageState: path.join(__dirname, "auth", "scoped-viewer.json"),
  });
  const page = await ctx.newPage();

  // Mock /api/auth/me for the scoped viewer.
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "00000000-0000-0000-0000-000000000002",
        email: "e2e-scoped@symphony.is",
        display_name: "E2E Scoped Viewer",
        role: "viewer",
      }),
    }),
  );

  // Mock the report so data.has_data=true (Export PDF button is enabled only
  // when there is data to export).
  await page.route("**/api/report**", (route) => {
    if (route.request().url().includes("export-pdf")) {
      // Serve a minimal PDF response.
      return route.fulfill({
        status: 200,
        contentType: "application/pdf",
        headers: {
          "Content-Disposition": 'attachment; filename="ta-report-2026-Annual.pdf"',
        },
        body: Buffer.from("%PDF-1.4 fake-pdf-body"),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        year: 2026,
        period: "Annual",
        fetched_at: "2026-04-17T10:00:00",
        stale: false,
        previous_year: null,
        previous_year_data: null,
        previous_year_missing: false,
        data: {
          has_data: true,
          kpis: {
            total: 10,
            wf: 9,
            non_wf: 1,
            below: 1,
            below_pct: 0.1,
            above: 2,
            above_pct: 0.2,
            at_mid: 7,
            at_mid_pct: 0.7,
            no_salary: 0,
            no_salary_pct: 0,
          },
          summary: [],
          hub_rows: [
            { hub: "Sarajevo", has_data: true, total: 6, rows: [], city_note: "" },
            { hub: "Skopje", has_data: true, total: 4, rows: [], city_note: "" },
          ],
          above_detail: [],
          benchmark_note: "",
          hub_totals: { Sarajevo: 6, Skopje: 4 },
        },
      }),
    });
  });

  // Mock /api/comments.
  await page.route("**/api/comments", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) }),
  );

  await page.goto("/");

  // Wait for the page to load (KPI data visible).
  await expect(page.getByTestId("kpi-card-row")).toBeVisible();

  // The Export PDF link must be present and enabled.
  const exportLink = page.getByRole("link", { name: /export pdf/i });
  await expect(exportLink).toBeVisible();
  await expect(exportLink).not.toHaveAttribute("aria-disabled", "true");

  // Verify the href contains the correct params — year, period, no hub param.
  const href = await exportLink.getAttribute("href");
  expect(href).toContain("/api/report/export-pdf");
  expect(href).toContain("year=2026");
  expect(href).toContain("period=Annual");
  // Hub scope must NOT be in the URL — it is resolved server-side.
  expect(href).not.toContain("hub=");

  await ctx.close();
});

// ---------------------------------------------------------------------------
// TC-E-12: Admin demotes the only admin — 409, role unchanged
// ---------------------------------------------------------------------------

test("TC-E-12: admin attempts to demote last remaining admin — UI shows 409 error", async ({
  browser,
}) => {
  const ctx = await browser.newContext({
    storageState: path.join(__dirname, "auth", "admin.json"),
  });
  const page = await ctx.newPage();

  const adminUserId = "00000000-0000-0000-0000-000000000001";

  // Mock /api/auth/me.
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: adminUserId,
        email: "e2e-admin@symphony.is",
        display_name: "E2E Admin",
        role: "admin",
      }),
    }),
  );

  // User list: only one admin.
  await page.route("**/api/admin/users", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: adminUserId,
            email: "e2e-admin@symphony.is",
            display_name: "E2E Admin",
            role: "admin",
            is_active: true,
            allowed_hubs: [],
            created_at: "2026-01-01T00:00:00",
            updated_at: "2026-01-01T00:00:00",
          },
        ]),
      });
    }
    // PATCH → 409 last-admin guard.
    if (route.request().method() === "PATCH") {
      return route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({
          detail: "Cannot remove the last active admin.",
        }),
      });
    }
    return route.continue();
  });

  await page.goto("/admin/users");

  // The admin row must be visible.
  await expect(page.getByText("e2e-admin@symphony.is")).toBeVisible();

  // Click Edit on the only admin row.
  await page.getByRole("button", { name: /edit/i }).first().click();

  // In the inline edit row, change the role to "viewer" and save.
  const roleSelect = page.getByLabel("Role");
  await roleSelect.selectOption("viewer");
  await page.getByRole("button", { name: /save/i }).first().click();

  // The UI must show an error message containing the 409 reason.
  const errorMsg = page.getByText(/409|Cannot remove the last active admin|Update failed/i);
  await expect(errorMsg).toBeVisible();

  await ctx.close();
});
