# TA Hiring Report — Production Setup Guide

## What This Does

The `generate_report.py` script connects directly to your Google Sheet,
reads the Report Template tab, computes all period stats, and produces
`TA_Hiring_Report_2026.html` — a self-contained dashboard anyone on your
team can open in any browser. No Excel export needed.

---

## Prerequisites

- Python 3.8+ installed on your machine
- Access to your company Google Workspace account
- The Google Sheet already set up (the one you've been using)

---

## Step 1 — Install Python dependencies

Open a terminal (Command Prompt on Windows, Terminal on Mac) and run:

```
pip install gspread google-auth pandas openpyxl
```

---

## Step 2 — Create a Google Cloud Service Account (~10 min, one-time)

This is the "bot account" that the script uses to read your Sheet.

1. Go to https://console.cloud.google.com
   - Sign in with your **company** Google account (@yourcompany.com)

2. Click the project dropdown (top-left) → **New Project**
   - Name: `ta-reporting` → Create

3. In the search bar, search **"Google Sheets API"** → click Enable

4. Search **"Google Drive API"** → click Enable

5. Go to **IAM & Admin → Service Accounts** (left sidebar)
   → Click **+ Create Service Account**
   - Name: `ta-report-bot`
   - Click through (no special roles needed) → Done

6. Click on the service account you just created
   → Go to **Keys** tab → **Add Key → Create New Key → JSON**
   → A file downloads (e.g. `ta-reporting-abc123.json`)

7. **Rename it to `credentials.json`** and place it in the same folder
   as `generate_report.py`

> ⚠️ Keep `credentials.json` private. Do not share it or commit it to git.

---

## Step 3 — Share your Google Sheet with the service account

1. Open the service account you created in Google Cloud Console
2. Copy the **email address** — it looks like:
   `ta-report-bot@ta-reporting-abc123.iam.gserviceaccount.com`

3. Open your Google Sheet → click **Share** (top-right)
4. Paste that email address → set permission to **Viewer** → Send

The script can now read your Sheet.

---

## Step 4 — Configure the script

Open `generate_report.py` in any text editor and update the CONFIGURATION
section near the top:

```python
CREDENTIALS_FILE = "credentials.json"   # ← path to your downloaded key

SPREADSHEET_ID = "1QQ4EW7_XhVdQmrLQKAWVF9MESxvv8EYiGUotzqnxzcE"  # ← already set

OUTPUT_FOLDER = "."    # ← change to your shared folder path, e.g.:
                       #   "C:/Users/YourName/Google Drive/TA Reports"
                       #   or "/Users/yourname/Google Drive/TA Reports"
```

---

## Step 5 — Run the script

```
python generate_report.py
```

You should see:
```
📊  TA Hiring Report Generator
========================================
✓  Connected to: Hiring Monthly Report Template - 2026
   Loading Report Template sheet...
   Loaded 78 rows from Report Template
   Computing period statistics...

✅  Report generated: ./TA_Hiring_Report_2026.html
```

Open `TA_Hiring_Report_2026.html` in Chrome, Firefox, or Edge.

---

## Step 6 — Save to a shared Google Drive folder (recommended)

1. Create a folder in your company Google Drive called `TA Reports 2026`
2. Install **Google Drive for Desktop** (if not already installed)
   - It creates a local folder that syncs automatically
3. Set `OUTPUT_FOLDER` in the script to that local sync folder path
4. Every time you run the script, the HTML refreshes in Drive instantly
5. Share the Drive folder with stakeholders — they just open the file

---

## Adding Comments for Future Above Mid-Point Hires

When new hires are above the midpoint and you want their justification
to appear in the report, add them to the `COMMENTS_LOOKUP` dictionary
in `generate_report.py`:

```python
COMMENTS_LOOKUP = {
    # Format: (Position, Seniority, City, Salary_as_int): "Your comment here"
    ("BE Engineer", "Senior", "Belgrade", 5800): "Approved by VP — critical hire for Q2 project.",
    # ... existing entries ...
}
```

---

## Offline / Testing Mode

To run without connecting to Google Sheets (useful for testing):

```
python generate_report.py --offline --excel "your_file.xlsx"
```

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Credentials file not found` | Check `credentials.json` is in the same folder as the script |
| `Could not open spreadsheet` | Make sure you shared the Sheet with the service account email |
| `gspread not found` | Run `pip install gspread google-auth` |
| `Permission denied` on output | Check you have write access to the OUTPUT_FOLDER |

---

## Folder Structure

```
TA REPORTING/
├── generate_report.py          ← the script (run this)
├── credentials.json            ← your service account key (keep private!)
├── TA_Hiring_Report_2026.html  ← the generated report (open in browser)
└── SETUP_GUIDE.md              ← this file
```
