#!/usr/bin/env python3
"""
01_download_data.py — Download raw data from OECD STAN, Eurostat, and GUS BDL.

Sources:
  1. OECD STAN 2025 (ISIC Rev.4): value added, employment, GFCF, labor compensation,
     ICT capital stock (proxy for automation capital in manufacturing + services)
  2. Eurostat isoc_ci_it_en2: ICT capital expenditure by NACE
  3. GUS BDL: employment, wages by PKD section (Poland-specific)

OECD SDMX v2 API:
  Dataflow: OECD.STI.PIE,DSD_STAN@DF_STAN_2025
  Dimensions: FREQ.REF_AREA.ACTIVITY.MEASURE.PRICE_BASE.UNIT_MEASURE
  Measures: B1G (VA), EMP (employment), D1 (labor comp), P51G (GFCF),
            N11GA_ICT (gross ICT capital stock)
"""
import json
import time
from pathlib import Path

import pandas as pd
import requests

from config import DATA_RAW, OECD_BASE_URL, OECD_COUNTRIES, GUS_BASE_URL, GUS_LANG

HEADERS = {"Accept": "application/vnd.sdmx.data+csv;version=2.0.0"}
OECD_DIR = DATA_RAW / "oecd"
IFR_DIR = DATA_RAW / "ifr"
EURO_DIR = DATA_RAW / "eurostat"
GUS_DIR = DATA_RAW / "gus"

for d in [OECD_DIR, IFR_DIR, EURO_DIR, GUS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# OECD STAN 2025 dataflow
STAN_DATAFLOW = "OECD.STI.PIE,DSD_STAN@DF_STAN_2025"

# ISIC section-level activity codes available in STAN
STAN_ACTIVITIES = "A+C+G+H+I+J+K+L+M+N+O+P+Q+R+S"


# ── Helpers ───────────────────────────────────────────────────────────
def fetch_oecd_stan(measure: str, out_path: Path,
                    price_base: str = "V", unit: str = "XDC") -> None:
    """Download STAN data for a specific measure.

    Dimensions: FREQ.REF_AREA.ACTIVITY.MEASURE.PRICE_BASE.UNIT_MEASURE
    """
    if out_path.exists() and out_path.stat().st_size > 100:
        print(f"  [skip] {out_path.name} already exists")
        return

    countries = "+".join(OECD_COUNTRIES)
    filter_expr = f"A.{countries}.{STAN_ACTIVITIES}.{measure}.{price_base}.{unit}"
    url = f"{OECD_BASE_URL}/data/{STAN_DATAFLOW}/{filter_expr}"
    print(f"  [GET]  {url[:140]}...")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=180)
        if resp.status_code == 200:
            out_path.write_text(resp.text)
            n_lines = resp.text.count("\n")
            print(f"  [OK]   {out_path.name} ({len(resp.text)//1024} KB, ~{n_lines} rows)")
        else:
            body = resp.text[:200]
            print(f"  [WARN] HTTP {resp.status_code} for {measure}: {body}")
            out_path.write_text("")
    except requests.exceptions.Timeout:
        print(f"  [WARN] Timeout for {measure}")
        out_path.write_text("")
    time.sleep(2)  # rate limit courtesy


def fetch_eurostat(table_code: str, out_path: Path) -> None:
    """Download Eurostat table via eurostat package or SDMX bulk URL."""
    if out_path.exists() and out_path.stat().st_size > 100:
        print(f"  [skip] {out_path.name} already exists")
        return
    try:
        import eurostat
        df = eurostat.get_data_df(table_code)
        df.to_csv(out_path, index=False)
        print(f"  [OK]   {out_path.name} ({len(df)} rows)")
    except ImportError:
        print("  [WARN] `eurostat` package not installed — downloading via bulk URL")
        url = (
            f"https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/"
            f"{table_code}/?format=SDMX-CSV&compressed=false"
        )
        resp = requests.get(url, timeout=180)
        if resp.status_code == 200:
            out_path.write_text(resp.text)
            print(f"  [OK]   {out_path.name} ({len(resp.text)//1024} KB)")
        else:
            print(f"  [WARN] HTTP {resp.status_code}, saving empty")
            out_path.write_text("")
    time.sleep(1)


def fetch_gus_bdl_variables(subject_id: str, out_path: Path) -> None:
    """Download all variables for a GUS BDL subject via REST API.

    BDL API does not require authentication when no X-ClientId header is sent.
    """
    if out_path.exists() and out_path.stat().st_size > 100:
        print(f"  [skip] {out_path.name} already exists")
        return

    url = (
        f"{GUS_BASE_URL}/data/by-variable/{subject_id}"
        f"?format=json&lang={GUS_LANG}&page-size=5000"
    )
    print(f"  [GET]  {url[:120]}...")
    try:
        resp = requests.get(url, timeout=120)
        if resp.status_code == 200:
            data = resp.json()
            out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            n = len(data.get("results", []))
            print(f"  [OK]   {out_path.name} ({n} records)")
        else:
            print(f"  [WARN] HTTP {resp.status_code}: {resp.text[:200]}")
            out_path.write_text("{}")
    except Exception as e:
        print(f"  [WARN] GUS request failed: {e}")
        out_path.write_text("{}")
    time.sleep(1)


