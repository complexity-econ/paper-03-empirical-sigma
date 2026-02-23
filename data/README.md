# Data Provenance

## Sources

| Directory | Source | URL | Variables |
|-----------|--------|-----|-----------|
| `raw/ifr/` | IFR (International Federation of Robotics) | OECD ROBOT_INDUSTRY dataset | Robot stock per 10k employees by industry |
| `raw/oecd/` | OECD STAN (ISIC Rev.4) | OECD SDMX API | Value added, employment, GFCF, labor compensation |
| `raw/eurostat/` | Eurostat (isoc_ci_it_en2) | Eurostat bulk download | ICT capital expenditure by NACE sector |
| `raw/gus/` | GUS BDL (Bank Danych Lokalnych) | bdl.stat.gov.pl REST API | Fixed assets, employment, wages by PKD section |

## Panel Construction

Final panel: `processed/panel_oecd.csv`
- ~30 OECD countries x 6 ABM sectors x 2000-2023
- Variables: country, year, sector_abm, Y (real VA), L (employment), K_robot, K_ict, w (real wage), K_L, Y_L
- Deflated with OECD GDP deflator (base year 2015)
- User cost of capital: r_K = i + delta - pi_K (delta=15% robots, 25% ICT)

Poland panel: `processed/panel_poland.csv`
- GUS BDL data mapped to same 6 ABM sectors
- Used for Poland-specific comparison vs OECD pooled estimates

## Sector Mapping (ISIC Rev.4 -> ABM)

| ISIC sections | ABM sector |
|---------------|------------|
| J, N | BPO/SSC |
| C | Manufacturing |
| G, H, I, K, L, M, R, S | Retail/Services |
| Q | Healthcare |
| O, P | Public |
| A | Agriculture |

## Reproducibility

Run `python3 analysis/python/01_download_data.py` to re-download all raw data.
Run `python3 analysis/python/02_clean_merge.py` to rebuild cleaned panels.

Note: IFR robot density data may require institutional access for some granularity levels.
The OECD SDMX API is freely accessible. Eurostat data via `eurostat` Python package.
GUS BDL REST API is freely accessible.
