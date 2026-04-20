"""PDF rendering for the TA Hiring Report (FR-REPORT-10, ADR 0009).

WeasyPrint is chosen for its Python-native HTML-to-PDF conversion:
- No external browser process required (unlike Playwright headless).
- Structured data renders cleanly with CSS-based print layout.
- Smaller dependency surface vs. ReportLab for structured HTML output.

System dependencies needed in the Dockerfile:
  libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf-2.0-0 libcairo2
  libffi8 shared-mime-info fonts-liberation

Security rules (ADR 0009, NFR-PRIV-3):
- All data rendered in the PDF comes from the server-resolved report payload
  (hub names, hire details, benchmark notes).  No client-supplied strings
  are echoed into the document body or filename.
- The caller's hub scope is applied by the endpoint BEFORE this module is
  called; this module renders whatever it receives.
- The URL fetcher passed to WeasyPrint (_deny_all_fetcher) only resolves
  file:// URIs under the local assets directory and data: URIs.  All
  http:// and https:// requests are refused to prevent SSRF.
"""

from __future__ import annotations

import html
import pathlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.report.models import ReportResponse

# ---------------------------------------------------------------------------
# Asset paths
# ---------------------------------------------------------------------------

_ASSETS_DIR = pathlib.Path(__file__).parent.parent / "assets"
_FONTS_DIR = _ASSETS_DIR / "fonts"

# Resolved at import time so missing font files surface early.
_FONT_FILES = {
    "regular": _FONTS_DIR / "poppins-regular.woff2",
    "500": _FONTS_DIR / "poppins-v24-latin_latin-ext-500.woff2",
    "600": _FONTS_DIR / "poppins-v24-latin_latin-ext-600.woff2",
    "700": _FONTS_DIR / "poppins-v24-latin_latin-ext-700.woff2",
}


def _font_src(weight_key: str) -> str:
    """Return a CSS src() value for the given Poppins weight.

    Uses a ``file://`` URI that the deny-all fetcher permits.
    Falls back gracefully if the file is absent (dev without fonts vendored).
    """
    p = _FONT_FILES.get(weight_key)
    if p is None or not p.exists():
        return "local('Poppins')"
    return f"url('file://{p.as_posix()}') format('woff2')"


def _deny_all_fetcher(url: str, timeout: int = 10) -> dict:  # type: ignore[type-arg]
    """WeasyPrint URL fetcher that blocks all network requests.

    Only ``data:`` URIs and ``file://`` paths under _ASSETS_DIR are allowed.
    Everything else raises ``ValueError``, which WeasyPrint surfaces as a
    resource-load warning — not a fatal error — so the PDF still renders
    without the blocked resource.
    """
    if url.startswith("data:"):
        from weasyprint.urls import default_url_fetcher  # noqa: PLC0415

        return default_url_fetcher(url, timeout=timeout)  # type: ignore[no-any-return]

    assets_prefix = f"file://{_ASSETS_DIR.as_posix()}"
    if url.startswith(assets_prefix):
        from weasyprint.urls import default_url_fetcher  # noqa: PLC0415

        return default_url_fetcher(url, timeout=timeout)  # type: ignore[no-any-return]

    raise ValueError(f"PDF renderer: URL blocked by deny-all fetcher (SSRF protection): {url!r}")


# ---------------------------------------------------------------------------
# Symphony design tokens mirrored from frontend/src/theme/tokens.ts
# ---------------------------------------------------------------------------

_COLORS = {
    "black": "#000000",
    "white": "#ffffff",
    "primary": "#E8D5B0",  # warm sand — brand accent
    "navy": "#1A2B4A",  # deep navy
    "lightBlue": "#5B9BD5",  # sky blue
    "blueGrey": "#8BA0B4",  # mid grey-blue
    "peach": "#F4A261",  # soft peach
    "lightGrey": "#F5F5F5",
    "divider": "#E0E0E0",
}

# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------


def _esc(value: object) -> str:
    """HTML-escape a value for safe embedding in the document."""
    return html.escape(str(value))


def _format_num(value: object) -> str:
    """Format a numeric value as a comma-separated string."""
    try:
        return f"{int(float(str(value))):,}"
    except (ValueError, TypeError):
        return _esc(value)


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------


