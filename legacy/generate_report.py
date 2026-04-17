"""
TA Hiring Report Generator — Production Version
================================================
Reads live data from Google Sheets and generates the HTML dashboard.

SETUP (one-time):
    pip install gspread google-auth pandas openpyxl

USAGE:
    python generate_report.py

    Or with a custom output folder:
    python generate_report.py --output "/path/to/shared/folder"

CONFIGURATION (edit the section below):
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ── CONFIGURATION ─────────────────────────────────────────────────────────────
# Path to your Google Service Account credentials JSON file
# Download from: Google Cloud Console → IAM → Service Accounts → Keys → JSON
CREDENTIALS_FILE = "credentials.json"

# Your Google Sheet ID — copy from the URL:
# https://docs.google.com/spreadsheets/d/  >>>THIS PART<<<  /edit
SPREADSHEET_ID = "1QQ4EW7_XhVdQmrLQKAWVF9MESxvv8EYiGUotzqnxzcE"

# Where to save the HTML report (defaults to same folder as this script)
OUTPUT_FOLDER = "."

# Report filename
OUTPUT_FILENAME = "TA_Hiring_Report_2026.html"
# ── END CONFIGURATION ─────────────────────────────────────────────────────────


def load_sheet_as_dataframe(sheet, header_row=0):
    """Load a worksheet into a pandas DataFrame."""
    import pandas as pd
    data = sheet.get_all_values()
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data[header_row + 1:], columns=data[header_row])
    return df


def connect_to_sheets():
    """Authenticate and return the spreadsheet object."""
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]

    if not os.path.exists(CREDENTIALS_FILE):
        print(f"\n❌  Credentials file not found: {CREDENTIALS_FILE}")
        print("    Download it from Google Cloud Console → IAM & Admin → Service Accounts → Keys → JSON")
        print("    Then place it in the same folder as this script.\n")
        sys.exit(1)

    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    client = gspread.authorize(creds)

    try:
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        print(f"✓  Connected to: {spreadsheet.title}")
        return spreadsheet
    except Exception as e:
        print(f"\n❌  Could not open spreadsheet: {e}")
        print(f"    Make sure you shared the sheet with the service account email.")
        sys.exit(1)


def load_data(spreadsheet):
    """Load Report Template sheet into a clean DataFrame."""
    import pandas as pd

    print("   Loading Report Template sheet...")
    sheet = spreadsheet.worksheet("Report Template")
    df = load_sheet_as_dataframe(sheet, header_row=0)

    # Rename columns to match expected structure
    col_map = {
        df.columns[0]: "Position",
        df.columns[1]: "Seniority",
        df.columns[2]: "City",
        df.columns[3]: "Salary",
        df.columns[4]: "Midpoint",
        df.columns[5]: "Gap_EUR",
        df.columns[6]: "Gap_PCT",
        df.columns[7]: "Status",
        df.columns[8]: "Month",
        df.columns[9]: "Type",
    }
    df = df.rename(columns=col_map)
    df = df[list(col_map.values())]

    # Clean and type-cast
    for col in ["Position", "Seniority", "City", "Status", "Month", "Type"]:
        df[col] = df[col].str.strip()

    for col in ["Salary", "Midpoint", "Gap_EUR", "Gap_PCT"]:
        df[col] = pd.to_numeric(df[col].replace("", None), errors="coerce")

    # Drop completely empty rows
    df = df.dropna(subset=["Position"]).reset_index(drop=True)
    print(f"   Loaded {len(df)} rows from Report Template")
    return df


# ── COMMENTS from JanFebMar tab (update this as you add new comments) ─────────
COMMENTS_LOOKUP = {
    ("Data Analyst", "Senior", "Sarajevo", 6000): "Hired before introduction of new salary ranges",
    ("BE Engineer", "Medior", "Sarajevo", 3634): "Strong Medior — difference of 34 euros is negligible.",
    ("Delivery Manager", "Medior", "Sarajevo", 3887): "Approval for hiring received from VP of Client Services",
    ("QA Engineer", "Medior", "Belgrade", 3894): "All three candidates were hired prior to the introduction of the new salary ranges.",
    ("QA Engineer", "Senior", "Belgrade", 5701): "All three candidates were hired prior to the introduction of the new salary ranges.",
    ("BE Engineer", "Intermediate", "Skopje", 3065): "Hired in January 2026, prior to the introduction of new salary ranges for mediors.",
    ("AI/ML Engineer", "Principal", "Skopje", 7222): "Short-term engagement for Bain — special approval received.",
    ("BE Engineer", "Intermediate", "Skopje", 2210): "Irrelevant difference compared to midpoint due to currency conversion.",
    ("FS Engineer", "Intermediate", "Skopje", 2210): "Irrelevant difference compared to midpoint due to currency conversion.",
    ("BE Engineer", "Intermediate", "Skopje", 2441): "Approved by WFM team — candidate received a salary increase in their current company.",
    ("QA Engineer", "Senior", "Medellin", 7162): "Approved by Senior Client Partner and VP of Client Services for AlixPartners.",
    ("BE Engineer", "Medior", "Medellin", 5448): "",
    ("FE Engineer", "Medior", "Medellin", 5493): "",
    ("DevOps Engineer", "Principal", "Medellin", 10000): "",
    ("DevOps Engineer", "Senior", "Medellin", 7671): "",
    ("FS Engineer", "Staff", "Medellin", 6753): "Special approval received for hiring for DC.",
}

BENCHMARK_NOTES = {
    "Jan": "No salary data for: UX/UI Designer (Remote, WFM) and TA Specialist (Medellin, NonWFM).",
    "Feb": "No salary data for: VP of Operations (Remote, NonWFM).",
    "Mar": "",
    "Q1": "Not benchmarked (3 hires): TA Specialist in Medellin, VP of Operations (Remote), and Product Designer in London (hired as consultant for Metrobank).",
    "H1": "Not benchmarked (3 hires): TA Specialist in Medellin, VP of Operations (Remote), and Product Designer in London. H1 2026 reflects Q1 data only.",
    "Annual": "Not benchmarked (3 hires): TA Specialist in Medellin, VP of Operations (Remote), and Product Designer in London. Annual 2026 reflects Q1 data only.",
}

CITY_NOTES = {
    "Medellin": "In agreement with VP of Finance, Belgrade salary ranges are used as the reference point for Medellin.",
    "Remote": "In agreement with VP of Finance, Belgrade salary ranges are used as the reference point for Remote Hub.",
}

CITY_PAIRS = [("Sarajevo", "Banja Luka"), ("Belgrade", "Novi Sad"), ("Nis", "Skopje"), ("Medellin", "Remote")]
STATUSES = ["Below", "At mid-point", "Above", "No salary"]
TYPES = ["WFM", "NonWFM"]


def compute_period(df_p):
    if len(df_p) == 0:
        return {"has_data": False}

    total = len(df_p)

    def tbl(sub):
        r = {s: int(len(sub[sub["Status"] == s])) for s in STATUSES}
        r["Total"] = int(len(sub))
        return r

    summary = {t: tbl(df_p[df_p["Type"] == t]) for t in TYPES}
    summary["Total"] = tbl(df_p)

    city_data = {}
    for pair in CITY_PAIRS:
        for city in pair:
            dc = df_p[df_p["City"] == city]
            if len(dc) == 0:
                city_data[city] = {"has_data": False, "total": 0, "rows": {}}
                continue
            cr = {t: tbl(dc[dc["Type"] == t]) for t in TYPES}
            cr["Total"] = tbl(dc)
            city_data[city] = {"has_data": True, "total": int(len(dc)), "rows": cr, "note": CITY_NOTES.get(city, "")}

    above_detail = []
    for city in ["Sarajevo", "Belgrade", "Skopje", "Medellin"]:
        rows_above = df_p[(df_p["City"] == city) & (df_p["Status"] == "Above")]
        if len(rows_above) == 0:
            continue
        entries = []
        for _, r in rows_above.iterrows():
            sal = float(r["Salary"]) if r["Salary"] == r["Salary"] else None
            key = (str(r["Position"]).strip(), str(r["Seniority"]).strip(), city, int(sal) if sal else None)
            entries.append({
                "position": str(r["Position"]).strip(),
                "seniority": str(r["Seniority"]).strip(),
                "salary": sal,
                "midpoint": float(r["Midpoint"]) if r["Midpoint"] == r["Midpoint"] else None,
                "gap_eur": float(r["Gap_EUR"]) if r["Gap_EUR"] == r["Gap_EUR"] else None,
                "gap_pct": float(r["Gap_PCT"]) if r["Gap_PCT"] == r["Gap_PCT"] else None,
                "comment": COMMENTS_LOOKUP.get(key, ""),
            })
        above_detail.append({"city": city, "rows": entries})

    city_totals = {c: int(len(df_p[df_p["City"] == c])) for pair in CITY_PAIRS for c in pair}
    wfm_n = len(df_p[df_p["Type"] == "WFM"])
    below_n = len(df_p[df_p["Status"] == "Below"])
    above_n = len(df_p[df_p["Status"] == "Above"])
    at_n = len(df_p[df_p["Status"] == "At mid-point"])
    no_n = len(df_p[df_p["Status"] == "No salary"])

    return {
        "has_data": True,
        "kpis": {
            "total": total, "wfm": wfm_n, "non_wfm": total - wfm_n,
            "below": below_n, "below_pct": round(below_n / total * 100, 1),
            "above": above_n, "above_pct": round(above_n / total * 100, 1),
            "at_mid": at_n, "at_mid_pct": round(at_n / total * 100, 1),
            "no_sal": no_n, "no_sal_pct": round(no_n / total * 100, 1),
        },
        "summary": summary,
        "city_data": city_data,
        "above_detail": above_detail,
        "city_totals": city_totals,
    }


def build_period_data(df):
    """Build stats for all periods from the loaded DataFrame."""
    import pandas as pd

    # Detect available months dynamically
    available_months = df["Month"].dropna().unique().tolist()
    all_months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    DATA = {}
    for m in all_months:
        DATA[m] = compute_period(df[df["Month"] == m])

    # Quarters
    DATA["Q1"] = compute_period(df[df["Month"].isin(["Jan", "Feb", "Mar"])])
    DATA["Q2"] = compute_period(df[df["Month"].isin(["Apr", "May", "Jun"])])
    DATA["Q3"] = compute_period(df[df["Month"].isin(["Jul", "Aug", "Sep"])])
    DATA["Q4"] = compute_period(df[df["Month"].isin(["Oct", "Nov", "Dec"])])

    # Half-years
    DATA["H1"] = compute_period(df[df["Month"].isin(["Jan", "Feb", "Mar", "Apr", "May", "Jun"])])
    DATA["H2"] = compute_period(df[df["Month"].isin(["Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])])

    # Annual
    DATA["Annual"] = compute_period(df)

    for k in DATA:
        DATA[k]["benchmark_note"] = BENCHMARK_NOTES.get(k, "")

    return DATA


def generate_html(DATA, generated_at):
    """Return the complete HTML string."""
    DATA_JSON = json.dumps(DATA)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TA Hiring Report · 2026</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;background:#F0F2F5;color:#2D3748;min-height:100vh}}
.header{{background:linear-gradient(135deg,#1B2855 0%,#2E4170 100%);padding:0 32px;display:flex;align-items:center;justify-content:space-between;height:68px;box-shadow:0 2px 8px rgba(0,0,0,0.25)}}
.header-left{{display:flex;align-items:center;gap:14px}}
.header-icon{{width:40px;height:40px;background:rgba(255,255,255,0.15);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:20px}}
.header-title h1{{color:#fff;font-size:18px;font-weight:700;letter-spacing:.3px}}
.header-title p{{color:rgba(255,255,255,0.65);font-size:12px;margin-top:1px}}
.header-right{{display:flex;align-items:center;gap:12px}}
.header-badge{{background:rgba(255,255,255,0.12);color:rgba(255,255,255,0.8);font-size:11px;padding:4px 10px;border-radius:20px;border:1px solid rgba(255,255,255,0.2)}}
.header-updated{{color:rgba(255,255,255,0.45);font-size:10px}}
.period-nav{{background:#fff;border-bottom:1px solid #E2E8F0;box-shadow:0 1px 3px rgba(0,0,0,0.06)}}
.nav-top{{display:flex;gap:0;padding:0 32px;border-bottom:1px solid #EEF0F3}}
.nav-top-btn{{padding:13px 22px;font-size:13px;font-weight:600;color:#718096;background:none;border:none;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px;transition:all .15s}}
.nav-top-btn:hover{{color:#4A7FC1}}
.nav-top-btn.active{{color:#1B2855;border-bottom-color:#4A7FC1}}
.nav-sub{{display:flex;gap:4px;padding:8px 32px}}
.nav-sub-btn{{padding:5px 14px;font-size:12px;font-weight:500;color:#718096;background:#F7F8FA;border:1px solid #E2E8F0;border-radius:20px;cursor:pointer;transition:all .15s}}
.nav-sub-btn:hover{{background:#EBF2FA;color:#4A7FC1;border-color:#C3D9F0}}
.nav-sub-btn.active{{background:#1B2855;color:#fff;border-color:#1B2855}}
.nav-sub-btn.no-data{{opacity:.45;cursor:default}}
.main{{max-width:1320px;margin:0 auto;padding:28px 24px}}
.period-header{{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:20px}}
.period-title{{font-size:22px;font-weight:700;color:#1B2855}}
.period-subtitle{{font-size:13px;color:#718096;margin-top:3px}}
.partial-badge{{display:inline-flex;align-items:center;gap:5px;background:#FFF8E1;color:#B7791F;border:1px solid #F6D860;border-radius:20px;padding:4px 12px;font-size:11px;font-weight:600}}
.kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}}
.kpi-card{{background:#fff;border-radius:12px;padding:18px 20px;box-shadow:0 1px 4px rgba(0,0,0,0.07);border:1px solid #EEF0F3;position:relative;overflow:hidden}}
.kpi-card::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:12px 12px 0 0}}
.kpi-card.total::before{{background:#4A7FC1}}
.kpi-card.wfm::before{{background:#4299E1}}
.kpi-card.below::before{{background:#E53E3E}}
.kpi-card.above::before{{background:#38A169}}
.kpi-label{{font-size:11px;font-weight:600;color:#A0AEC0;text-transform:uppercase;letter-spacing:.6px;margin-bottom:8px}}
.kpi-value{{font-size:34px;font-weight:800;color:#1B2855;line-height:1}}
.kpi-sub{{font-size:12px;color:#718096;margin-top:5px}}
.kpi-pct{{font-size:13px;font-weight:600;margin-left:4px}}
.kpi-pct.bad{{color:#E53E3E}}.kpi-pct.good{{color:#38A169}}
.kpi-split{{display:flex;gap:12px;margin-top:8px}}
.kpi-split-item{{font-size:11px;color:#718096}}
.kpi-split-item span{{font-weight:700;color:#4A7FC1}}
.content-grid{{display:grid;grid-template-columns:1fr 360px;gap:20px;margin-bottom:20px}}
.card{{background:#fff;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,0.07);border:1px solid #EEF0F3}}
.card-header{{padding:16px 20px;border-bottom:1px solid #EEF0F3;display:flex;align-items:center;justify-content:space-between}}
.card-title{{font-size:14px;font-weight:700;color:#1B2855}}
.card-body{{padding:20px}}
table.report-tbl{{width:100%;border-collapse:collapse;font-size:13px}}
table.report-tbl th{{background:#F7F8FA;padding:9px 14px;text-align:center;font-size:11px;font-weight:700;color:#718096;text-transform:uppercase;letter-spacing:.4px;border-bottom:2px solid #E2E8F0}}
table.report-tbl th:first-child{{text-align:left}}
table.report-tbl td{{padding:10px 14px;text-align:center;border-bottom:1px solid #F0F2F5}}
table.report-tbl td:first-child{{text-align:left;font-weight:600}}
table.report-tbl tr.wfm-row td:first-child::before{{content:'';display:inline-block;width:8px;height:8px;border-radius:50%;background:#4299E1;margin-right:7px;vertical-align:middle}}
table.report-tbl tr.nonwfm-row td:first-child::before{{content:'';display:inline-block;width:8px;height:8px;border-radius:50%;background:#9F7AEA;margin-right:7px;vertical-align:middle}}
table.report-tbl tr.total-row{{background:#F9FAFB}}
table.report-tbl tr.total-row td{{font-weight:700;border-top:2px solid #E2E8F0;border-bottom:none}}
.num-below{{color:#E53E3E;font-weight:700}}.num-above{{color:#38A169;font-weight:700}}
.num-atm{{color:#D69E2E;font-weight:700}}.num-nosal{{color:#A0AEC0;font-weight:600}}
.benchmark-note{{margin-top:12px;padding:10px 14px;background:#FFFBF0;border-left:3px solid #D69E2E;border-radius:0 6px 6px 0;font-size:12px;color:#744210}}
.chart-container{{position:relative;height:220px}}
.section-title{{font-size:15px;font-weight:700;color:#1B2855;margin-bottom:14px;display:flex;align-items:center;gap:8px}}
.section-title::after{{content:'';flex:1;height:1px;background:#E2E8F0}}
.city-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px}}
.city-card{{background:#fff;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,0.07);border:1px solid #EEF0F3;overflow:hidden}}
.city-card-header{{background:#F7F8FA;padding:10px 14px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #EEF0F3}}
.city-name{{font-size:13px;font-weight:700;color:#1B2855}}
.city-total{{font-size:11px;font-weight:600;background:#1B2855;color:#fff;padding:2px 8px;border-radius:10px}}
.city-empty{{padding:20px;text-align:center;color:#A0AEC0;font-size:12px;font-style:italic}}
.city-note{{padding:6px 12px;font-size:11px;color:#744210;background:#FFFBF0;border-top:1px solid #F0E0C0}}
table.city-tbl{{width:100%;border-collapse:collapse;font-size:11.5px}}
table.city-tbl th{{background:#F9FAFB;padding:6px 10px;text-align:center;font-size:10px;font-weight:700;color:#A0AEC0;text-transform:uppercase;letter-spacing:.3px}}
table.city-tbl th:first-child{{text-align:left}}
table.city-tbl td{{padding:6px 10px;text-align:center;border-top:1px solid #F0F2F5}}
table.city-tbl td:first-child{{text-align:left;font-weight:600;font-size:11px}}
table.city-tbl tr.city-total-row td{{font-weight:700;background:#F9FAFB}}
.city-tbl .nb{{color:#E53E3E;font-weight:700}}.city-tbl .ab{{color:#38A169;font-weight:700}}
.city-tbl .am{{color:#D69E2E;font-weight:700}}.city-tbl .ns{{color:#A0AEC0}}
.above-section{{margin-bottom:24px}}
.city-above-group{{margin-bottom:16px}}
.city-above-header{{display:flex;align-items:center;gap:10px;margin-bottom:8px}}
.city-above-name{{font-size:13px;font-weight:700;color:#2D3748}}
.above-count-badge{{background:#FFF5F5;color:#E53E3E;border:1px solid #FED7D7;font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px}}
table.above-tbl{{width:100%;border-collapse:collapse;font-size:12px;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.06);border:1px solid #EEF0F3}}
table.above-tbl thead tr{{background:#F7F8FA}}
table.above-tbl th{{padding:9px 12px;text-align:left;font-size:10.5px;font-weight:700;color:#718096;text-transform:uppercase;letter-spacing:.4px;border-bottom:2px solid #E2E8F0}}
table.above-tbl th.num{{text-align:right}}
table.above-tbl td{{padding:10px 12px;border-bottom:1px solid #F0F2F5;vertical-align:top}}
table.above-tbl td.num{{text-align:right;font-variant-numeric:tabular-nums}}
table.above-tbl tr:last-child td{{border-bottom:none}}
table.above-tbl tr:nth-child(even){{background:#FAFBFC}}
.gap-positive{{color:#38A169;font-weight:700}}
.comment-cell{{font-size:11.5px;color:#4A5568;font-style:italic;max-width:320px}}
.comment-empty{{color:#CBD5E0;font-size:11px}}
.empty-state{{text-align:center;padding:80px 40px;background:#fff;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,0.07);border:1px solid #EEF0F3}}
.empty-icon{{font-size:48px;margin-bottom:16px}}
.empty-title{{font-size:18px;font-weight:700;color:#A0AEC0;margin-bottom:8px}}
.empty-sub{{font-size:13px;color:#CBD5E0}}
.footer{{text-align:center;padding:24px;font-size:11px;color:#CBD5E0;border-top:1px solid #E2E8F0;margin-top:8px}}
@media(max-width:1000px){{.content-grid{{grid-template-columns:1fr}}.kpi-grid{{grid-template-columns:repeat(2,1fr)}}.city-grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<header class="header">
  <div class="header-left">
    <div class="header-icon">👥</div>
    <div class="header-title">
      <h1>Talent Acquisition</h1>
      <p>Hiring Performance Report · 2026</p>
    </div>
  </div>
  <div class="header-right">
    <div class="header-badge">Workforce Analytics</div>
    <div class="header-updated">Updated: {generated_at}</div>
  </div>
</header>
<nav class="period-nav">
  <div class="nav-top">
    <button class="nav-top-btn active" onclick="switchGroup('monthly',this)">Monthly</button>
    <button class="nav-top-btn" onclick="switchGroup('quarterly',this)">Quarterly</button>
    <button class="nav-top-btn" onclick="switchGroup('halfyear',this)">Half-Year</button>
    <button class="nav-top-btn" onclick="switchGroup('annual',this)">Annual</button>
  </div>
  <div class="nav-sub" id="nav-sub"></div>
</nav>
<div class="main" id="main-content"></div>
<div class="footer">Talent Acquisition · Hiring Report 2026 · Data reflects offer acceptance dates · Generated {generated_at}</div>
<script>
const DATA={DATA_JSON};
const GROUPS={{monthly:{{keys:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],labels:{{Jan:'January',Feb:'February',Mar:'March',Apr:'April',May:'May',Jun:'June',Jul:'July',Aug:'August',Sep:'September',Oct:'October',Nov:'November',Dec:'December'}},full:{{Jan:'January 2026',Feb:'February 2026',Mar:'March 2026',Apr:'April 2026',May:'May 2026',Jun:'June 2026',Jul:'July 2026',Aug:'August 2026',Sep:'September 2026',Oct:'October 2026',Nov:'November 2026',Dec:'December 2026'}},default:'Jan'}},quarterly:{{keys:['Q1','Q2','Q3','Q4'],labels:{{Q1:'Q1',Q2:'Q2',Q3:'Q3',Q4:'Q4'}},full:{{Q1:'Q1 2026 — January to March',Q2:'Q2 2026 — April to June',Q3:'Q3 2026 — July to September',Q4:'Q4 2026 — October to December'}},default:'Q1'}},halfyear:{{keys:['H1','H2'],labels:{{H1:'H1',H2:'H2'}},full:{{H1:'H1 2026 — January to June',H2:'H2 2026 — July to December'}},default:'H1'}},annual:{{keys:['Annual'],labels:{{Annual:'2026'}},full:{{Annual:'Annual 2026'}},default:'Annual'}}}};
let currentGroup='monthly',currentPeriod='Jan',donutChart=null,barChart=null;
function switchGroup(g,btn){{document.querySelectorAll('.nav-top-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');currentGroup=g;currentPeriod=GROUPS[g].default||GROUPS[g].keys[0];renderSubNav();renderMain();}}
function switchPeriod(p){{currentPeriod=p;document.querySelectorAll('.nav-sub-btn').forEach(b=>b.classList.toggle('active',b.dataset.period===p));renderMain();}}
function renderSubNav(){{const g=GROUPS[currentGroup];document.getElementById('nav-sub').innerHTML=g.keys.map(k=>{{const hd=DATA[k]&&DATA[k].has_data;return`<button class="nav-sub-btn ${{k===currentPeriod?'active':''}} ${{!hd?'no-data':''}}" data-period="${{k}}" onclick="switchPeriod('${{k}}')">${{g.labels[k]}}</button>`;
}}).join('');}}
function fmt(n){{return n==null?'—':Math.round(n).toLocaleString();}}
function statusClass(col){{if(col==='Below')return'num-below';if(col==='Above')return'num-above';if(col==='At mid-point')return'num-atm';if(col==='No salary')return'num-nosal';return'';}}
function cityClass(col){{if(col==='Below')return'nb';if(col==='Above')return'ab';if(col==='At mid-point')return'am';if(col==='No salary')return'ns';return'';}}
function buildSummaryTable(d){{const cols=['Below','At mid-point','Above','No salary','Total'];const rows=[{{key:'WFM',cls:'wfm-row',label:'WFM'}},{{key:'NonWFM',cls:'nonwfm-row',label:'NonWFM'}},{{key:'Total',cls:'total-row',label:'Total'}}];let th=`<tr><th>Segment</th><th>Below Mid-Point</th><th>At Mid-Point</th><th>Above Mid-Point</th><th>No Salary / Not Benchmarked</th><th>Total</th></tr>`;let tb=rows.map(r=>{{let tds=cols.map(c=>{{const v=(d.summary[r.key]||{{}})[c]||0;const cl=r.cls==='total-row'?'':statusClass(c);return`<td class="${{cl}}">${{v||'—'}}</td>`;
}}).join('');return`<tr class="${{r.cls}}"><td>${{r.label}}</td>${{tds}}</tr>`;}}).join('');return`<table class="report-tbl"><thead>${{th}}</thead><tbody>${{tb}}</tbody></table>`;}}
function buildCityCard(city,d){{const cd=d.city_data[city];if(!cd||!cd.has_data)return`<div class="city-card"><div class="city-card-header"><span class="city-name">${{city}}</span><span class="city-total" style="background:#A0AEC0">0</span></div><div class="city-empty">No hires this period</div></div>`;const cols=['Below','At mid-point','Above','No salary','Total'];let th=`<tr><th></th><th>Below</th><th>At Mid</th><th>Above</th><th>No Sal.</th><th>Total</th></tr>`;let tb=['WFM','NonWFM','Total'].map(t=>{{const iT=t==='Total';let tds=cols.map(c=>{{const v=(cd.rows[t]||{{}})[c]||0;return`<td class="${{cityClass(c)}}">${{v||'—'}}</td>`;}}).join('');return`<tr class="${{iT?'city-total-row':''}}" ><td>${{t}}</td>${{tds}}</tr>`;}}).join('');const nt=cd.note?`<div class="city-note">ⓘ ${{cd.note}}</div>`:'';return`<div class="city-card"><div class="city-card-header"><span class="city-name">${{city}}</span><span class="city-total">${{cd.total}}</span></div><table class="city-tbl"><thead>${{th}}</thead><tbody>${{tb}}</tbody></table>${{nt}}</div>`;}}
function buildAboveSection(d){{if(!d.above_detail||!d.above_detail.length)return'';let h=`<div class="section-title">Above Mid-Point — Exceptions &amp; Justifications</div><div class="above-section">`;d.above_detail.forEach(g=>{{h+=`<div class="city-above-group"><div class="city-above-header"><span class="city-above-name">${{g.city}}</span><span class="above-count-badge">${{g.rows.length}} hire${{g.rows.length>1?'s':''}}</span></div><table class="above-tbl"><thead><tr><th>Position</th><th>Seniority</th><th class="num">Salary (€)</th><th class="num">Midpoint (€)</th><th class="num">Gap (€)</th><th class="num">Gap (%)</th><th>Justification</th></tr></thead><tbody>`;g.rows.forEach(r=>{{const gp=r.gap_pct!=null?(r.gap_pct*100).toFixed(1)+'%':'—';const cm=r.comment?`<span class="comment-cell">${{r.comment}}</span>`:`<span class="comment-empty">—</span>`;h+=`<tr><td><strong>${{r.position}}</strong></td><td>${{r.seniority}}</td><td class="num">${{r.salary!=null?r.salary.toLocaleString():'—'}}</td><td class="num">${{r.midpoint!=null?r.midpoint.toLocaleString():'—'}}</td><td class="num gap-positive">+${{r.gap_eur!=null?r.gap_eur.toLocaleString():'—'}}</td><td class="num gap-positive">+${{gp}}</td><td>${{cm}}</td></tr>`;}});h+=`</tbody></table></div>`;}});h+=`</div>`;return h;}}
function renderCharts(d){{if(donutChart){{donutChart.destroy();donutChart=null;}}if(barChart){{barChart.destroy();barChart=null;}}const k=d.kpis;const dc=document.getElementById('donut-chart');if(dc){{donutChart=new Chart(dc,{{type:'doughnut',data:{{labels:['Below Mid-Point','At Mid-Point','Above Mid-Point','No Salary'],datasets:[{{data:[k.below,k.at_mid,k.above,k.no_sal],backgroundColor:['#FC8181','#F6E05E','#68D391','#CBD5E0'],borderWidth:2,borderColor:'#fff'}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{position:'bottom',labels:{{font:{{size:11}},padding:10,usePointStyle:true}}}},tooltip:{{callbacks:{{label:function(c){{const t=c.dataset.data.reduce((a,b)=>a+b,0);return` ${{c.label}}: ${{c.parsed}} (${{(c.parsed/t*100).toFixed(1)}}%)`;}}}}}}}}}});}}const bc=document.getElementById('bar-chart');if(bc&&d.city_totals){{const cities=[['Sarajevo','Banja Luka'],['Belgrade','Novi Sad'],['Nis','Skopje'],['Medellin','Remote']].flat();const vals=cities.map(c=>d.city_totals[c]||0);barChart=new Chart(bc,{{type:'bar',data:{{labels:cities,datasets:[{{data:vals,backgroundColor:cities.map(c=>(d.city_totals[c]||0)>0?'#4A7FC1':'#CBD5E0'),borderRadius:4,borderSkipped:false}}]}},options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{grid:{{color:'#F0F2F5'}},ticks:{{font:{{size:11}},stepSize:1}}}},y:{{grid:{{display:false}},ticks:{{font:{{size:11}}}}}}}}}}});}}}}
function renderMain(){{const d=DATA[currentPeriod];const g=GROUPS[currentGroup];const fullLabel=g.full[currentPeriod]||currentPeriod;const el=document.getElementById('main-content');if(!d||!d.has_data){{el.innerHTML=`<div class="period-header"><div><div class="period-title">${{fullLabel}}</div><div class="period-subtitle">No data available for this period yet</div></div></div><div class="empty-state"><div class="empty-icon">📋</div><div class="empty-title">No Hiring Data Yet</div><div class="empty-sub">Add hires to the Google Sheet to populate this period automatically.</div></div>`;return;}}const k=d.kpis;const isPartial=['H1','Annual'].includes(currentPeriod);const pb=isPartial?`<span class="partial-badge">⚡ Partial Data</span>`:'';let html=`<div class="period-header"><div><div class="period-title">${{fullLabel}}</div><div class="period-subtitle">Offer acceptance dates · All contracting hubs</div></div>${{pb}}</div><div class="kpi-grid"><div class="kpi-card total"><div class="kpi-label">Total New Hires</div><div class="kpi-value">${{k.total}}</div><div class="kpi-split"><div class="kpi-split-item">WFM <span>${{k.wfm}}</span></div><div class="kpi-split-item">NonWFM <span>${{k.non_wfm}}</span></div></div></div><div class="kpi-card below"><div class="kpi-label">Below Mid-Point</div><div class="kpi-value">${{k.below}}<span class="kpi-pct bad"> ${{k.below_pct}}%</span></div><div class="kpi-sub">of total hires</div></div><div class="kpi-card above"><div class="kpi-label">Above Mid-Point</div><div class="kpi-value">${{k.above}}<span class="kpi-pct good"> ${{k.above_pct}}%</span></div><div class="kpi-sub">of total hires</div></div><div class="kpi-card wfm"><div class="kpi-label">At Mid-Point / No Data</div><div class="kpi-value">${{k.at_mid+k.no_sal}}</div><div class="kpi-split"><div class="kpi-split-item">At Mid <span>${{k.at_mid}}</span></div><div class="kpi-split-item">No Salary <span>${{k.no_sal}}</span></div></div></div></div><div class="content-grid"><div class="card"><div class="card-header"><span class="card-title">Summary — All Contracting Hubs</span></div><div class="card-body">${{buildSummaryTable(d)}}${{d.benchmark_note?`<div class="benchmark-note">⚠️ ${{d.benchmark_note}}</div>`:''}}</div></div><div class="card"><div class="card-header"><span class="card-title">Distribution by Status</span></div><div class="card-body"><div class="chart-container"><canvas id="donut-chart"></canvas></div></div></div></div><div class="card" style="margin-bottom:20px"><div class="card-header"><span class="card-title">Hires by Contracting Hub</span></div><div class="card-body"><div class="chart-container" style="height:200px"><canvas id="bar-chart"></canvas></div></div></div><div class="section-title">Breakdown by Contracting Hub</div><div class="city-grid">`;[['Sarajevo','Banja Luka'],['Belgrade','Novi Sad'],['Nis','Skopje'],['Medellin','Remote']].forEach(p=>{{html+=buildCityCard(p[0],d);html+=buildCityCard(p[1],d);}});html+=`</div>`;html+=buildAboveSection(d);el.innerHTML=html;setTimeout(()=>renderCharts(d),50);}}
renderSubNav();renderMain();
</script>
</body>
</html>'''


def main():
    parser = argparse.ArgumentParser(description="Generate TA Hiring Report from Google Sheets")
    parser.add_argument("--output", default=OUTPUT_FOLDER, help="Output folder path")
    parser.add_argument("--offline", action="store_true", help="Use local Excel file instead of Google Sheets (for testing)")
    parser.add_argument("--excel", default="Hiring Monthly Report Template - 2026.xlsx", help="Local Excel file path (only used with --offline)")
    args = parser.parse_args()

    print("\n📊  TA Hiring Report Generator")
    print("=" * 40)

    if args.offline:
        import pandas as pd
        print(f"   [OFFLINE MODE] Reading from: {args.excel}")
        xl = pd.ExcelFile(args.excel)
        df = pd.read_excel(xl, sheet_name="Report Template", header=0)
        df.columns = ["Position", "Seniority", "City", "Salary", "Midpoint", "Gap_EUR", "Gap_PCT", "Status", "Month", "Type"]
        for col in ["Position", "Seniority", "City", "Status", "Month", "Type"]:
            df[col] = df[col].str.strip()
        import numpy as np
        for col in ["Salary", "Midpoint", "Gap_EUR", "Gap_PCT"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["Position"]).reset_index(drop=True)
        print(f"   Loaded {len(df)} rows")
    else:
        spreadsheet = connect_to_sheets()
        df = load_data(spreadsheet)

    print("   Computing period statistics...")
    DATA = build_period_data(df)

    generated_at = datetime.now().strftime("%d %b %Y, %H:%M")
    html = generate_html(DATA, generated_at)

    output_path = Path(args.output) / OUTPUT_FILENAME
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅  Report generated: {output_path}")
    print(f"   Size: {len(html):,} bytes")
    print(f"   Open in any browser to view\n")


if __name__ == "__main__":
    main()
