#!/usr/bin/env python3
"""
04_descriptive_stats.py — Summary statistics and trend plots for the OECD panel.

Figures:
  fig_01_robot_density_trends.png — Robot density by ABM sector over time
  fig_02_kl_ratios.png            — Capital-labor ratio distributions by sector
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from config import (
    DATA_PROC, FIGURES, RESULTS,
    ABM_SECTORS, SECTOR_COLORS,
    FIG_DPI, FIG_SIZE_PANEL, FIG_SIZE_WIDE,
)

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.titlesize": 11,
    "figure.dpi": FIG_DPI,
})


def load_panel() -> pd.DataFrame:
    path = DATA_PROC / "panel_oecd.csv"
    if not path.exists():
        raise FileNotFoundError(f"Run 02_clean_merge.py first: {path}")
    return pd.read_csv(path)


def summary_table(panel: pd.DataFrame) -> pd.DataFrame:
    """Per-sector summary statistics."""
    rows = []
    for sector in ABM_SECTORS:
        sub = panel[panel["sector_abm"] == sector]
        rows.append({
            "Sector": sector,
            "N_obs": len(sub),
            "Countries": sub["country"].nunique(),
            "Years": f"{sub['year'].min()}-{sub['year'].max()}" if len(sub) else "—",
            "Y_mean": sub["Y"].mean(),
            "L_mean": sub["L"].mean(),
            "w_mean": sub["w"].mean(),
            "Y_L_mean": sub["Y_L"].mean(),
            "K_robot_mean": sub["K_robot"].mean(),
            "K_ict_mean": sub["K_ict"].mean() if "K_ict" in sub else np.nan,
            "K_L_mean": sub["K_L"].mean(),
        })
    df = pd.DataFrame(rows)
    out = RESULTS / "descriptive_summary.csv"
    df.to_csv(out, index=False)
    print(f"Summary table saved: {out}")
    return df


def fig_robot_density_trends(panel: pd.DataFrame):
    """Figure 1: Robot density trends by ABM sector."""
    fig, ax = plt.subplots(figsize=FIG_SIZE_WIDE)

    for sector in ABM_SECTORS:
        sub = panel[panel["sector_abm"] == sector]
        if sub.empty or sub["K_robot"].isna().all():
            continue
        ts = sub.groupby("year")["K_robot"].mean()
        ax.plot(ts.index, ts.values, label=sector,
                color=SECTOR_COLORS[sector], linewidth=2)

    ax.set_xlabel("Year")
    ax.set_ylabel("Robot density (per 10k employees)")
    ax.set_title("Robot Density by ABM Sector (OECD Mean)")
    ax.legend(loc="upper left", frameon=False)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    fig.tight_layout()
    out = FIGURES / "fig_01_robot_density_trends.png"
    fig.savefig(out, dpi=FIG_DPI)
    plt.close(fig)
    print(f"Figure saved: {out}")


def fig_kl_ratios(panel: pd.DataFrame):
    """Figure 2: Capital-labor ratio box plots by sector."""
    fig, axes = plt.subplots(1, 2, figsize=FIG_SIZE_PANEL)

    # Panel A: Y/L (labor productivity)
    data_yl = []
    labels = []
    colors = []
    for sector in ABM_SECTORS:
        sub = panel[panel["sector_abm"] == sector]
        vals = sub["Y_L"].dropna()
        if len(vals) > 0:
            data_yl.append(vals.values)
            labels.append(sector.replace("/", "/\n"))
            colors.append(SECTOR_COLORS[sector])

    if data_yl:
        bp = axes[0].boxplot(data_yl, labels=labels, patch_artist=True,
                             widths=0.6, showfliers=False)
        for patch, color in zip(bp["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
    axes[0].set_ylabel("Value Added per Employee")
    axes[0].set_title("(a) Labor Productivity (Y/L)")
    axes[0].tick_params(axis="x", rotation=30)

    # Panel B: K/L (automation intensity)
    data_kl = []
    labels_kl = []
    colors_kl = []
    for sector in ABM_SECTORS:
        sub = panel[panel["sector_abm"] == sector]
        vals = sub["K_L"].dropna()
        if len(vals) > 0:
            data_kl.append(vals.values)
            labels_kl.append(sector.replace("/", "/\n"))
            colors_kl.append(SECTOR_COLORS[sector])

    if data_kl:
        bp2 = axes[1].boxplot(data_kl, labels=labels_kl, patch_artist=True,
                              widths=0.6, showfliers=False)
        for patch, color in zip(bp2["boxes"], colors_kl):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
    axes[1].set_ylabel("Automation Capital per Employee")
    axes[1].set_title("(b) Automation Intensity (K/L)")
    axes[1].tick_params(axis="x", rotation=30)

    fig.suptitle("Factor Intensity by ABM Sector (OECD Panel)", fontsize=12, y=1.02)
    fig.tight_layout()
    out = FIGURES / "fig_02_kl_ratios.png"
    fig.savefig(out, dpi=FIG_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Figure saved: {out}")


if __name__ == "__main__":
    print("Paper-03: Descriptive statistics...")
    panel = load_panel()
    summary_table(panel)
    fig_robot_density_trends(panel)
    fig_kl_ratios(panel)
    print("Done.")
