#!/usr/bin/env python3
"""
02_clean_merge.py — Build analysis panel from raw OECD + Eurostat + GUS data.

Outputs:
  data/processed/panel_oecd.csv   — OECD panel (country × sector_abm × year)
  data/processed/panel_poland.csv — Poland-specific panel from GUS BDL
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from config import (
    DATA_RAW, DATA_PROC, BASE_YEAR,
    DEPRECIATION_ROBOT, DEPRECIATION_ICT,
)
from config import ISIC_TO_ABM

# Regex to extract 1-letter ISIC section from various code formats
ISIC_SECTION_PATTERN = r"^([A-U])"


def map_isic_to_abm(code: str) -> str | None:
    """Map ISIC section letter to ABM sector name."""
    if not code or not isinstance(code, str):
        return None
    return ISIC_TO_ABM.get(code[0].upper())


# ── OECD STAN loader ─────────────────────────────────────────────────
def load_stan_csv(filename: str) -> pd.DataFrame:
    """Load an OECD STAN CSV (SDMX format) and normalize columns."""
    path = DATA_RAW / "oecd" / filename
    if not path.exists() or path.stat().st_size < 100:
        print(f"  [WARN] Missing or empty: {filename}")
        return pd.DataFrame()
    df = pd.read_csv(path, low_memory=False)
    # SDMX CSV columns vary; normalize to standard names
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if "ref_area" in cl or c == "REF_AREA":
            col_map[c] = "country"
        elif "time_period" in cl or c == "TIME_PERIOD":
            col_map[c] = "year"
        elif "activity" in cl or "industry" in cl:
            col_map[c] = "isic"
        elif "obs_value" in cl or c == "OBS_VALUE":
            col_map[c] = "value"
    df = df.rename(columns=col_map)
    needed = {"country", "year", "isic", "value"}
    if not needed.issubset(df.columns):
        print(f"  [WARN] {filename}: missing columns {needed - set(df.columns)}")
        return pd.DataFrame()
    df = df[list(needed)].copy()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["year", "value"])
    df["year"] = df["year"].astype(int)
    return df


def build_oecd_panel() -> pd.DataFrame:
    """Merge STAN variables into a single panel."""
    print("\n=== Building OECD panel ===")

    # Load individual variables
    va = load_stan_csv("stan_value_added.csv")
    emp = load_stan_csv("stan_employment.csv")
    gfcf = load_stan_csv("stan_gross_fixed_capital.csv")
    labr = load_stan_csv("stan_labor_compensation.csv")

    # Tag variables
    for df, name in [(va, "Y"), (emp, "L"), (gfcf, "GFCF"), (labr, "LABR")]:
        if not df.empty:
            df.rename(columns={"value": name}, inplace=True)

    # Merge on (country, year, isic)
    keys = ["country", "year", "isic"]
    panel = va
    for df in [emp, gfcf, labr]:
        if not df.empty:
            panel = panel.merge(df, on=keys, how="outer")

    if panel.empty:
        print("  [WARN] Empty OECD panel")
        return panel

    # Map ISIC section codes to ABM sectors
    panel["isic_section"] = panel["isic"].str.extract(ISIC_SECTION_PATTERN)
    panel["sector_abm"] = panel["isic_section"].map(map_isic_to_abm)
    panel = panel.dropna(subset=["sector_abm"])

    # Aggregate ISIC divisions to ABM sector level
    panel = (
        panel
        .groupby(["country", "year", "sector_abm"], as_index=False)
        .agg({"Y": "sum", "L": "sum", "GFCF": "sum", "LABR": "sum"})
    )

    # Derived variables
    panel["w"] = np.where(panel["L"] > 0, panel["LABR"] / panel["L"], np.nan)
    panel["Y_L"] = np.where(panel["L"] > 0, panel["Y"] / panel["L"], np.nan)

    print(f"  OECD panel: {len(panel)} rows, "
          f"{panel['country'].nunique()} countries, "
          f"{panel['sector_abm'].nunique()} sectors, "
          f"years {panel['year'].min()}-{panel['year'].max()}")

    return panel


# ── Robot density loader ──────────────────────────────────────────────
def load_robot_density() -> pd.DataFrame:
    """Load IFR robot density from OECD ROBOT_INDUSTRY dataset."""
    print("\n=== Loading robot density ===")
    path = DATA_RAW / "ifr" / "oecd_robot_industry.csv"
    if not path.exists() or path.stat().st_size < 100:
        print("  [WARN] No robot density data")
        return pd.DataFrame()

    df = pd.read_csv(path, low_memory=False)
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if "ref_area" in cl or c == "REF_AREA":
            col_map[c] = "country"
        elif "time_period" in cl or c == "TIME_PERIOD":
            col_map[c] = "year"
        elif "activity" in cl or "industry" in cl:
            col_map[c] = "isic"
        elif "obs_value" in cl or c == "OBS_VALUE":
            col_map[c] = "K_robot"
    df = df.rename(columns=col_map)
    if "K_robot" not in df.columns:
        return pd.DataFrame()
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["K_robot"] = pd.to_numeric(df["K_robot"], errors="coerce")
    df = df.dropna(subset=["year", "K_robot"])
    df["year"] = df["year"].astype(int)

    # Map to ABM sectors
    if "isic" in df.columns:
        df["isic_section"] = df["isic"].str.extract(ISIC_SECTION_PATTERN)
        df["sector_abm"] = df["isic_section"].map(map_isic_to_abm)
        df = df.dropna(subset=["sector_abm"])
        df = (
            df
            .groupby(["country", "year", "sector_abm"], as_index=False)
            ["K_robot"].sum()
        )

    print(f"  Robot density: {len(df)} rows")
    return df


# ── Eurostat ICT CAPEX loader ────────────────────────────────────────
def load_eurostat_ict() -> pd.DataFrame:
    """Load Eurostat ICT capital expenditure."""
    print("\n=== Loading Eurostat ICT CAPEX ===")
    path = DATA_RAW / "eurostat" / "eurostat_ict_capex.csv"
    if not path.exists() or path.stat().st_size < 100:
        print("  [WARN] No Eurostat ICT data")
        return pd.DataFrame()

    df = pd.read_csv(path, low_memory=False)
    # Eurostat CSV format varies; try common column patterns
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if "geo" in cl:
            col_map[c] = "country"
        elif "time" in cl:
            col_map[c] = "year"
        elif "nace" in cl:
            col_map[c] = "nace"
        elif "obs_value" in cl or "values" in cl:
            col_map[c] = "K_ict"
    df = df.rename(columns=col_map)

    if "K_ict" not in df.columns:
        # Try melting year columns (wide format)
        year_cols = [c for c in df.columns if c.isdigit() and len(c) == 4]
        if year_cols:
            id_cols = [c for c in df.columns if c not in year_cols]
            df = df.melt(id_vars=id_cols, value_vars=year_cols,
                         var_name="year", value_name="K_ict")

    if "K_ict" not in df.columns:
        print("  [WARN] Could not parse ICT CAPEX columns")
        return pd.DataFrame()

    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["K_ict"] = pd.to_numeric(df["K_ict"], errors="coerce")
    df = df.dropna(subset=["year", "K_ict"])
    df["year"] = df["year"].astype(int)

    print(f"  Eurostat ICT: {len(df)} rows")
    return df


# ── GUS BDL loader ───────────────────────────────────────────────────
def load_gus_data() -> pd.DataFrame:
    """Load and merge GUS BDL data into Poland panel."""
    print("\n=== Loading GUS BDL (Poland) ===")
    gus_dir = DATA_RAW / "gus"

    def parse_bdl_json(filename: str, var_name: str) -> pd.DataFrame:
        path = gus_dir / filename
        if not path.exists() or path.stat().st_size < 10:
            return pd.DataFrame()
        with open(path) as f:
            data = json.load(f)
        records = []
        for result in data.get("results", []):
            name = result.get("name", "")
            for val in result.get("values", []):
                records.append({
                    "pkd_name": name,
                    "year": val.get("year"),
                    var_name: val.get("val"),
                })
        return pd.DataFrame(records)

    emp = parse_bdl_json("gus_employment.json", "L")
    wages = parse_bdl_json("gus_wages.json", "w")
    assets = parse_bdl_json("gus_fixed_assets.json", "K")
    va = parse_bdl_json("gus_value_added.json", "Y")

    if all(df.empty for df in [emp, wages, assets, va]):
        print("  [WARN] No GUS data available")
        return pd.DataFrame()

    # Merge on (pkd_name, year)
    keys = ["pkd_name", "year"]
    panel = emp
    for df in [wages, assets, va]:
        if not df.empty:
            panel = panel.merge(df, on=keys, how="outer")

    panel["country"] = "POL"
    panel["year"] = pd.to_numeric(panel["year"], errors="coerce").astype("Int64")

    # Map PKD to ABM sectors (PKD uses same letters as ISIC/NACE)
    from config import ISIC_TO_ABM
    panel["sector_abm"] = panel["pkd_name"].str[0].map(ISIC_TO_ABM)
    panel = panel.dropna(subset=["sector_abm", "year"])
    panel["year"] = panel["year"].astype(int)

    panel = (
        panel
        .groupby(["country", "year", "sector_abm"], as_index=False)
        .agg({c: "sum" for c in ["Y", "L", "K", "w"] if c in panel.columns})
    )

    # Derived
    if "w" in panel.columns and "L" in panel.columns:
        panel["w"] = np.where(panel["L"] > 0, panel["w"] / panel["L"], np.nan)
    if "Y" in panel.columns and "L" in panel.columns:
        panel["Y_L"] = np.where(panel["L"] > 0, panel["Y"] / panel["L"], np.nan)

    print(f"  GUS panel: {len(panel)} rows")
    return panel


# ── Merge all sources ─────────────────────────────────────────────────
def merge_panels():
    """Merge OECD STAN + robot density + ICT into final panel."""
    panel = build_oecd_panel()
    if panel.empty:
        print("[ERROR] Cannot build panel — no OECD STAN data")
        return

    # Merge robot density
    robots = load_robot_density()
    if not robots.empty:
        panel = panel.merge(
            robots[["country", "year", "sector_abm", "K_robot"]],
            on=["country", "year", "sector_abm"],
            how="left",
        )
    else:
        panel["K_robot"] = np.nan

    # Merge ICT CAPEX (if mappable)
    ict = load_eurostat_ict()
    if not ict.empty and "sector_abm" in ict.columns:
        panel = panel.merge(
            ict[["country", "year", "sector_abm", "K_ict"]],
            on=["country", "year", "sector_abm"],
            how="left",
        )
    else:
        panel["K_ict"] = np.nan

    # Composite automation capital: K_auto = K_robot + K_ict (where available)
    panel["K_auto"] = panel[["K_robot", "K_ict"]].sum(axis=1, min_count=1)
    panel["K_L"] = np.where(
        panel["L"] > 0, panel["K_auto"] / panel["L"], np.nan
    )

    # Ensure column order
    cols = [
        "country", "year", "sector_abm",
        "Y", "L", "K_robot", "K_ict", "K_auto",
        "w", "GFCF", "LABR",
        "K_L", "Y_L",
    ]
    cols = [c for c in cols if c in panel.columns]
    panel = panel[cols].sort_values(["country", "sector_abm", "year"])

    # Save OECD panel
    out = DATA_PROC / "panel_oecd.csv"
    panel.to_csv(out, index=False)
    print(f"\n=> OECD panel saved: {out} ({len(panel)} rows)")

    # Save Poland-specific panel from GUS
    gus = load_gus_data()
    if not gus.empty:
        out_pl = DATA_PROC / "panel_poland.csv"
        gus.to_csv(out_pl, index=False)
        print(f"=> Poland panel saved: {out_pl} ({len(gus)} rows)")


# ── Entry point ───────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Paper-03: Building analysis panels...")
    merge_panels()
    print("\nDone.")