def _kpi_table(report: ReportResponse) -> str:
    kpis = report.data.kpis
    if kpis is None:
        return "<p><em>No hire data for this period.</em></p>"
    return f"""
    <table class="summary-table">
      <tr><th>Total hires</th><td>{_esc(kpis.total)}</td>
          <th>WF</th><td>{_esc(kpis.wf)}</td>
          <th>Non-WF</th><td>{_esc(kpis.non_wf)}</td>
      </tr>
      <tr>
        <th>Above midpoint</th>
        <td>{_esc(kpis.above)} ({_esc(round(kpis.above_pct * 100, 1))}%)</td>
        <th>At midpoint</th>
        <td>{_esc(kpis.at_mid)} ({_esc(round(kpis.at_mid_pct * 100, 1))}%)</td>
        <th>Below midpoint</th>
        <td>{_esc(kpis.below)} ({_esc(round(kpis.below_pct * 100, 1))}%)</td>
      </tr>
    </table>
    """


def _hub_rows_table(report: ReportResponse) -> str:
    if not report.data.hub_rows:
        return "<p><em>No hires for this period.</em></p>"

    rows_html = ""
    for hub_row in report.data.hub_rows:
        if not hub_row.has_data:
            continue
        rows_html += (
            f"<tr class='hub-header'>"
            f"<td colspan='5'>{_esc(hub_row.hub)}"
            f"{' — ' + _esc(hub_row.city_note) if hub_row.city_note else ''}</td>"
            f"</tr>"
        )
        for type_row in hub_row.rows:
            rows_html += (
                f"<tr>"
                f"<td class='type'>{_esc(type_row.hire_type)}</td>"
                f"<td class='num'>{_esc(type_row.total)}</td>"
                f"<td class='num'>{_esc(type_row.above)}</td>"
                f"<td class='num'>{_esc(type_row.at_mid)}</td>"
                f"<td class='num'>{_esc(type_row.below)}</td>"
                f"</tr>"
            )

    if not rows_html:
        return "<p><em>No hires for this period.</em></p>"

    return f"""
    <table>
      <thead>
        <tr>
          <th>Type</th>
          <th class="num">Total</th>
          <th class="num">Above mid</th>
          <th class="num">At mid</th>
          <th class="num">Below mid</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
    """


def _above_detail_table(report: ReportResponse) -> str:
    if not report.data.above_detail:
        return ""

    rows_html = ""
    for entry in report.data.above_detail:
        salary_str = _format_num(entry.salary) if entry.salary is not None else "—"
        mid_str = _format_num(entry.midpoint) if entry.midpoint is not None else "—"
        gap_str = f"{_esc(round(entry.gap_pct * 100, 1))}%" if entry.gap_pct is not None else "—"
        rows_html += (
            f"<tr>"
            f"<td>{_esc(entry.position)}</td>"
            f"<td>{_esc(entry.seniority)}</td>"
            f"<td>{_esc(entry.hub)}</td>"
            f"<td class='num'>{salary_str}</td>"
            f"<td class='num'>{mid_str}</td>"
            f"<td class='num'>{gap_str}</td>"
            f"<td>{_esc(entry.recruiter)}</td>"
            f"</tr>"
        )
        if entry.comment:
            rows_html += (
                f"<tr class='comment-row'>"
                f"<td colspan='7' class='comment'>{_esc(entry.comment)}</td>"
                f"</tr>"
            )

    return f"""
    <section class="above-detail">
      <h2>Above-midpoint hires</h2>
      <table>
        <thead>
          <tr>
            <th>Position</th>
            <th>Seniority</th>
            <th>Hub</th>
            <th class="num">Salary (EUR)</th>
            <th class="num">Midpoint (EUR)</th>
            <th class="num">Gap %</th>
            <th>Recruiter</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </section>
    """


# ---------------------------------------------------------------------------
# Full HTML document
# ---------------------------------------------------------------------------


