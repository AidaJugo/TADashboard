/**
 * ExportPdfButton — triggers GET /api/report/export-pdf with current params.
 *
 * Security: query params are assembled from app state (validated period +
 * integer year), never from user-typed strings.  The server applies hub scope
 * and renders the PDF; no client-supplied hub string is sent.
 */

import type React from "react";
import { tokens } from "@/theme/tokens";

interface ExportPdfButtonProps {
  year: number;
  period: string;
  comparePrevious?: boolean;
  disabled?: boolean;
}

const btnStyle: React.CSSProperties = {
  padding: `6px ${tokens.spacing.md}px`,
  fontSize: 13,
  fontWeight: 600,
  fontFamily: tokens.typography.fontFamily,
  color: tokens.colors.white,
  background: tokens.colors.navy,
  border: "none",
  borderRadius: tokens.radius.sm,
  cursor: "pointer",
  textDecoration: "none",
  display: "inline-block",
  lineHeight: "1.5",
};

const disabledStyle: React.CSSProperties = {
  ...btnStyle,
  opacity: 0.5,
  cursor: "default",
  pointerEvents: "none",
};

export function ExportPdfButton({
  year,
  period,
  comparePrevious = false,
  disabled = false,
}: ExportPdfButtonProps) {
  function buildHref(): string {
    const url = new URL("/api/report/export-pdf", window.location.origin);
    url.searchParams.set("year", String(year));
    url.searchParams.set("period", period);
    if (comparePrevious) url.searchParams.set("compare_previous", "true");
    return url.toString();
  }

  return (
    <a
      href={disabled ? undefined : buildHref()}
      download
      data-testid="export-pdf-link"
      style={disabled ? disabledStyle : btnStyle}
      aria-label={`Export ${period} ${year} report as PDF`}
      aria-disabled={disabled}
    >
      Export PDF
    </a>
  );
}