def fetch_gus_bdl_by_variable(var_id: str, out_path: Path) -> None:
    """Download GUS BDL data for a variable (paginated, level 0 = Poland national).

    BDL API max page-size is 100. We paginate through all pages.
    """
    if out_path.exists() and out_path.stat().st_size > 100:
        print(f"  [skip] {out_path.name} already exists")
        return

    all_results = []
    page = 0
    while True:
        url = (
            f"{GUS_BASE_URL}/data/by-variable/{var_id}"
            f"?unit-level=0&format=json&lang={GUS_LANG}"
            f"&page-size=100&page={page}"
        )
        if page == 0:
            print(f"  [GET]  {url[:120]}...")
        try:
            resp = requests.get(url, timeout=120)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                all_results.extend(results)
                total = data.get("totalRecords", 0)
                if len(all_results) >= total or not results:
                    break
                page += 1
            else:
                print(f"  [WARN] HTTP {resp.status_code}: {resp.text[:200]}")
                break
        except Exception as e:
            print(f"  [WARN] GUS request failed: {e}")
            break
        time.sleep(0.5)

    if all_results:
        out_data = {"totalRecords": len(all_results), "results": all_results}
        out_path.write_text(json.dumps(out_data, ensure_ascii=False, indent=2))
        print(f"  [OK]   {out_path.name} ({len(all_results)} records, {page+1} pages)")
    else:
        out_path.write_text("{}")
        print(f"  [WARN] No results for var {var_id}")


# ── Main downloads ────────────────────────────────────────────────────
def download_oecd_stan():
    """OECD STAN 2025: value added, employment, labor comp, GFCF, ICT capital."""
    print("\n=== OECD STAN 2025 (ISIC Rev.4) ===")

    # B1G = Value added (current prices, national currency)
    fetch_oecd_stan("B1G", OECD_DIR / "stan_value_added.csv",
                    price_base="V", unit="XDC")

    # EMP = Total employment (thousands of persons, PRICE_BASE=_Z for non-monetary)
    fetch_oecd_stan("EMP", OECD_DIR / "stan_employment.csv",
                    price_base="_Z", unit="PS")

    # D1 = Compensation of employees (current prices)
    fetch_oecd_stan("D1", OECD_DIR / "stan_labor_compensation.csv",
                    price_base="V", unit="XDC")

    # P51G = Gross fixed capital formation (current prices)
    fetch_oecd_stan("P51G", OECD_DIR / "stan_gross_fixed_capital.csv",
                    price_base="V", unit="XDC")

    # N11GA_ICT = Gross capital stock, ICT equipment (proxy for automation capital)
    fetch_oecd_stan("N11GA_ICT", OECD_DIR / "stan_ict_capital_stock.csv",
                    price_base="V", unit="XDC")

    # P51G_ICT = GFCF in ICT (investment flow)
    fetch_oecd_stan("P51G_ICT", OECD_DIR / "stan_ict_gfcf.csv",
                    price_base="V", unit="XDC")


def download_eurostat_ict():
    """Eurostat ICT capital expenditure by NACE sector."""
    print("\n=== Eurostat ICT CAPEX ===")
    fetch_eurostat("isoc_ci_it_en2", EURO_DIR / "eurostat_ict_capex.csv")


def download_gus_bdl():
    """GUS BDL: employment and wages by PKD section (Poland-specific).

    BDL variable IDs found via: https://bdl.stat.gov.pl/api/v1/
    These are national-level (level=0) variables by PKD section.
    """
    print("\n=== GUS BDL (Poland) ===")

    # Search for relevant subjects first
    print("  Searching BDL subjects...")
    url = f"{GUS_BASE_URL}/subjects?lang={GUS_LANG}&format=json&page-size=100"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            for subj in data.get("results", []):
                name = subj.get("name", "").lower()
                if any(k in name for k in ["employment", "wages", "industry",
                                           "labour", "labor", "enterprise"]):
                    print(f"    {subj['id']}: {subj['name']}")
    except Exception as e:
        print(f"    [WARN] Subject search failed: {e}")

    # Known variable IDs for employment and wages (national PKD-level)
    # These may need adjustment based on BDL catalog exploration
    gus_variables = [
        # (description, var_id, filename)
        ("average_employment", "72305", "gus_employment.json"),
        ("average_wages", "64428", "gus_wages.json"),
    ]

    for desc, var_id, fname in gus_variables:
        print(f"\n  → {desc} (var_id={var_id})")
        fetch_gus_bdl_by_variable(var_id, GUS_DIR / fname)


# ── Entry point ───────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Paper-03: Downloading raw data...")
    download_oecd_stan()
    download_eurostat_ict()
    download_gus_bdl()
    print("\n✓ All downloads complete. Raw data in:", DATA_RAW)
