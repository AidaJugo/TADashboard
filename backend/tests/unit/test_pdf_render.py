"""WeasyPrint smoke test — html_to_pdf produces a real PDF (M6 carry-over #4).

This test calls ``html_to_pdf`` without mocking WeasyPrint.  It is the
regression guard for the Pillow/_imaging import failure that caused
every PDF export request to return 500 when the dev venv was contaminated
by macOS-native wheels (see fix/pdf-export-venv-isolation).

The test is skipped automatically on environments where WeasyPrint is not
installed (e.g. a bare macOS checkout without system libs).  It runs green
inside the Docker backend image where all system dependencies are present
(libpango, libcairo, etc. — see backend/Dockerfile).

docs/testing.md FR-REPORT-10, TC-I-API-7.
"""

from __future__ import annotations

import datetime

import pytest

# WeasyPrint requires system libraries (libpango, libgobject, libcairo) that are
# present in the Docker backend image but not on a bare macOS host.  Importing
# weasyprint raises OSError (cffi dlopen failure) — not ImportError — when those
# libs are missing, so pytest.importorskip is not sufficient.  We catch both and
# skip the test on environments without the full system dependency stack.
try:
    import weasyprint as _weasyprint  # noqa: F401

    _WEASYPRINT_AVAILABLE = True
except (ImportError, OSError):
    _WEASYPRINT_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _WEASYPRINT_AVAILABLE,
    reason=(
        "WeasyPrint system libs (libpango, libgobject, libcairo) not available "
        "— skipping (runs in Docker CI only)"
    ),
)


from app.report.models import KpiBlock, PeriodData, ReportResponse  # noqa: E402
from app.report.pdf import html_to_pdf, render_pdf_html  # noqa: E402


def _minimal_report() -> ReportResponse:
    kpis = KpiBlock(
        total=2,
        wf=1,
        non_wf=1,
        above=1,
        above_pct=0.5,
        at_mid=1,
        at_mid_pct=0.5,
        below=0,
        below_pct=0.0,
        no_salary=0,
        no_salary_pct=0.0,
    )
    data = PeriodData(
        kpis=kpis,
        hub_rows=[],
        above_detail=[],
        has_data=True,
    )
    return ReportResponse(
        year=2026,
        period="Annual",
        stale=False,
        fetched_at=datetime.datetime(2026, 4, 21, 12, 0, tzinfo=datetime.UTC),
        data=data,
    )


def test_html_to_pdf_returns_pdf_bytes() -> None:
    """html_to_pdf returns bytes that start with the PDF magic number.

    Covers FR-REPORT-10 and the WeasyPrint/Pillow import path.
    A failure here means WeasyPrint or one of its system dependencies
    (libpango, libcairo, Pillow _imaging extension) is broken in the
    current environment.
    """
    report = _minimal_report()

    html_content = render_pdf_html(report)

    pdf_bytes = html_to_pdf(html_content)

    assert isinstance(pdf_bytes, bytes), "html_to_pdf must return bytes"
    assert pdf_bytes[:4] == b"%PDF", (
        f"Output does not start with PDF magic bytes. "
        f"Got: {pdf_bytes[:20]!r}. "
        f"Likely cause: WeasyPrint or Pillow (_imaging) failed to import correctly."
    )
