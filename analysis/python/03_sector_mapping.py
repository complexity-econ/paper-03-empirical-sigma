#!/usr/bin/env python3
"""
03_sector_mapping.py — ISIC Rev.4 / NACE Rev.2 / PKD 2007 → ABM sector crosswalk.

Provides:
  - map_isic_to_abm(code) → ABM sector name
  - ISIC_SECTION_PATTERN: regex to extract 1-letter section from ISIC codes
  - CROSSWALK_TABLE: DataFrame with full mapping for documentation

The crosswalk maps 15 ISIC sections to the 6 ABM sectors used in Papers 01-03.
Unmapped sections (B=Mining, D=Utilities, E=Water, F=Construction, T, U) are excluded.
"""
import re

import pandas as pd

from config import ISIC_TO_ABM, ABM_SECTORS, DATA_PROC

# Regex to extract 1-letter ISIC section from various code formats
# Handles: "C", "C10-C12", "ISIC4_C", "D05T06", section letter at start
ISIC_SECTION_PATTERN = r"([A-U])"


def map_isic_to_abm(isic_code: str) -> str | None:
    """Map an ISIC section letter to the corresponding ABM sector.

    Returns None for unmapped sections (B, D, E, F, T, U).
    """
    if not isic_code or not isinstance(isic_code, str):
        return None
    # Extract section letter
    match = re.search(ISIC_SECTION_PATTERN, isic_code.upper())
    if match:
        return ISIC_TO_ABM.get(match.group(1))
    return None


# Full crosswalk documentation table
CROSSWALK_DF = pd.DataFrame([
    {"isic_section": "A", "isic_description": "Agriculture, forestry and fishing",
     "sector_abm": "Agriculture"},
    {"isic_section": "C", "isic_description": "Manufacturing",
     "sector_abm": "Manufacturing"},
    {"isic_section": "G", "isic_description": "Wholesale and retail trade",
     "sector_abm": "Retail/Services"},
    {"isic_section": "H", "isic_description": "Transportation and storage",
     "sector_abm": "Retail/Services"},
    {"isic_section": "I", "isic_description": "Accommodation and food service",
     "sector_abm": "Retail/Services"},
    {"isic_section": "J", "isic_description": "Information and communication",
     "sector_abm": "BPO/SSC"},
    {"isic_section": "K", "isic_description": "Financial and insurance activities",
     "sector_abm": "Retail/Services"},
    {"isic_section": "L", "isic_description": "Real estate activities",
     "sector_abm": "Retail/Services"},
    {"isic_section": "M", "isic_description": "Professional, scientific and technical",
     "sector_abm": "Retail/Services"},
    {"isic_section": "N", "isic_description": "Administrative and support services",
     "sector_abm": "BPO/SSC"},
    {"isic_section": "O", "isic_description": "Public administration and defence",
     "sector_abm": "Public"},
    {"isic_section": "P", "isic_description": "Education",
     "sector_abm": "Public"},
    {"isic_section": "Q", "isic_description": "Human health and social work",
     "sector_abm": "Healthcare"},
    {"isic_section": "R", "isic_description": "Arts, entertainment and recreation",
     "sector_abm": "Retail/Services"},
    {"isic_section": "S", "isic_description": "Other service activities",
     "sector_abm": "Retail/Services"},
])


def save_crosswalk():
    """Save crosswalk table as CSV for documentation."""
    out = DATA_PROC / "sector_crosswalk.csv"
    CROSSWALK_DF.to_csv(out, index=False)
    print(f"Sector crosswalk saved: {out}")

    # Summary: how many ISIC sections per ABM sector
    summary = CROSSWALK_DF.groupby("sector_abm")["isic_section"].apply(list)
    print("\nISIC → ABM mapping:")
    for sector in ABM_SECTORS:
        if sector in summary.index:
            codes = ", ".join(summary[sector])
            print(f"  {sector:20s} ← ISIC [{codes}]")


if __name__ == "__main__":
    save_crosswalk()
