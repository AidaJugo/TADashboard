/**
 * Component tests for StaleBanner and YoYToggle.
 *
 * TC-E-7 (stale banner renders) and TC-U-REP-12 (previous year missing marker)
 * are covered here at the unit level; E2E tests cover the full flow.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { StaleBanner } from "@/components/StaleBanner";
import { YoYToggle } from "@/components/YoYToggle";

// ---------------------------------------------------------------------------
// StaleBanner (TC-E-7 unit layer)
// ---------------------------------------------------------------------------

describe("StaleBanner", () => {
  it("renders with role=alert and stale message (TC-E-7)", () => {
    render(<StaleBanner fetchedAt="2026-04-17T12:00:00Z" />);
    const banner = screen.getByRole("alert");
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveAttribute("data-testid", "stale-banner");
    expect(banner.textContent).toMatch(/stale/i);
    expect(banner.textContent).toMatch(/Refresh/);
  });
});

// ---------------------------------------------------------------------------
// YoYToggle (TC-U-REP-12 unit layer)
// ---------------------------------------------------------------------------

describe("YoYToggle", () => {
  it("renders unchecked by default", () => {
    render(<YoYToggle enabled={false} previousYearMissing={false} onChange={vi.fn()} />);
    const checkbox = screen.getByRole("checkbox");
    expect(checkbox).not.toBeChecked();
  });

  it("calls onChange when toggled", async () => {
    const onChange = vi.fn();
    render(<YoYToggle enabled={false} previousYearMissing={false} onChange={onChange} />);
    await userEvent.click(screen.getByRole("checkbox"));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("shows previous-year-missing marker when enabled and missing (TC-U-REP-12)", () => {
    render(<YoYToggle enabled={true} previousYearMissing={true} onChange={vi.fn()} />);
    expect(screen.getByTestId("previous-year-missing")).toBeInTheDocument();
  });

  it("hides previous-year-missing marker when not enabled", () => {
    render(<YoYToggle enabled={false} previousYearMissing={true} onChange={vi.fn()} />);
    expect(screen.queryByTestId("previous-year-missing")).not.toBeInTheDocument();
  });

  it("hides previous-year-missing marker when enabled but data is present", () => {
    render(<YoYToggle enabled={true} previousYearMissing={false} onChange={vi.fn()} />);
    expect(screen.queryByTestId("previous-year-missing")).not.toBeInTheDocument();
  });
});
