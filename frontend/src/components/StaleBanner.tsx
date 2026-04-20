/**
 * StaleBanner — shown when the Sheet data is stale (TC-E-7, FR-REPORT-2).
 *
 * Uses tokens.colors.yellow background with tokens.colors.black text.
 * Never uses secondary colours as surface text.
 */

import { tokens } from "@/theme/tokens";

interface StaleBannerProps {
  fetchedAt: string;
}

export function StaleBanner({ fetchedAt }: StaleBannerProps) {
  const formatted = new Date(fetchedAt).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div
      role="alert"
      data-testid="stale-banner"
      style={{
        background: tokens.colors.yellow,
        color: tokens.colors.black,
        padding: `${tokens.spacing.sm}px ${tokens.spacing.xl}px`,
        fontSize: 13,
        fontFamily: tokens.typography.fontFamily,
        fontWeight: 500,
        display: "flex",
        alignItems: "center",
        gap: tokens.spacing.sm,
      }}
    >
      Data may be stale. Last successful fetch: {formatted}. Use Refresh to update.
    </div>
  );
}
