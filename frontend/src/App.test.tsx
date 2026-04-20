/**
 * App smoke test — verifies the report page renders without crashing.
 *
 * Full component tests live in src/test/*.test.tsx.
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { App } from "@/App";

// Mock fetch so the useReport hook doesn't make a real network call.
const mockFetch = vi.fn().mockResolvedValue({
  ok: true,
  status: 200,
  json: async () => ({
    year: 2026,
    period: "Annual",
    stale: false,
    fetched_at: "2026-04-17T12:00:00Z",
    data: {
      has_data: false,
      kpis: null,
      summary: [],
      hub_rows: [],
      above_detail: [],
      hub_totals: {},
      benchmark_note: "",
      unknown_statuses: [],
      rows_missing_month: 0,
    },
    previous_year: null,
    previous_year_data: null,
    previous_year_missing: false,
  }),
});

vi.stubGlobal("fetch", mockFetch);

describe("App", () => {
  it("renders the Talent Acquisition heading", () => {
    render(<App />);
    expect(screen.getByText("Talent Acquisition")).toBeInTheDocument();
  });
});
