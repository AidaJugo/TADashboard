import { test, expect } from "@playwright/test";
import path from "path";

test("landing page renders (TC-E-1 smoke)", async ({ browser }) => {
  const ctx = await browser.newContext({
    storageState: path.join(__dirname, "auth", "viewer.json"),
  });
  const page = await ctx.newPage();

  // Provide a minimal report response so the page renders without a backend.
  await page.route("**/api/report**", (route) => {
    route.fulfill({
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
        data: { has_data: false },
      }),
    });
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Talent Acquisition");
  await ctx.close();
});
