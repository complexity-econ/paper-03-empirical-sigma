"""
Paper-03 configuration: paths, sector mapping, plot style, CSV conventions.
"""
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROC = ROOT / "data" / "processed"
RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"
CORE_DIR = ROOT.parent / "core"

for d in [DATA_RAW, DATA_PROC, RESULTS, FIGURES]:
    d.mkdir(parents=True, exist_ok=True)

# ── ISIC Rev.4 → ABM sector crosswalk ─────────────────────────────────
ISIC_TO_ABM = {
    "J": "BPO/SSC",
    "N": "BPO/SSC",
    "C": "Manufacturing",
    "G": "Retail/Services",
    "H": "Retail/Services",
    "I": "Retail/Services",
    "K": "Retail/Services",
    "L": "Retail/Services",
    "M": "Retail/Services",
    "R": "Retail/Services",
    "S": "Retail/Services",
    "Q": "Healthcare",
    "O": "Public",
    "P": "Public",
    "A": "Agriculture",
}

# Ordered list of ABM sectors (matches core engine)
ABM_SECTORS = [
    "BPO/SSC",
    "Manufacturing",
    "Retail/Services",
    "Healthcare",
    "Public",
    "Agriculture",
]

# ── Market vs non-market sector split ─────────────────────────────────
# Non-market sectors (ISIC O, P, Q): value added measured by SNA cost
# convention (Y ≈ wL + δK), making the wage equation ln(w) ~ ln(Y/L)
# a near-tautology.  σ is not identified from data for these sectors.
MARKET_SECTORS = ["BPO/SSC", "Manufacturing", "Retail/Services", "Agriculture"]
NON_MARKET_SECTORS = ["Healthcare", "Public"]

# ── Calibrated σ from Papers 01-02 ────────────────────────────────────
CALIBRATED_SIGMA = {
    "BPO/SSC":         50.0,
    "Manufacturing":   10.0,
    "Retail/Services":  5.0,
    "Healthcare":       2.0,
    "Public":           1.0,
    "Agriculture":      3.0,
}

# ── Bayesian priors (Knoblach et al. 2020 meta-analysis) ──────────────
BAYESIAN_PRIORS = {
    "BPO/SSC":         {"mean": 3.0, "sd": 0.8},
    "Manufacturing":   {"mean": 1.5, "sd": 0.6},
    "Retail/Services": {"mean": 2.0, "sd": 0.7},
    "Healthcare":      {"mean": 1.0, "sd": 0.5},
    "Public":          {"mean": 0.8, "sd": 0.4},
    "Agriculture":     {"mean": 1.5, "sd": 0.6},
}

# ── User cost of capital ──────────────────────────────────────────────
DEPRECIATION_ROBOT = 0.15   # 15% annual depreciation for industrial robots
DEPRECIATION_ICT = 0.25     # 25% annual depreciation for ICT capital
BASE_YEAR = 2015            # Deflator base year

# ── OECD SDMX API ────────────────────────────────────────────────────
OECD_BASE_URL = "https://sdmx.oecd.org/public/rest"
OECD_COUNTRIES = [
    "AUS", "AUT", "BEL", "CAN", "CZE", "DEU", "DNK", "ESP", "EST", "FIN",
    "FRA", "GBR", "GRC", "HUN", "IRL", "ISL", "ISR", "ITA", "JPN", "KOR",
    "LTU", "LUX", "LVA", "MEX", "NLD", "NOR", "NZL", "POL", "PRT", "SVK",
    "SVN", "SWE", "TUR", "USA",
]

# ── GUS BDL API ──────────────────────────────────────────────────────
GUS_BASE_URL = "https://bdl.stat.gov.pl/api/v1"
GUS_LANG = "en"

# ── Plot style ────────────────────────────────────────────────────────
SECTOR_COLORS = {
    "BPO/SSC":         "#e41a1c",
    "Manufacturing":   "#377eb8",
    "Retail/Services": "#4daf4a",
    "Healthcare":      "#984ea3",
    "Public":          "#ff7f00",
    "Agriculture":     "#a65628",
}

FIG_DPI = 200
FIG_SIZE_SINGLE = (8, 5)
FIG_SIZE_PANEL = (14, 10)
FIG_SIZE_WIDE = (12, 5)

# ── ABM sensitivity scenarios ─────────────────────────────────────────
SENSITIVITY_BDP = 2000      # PLN, fixed UBI level for sensitivity
SENSITIVITY_SEEDS = 30
SENSITIVITY_REGIME = "pln"
