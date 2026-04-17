# Legacy prototype

Do not edit files in this directory.

This is Enis Kudo's validated prototype, preserved as the reference for:

- The aggregation logic that `backend/app/report/` must reproduce.
- The HTML/CSS/Chart.js dashboard that `frontend/src/` must port to components.
- The test fixture structure (see `Hiring_Report_TEST_DATA.xlsx`).

If you need to update the prototype, do it in the new codebase and update docs. The prototype is frozen.

## Files

- `generate_report.py`: single-file Python script that reads a Google Sheet, computes stats, emits a self-contained HTML dashboard.
- `SETUP_GUIDE.md`: original setup guide for the prototype.
- `Hiring_Report_TEST_DATA.xlsx`: offline test data in the same shape as the Sheet.

## Running the prototype (for reference only)

```bash
cd legacy
python -m venv .venv
source .venv/bin/activate
pip install gspread google-auth pandas openpyxl
python generate_report.py --offline
```