def render_pdf_html(report: ReportResponse) -> str:
    """Render the report as a self-contained HTML string for WeasyPrint.

    All values are HTML-escaped before insertion.  The report object is the
    server-resolved payload — hub names and hire data come from the DB and
    Sheet snapshot after scope intersection.

    Fonts are loaded from the local assets directory via file:// URIs which
    are permitted by _deny_all_fetcher.  All colours are drawn from the
    Symphony design token surface (_COLORS dict above).
    """
    import datetime as _dt  # noqa: PLC0415

    period_label = _esc(f"{report.period} {report.year}")
    stale_banner = (
        '<p class="stale-banner">Warning: Data may be stale — last live fetch failed.</p>'
        if report.stale
        else ""
    )

    benchmark_note = ""
    if report.data.benchmark_note:
        benchmark_note = (
            f'<p class="benchmark-note"><strong>Benchmark note:</strong> '
            f"{_esc(report.data.benchmark_note)}</p>"
        )

    yoy_section = ""
    if report.previous_year_data and not report.previous_year_missing:
        prev_kpis = report.previous_year_data.kpis
        prev_label = _esc(f"{report.period} {report.previous_year}")
        if prev_kpis:
            yoy_section = f"""
            <section class="yoy">
              <h2>Year-over-year: {prev_label}</h2>
              <table class="summary-table">
                <tr>
                  <th>Total</th><td>{_esc(prev_kpis.total)}</td>
                  <th>WF</th><td>{_esc(prev_kpis.wf)}</td>
                  <th>Non-WF</th><td>{_esc(prev_kpis.non_wf)}</td>
                </tr>
              </table>
            </section>
            """

    generated_at = _esc(_dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d %H:%M UTC"))

    c = _COLORS
    font_css = f"""
    @font-face {{
      font-family: 'Poppins';
      font-weight: 400;
      font-style: normal;
      src: {_font_src("regular")};
    }}
    @font-face {{
      font-family: 'Poppins';
      font-weight: 500;
      font-style: normal;
      src: {_font_src("500")};
    }}
    @font-face {{
      font-family: 'Poppins';
      font-weight: 600;
      font-style: normal;
      src: {_font_src("600")};
    }}
    @font-face {{
      font-family: 'Poppins';
      font-weight: 700;
      font-style: normal;
      src: {_font_src("700")};
    }}
    """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Symphony TA Hiring Report – {period_label}</title>
  <style>
    {font_css}
    @page {{
      size: A4 landscape;
      margin: 2cm;
    }}
    body {{
      font-family: 'Poppins', sans-serif;
      font-size: 9pt;
      color: {c["black"]};
      line-height: 1.4;
    }}
    h1 {{ font-size: 14pt; margin-bottom: 4pt; color: {c["navy"]}; font-weight: 700; }}
    h2 {{
      font-size: 11pt; margin-top: 16pt; margin-bottom: 4pt;
      color: {c["navy"]}; font-weight: 600;
    }}
    .stale-banner {{
      background: {c["primary"]}; border: 1px solid {c["peach"]};
      padding: 4pt 8pt; border-radius: 2pt; font-size: 8pt; color: {c["black"]};
    }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 12pt; }}
    th, td {{ text-align: left; padding: 3pt 6pt; border-bottom: 1px solid {c["divider"]}; }}
    th {{ background: {c["lightGrey"]}; font-weight: 600; color: {c["black"]}; }}
    .hub-header td {{
      background: {c["navy"]}; color: {c["white"]};
      font-weight: 700; padding: 4pt 6pt;
    }}
    .type {{ font-weight: 600; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .comment-row td {{ font-style: italic; color: {c["blueGrey"]}; padding-left: 24pt; }}
    .benchmark-note {{ font-size: 8pt; color: {c["blueGrey"]}; margin: 8pt 0; }}
    .summary-table {{ width: auto; }}
    .confidential {{
      text-align: center; font-size: 7pt; color: {c["blueGrey"]};
      border-top: 1px solid {c["divider"]}; padding-top: 4pt; margin-top: 16pt;
    }}
  </style>
</head>
<body>
  <h1>Symphony TA Hiring Report – {period_label}</h1>
  {stale_banner}
  <section class="kpis">
    <h2>Key figures</h2>
    {_kpi_table(report)}
  </section>
  {benchmark_note}
  <section class="hub-breakdown">
    <h2>Hub breakdown</h2>
    {_hub_rows_table(report)}
  </section>
  {_above_detail_table(report)}
  {yoy_section}
  <p class="confidential">
    STRICTLY CONFIDENTIAL — internal use only. Generated {generated_at}
  </p>
</body>
</html>"""


def html_to_pdf(html_content: str) -> bytes:
    """Convert HTML to PDF bytes using WeasyPrint.

    This is a synchronous call; the endpoint wraps it in ``asyncio.to_thread``
    so the event loop is not blocked during PDF rendering.

    The deny-all URL fetcher is passed explicitly to block all network
    requests from the renderer (SSRF protection, P1-6).
    """
    import weasyprint  # noqa: PLC0415 — deferred to avoid import overhead at startup

    return weasyprint.HTML(string=html_content, url_fetcher=_deny_all_fetcher).write_pdf()  # type: ignore[no-any-return]
