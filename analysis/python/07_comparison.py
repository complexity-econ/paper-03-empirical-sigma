#!/usr/bin/env python3
"""
07_comparison.py — Compare GMM vs Bayesian estimates, OECD vs Poland.

Outputs:
  results/comparison_summary.csv    — merged table of all estimates
  figures/fig_05_method_comparison.png — GMM vs Bayesian scatter
  figures/fig_06_oecd_vs_poland.png    — OECD vs Poland comparison
  figures/fig_07_threshold_mapping.png — sigmaThreshold mapping
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from config import (
    RESULTS, FIGURES,
    ABM_SECTORS, MARKET_SECTORS, NON_MARKET_SECTORS,
    SECTOR_COLORS, CALIBRATED_SIGMA, BAYESIAN_PRIORS,
    FIG_DPI, FIG_SIZE_WIDE, FIG_SIZE_PANEL,
)

plt.rcParams.update({"font.family": "serif", "font.size": 10, "figure.dpi": FIG_DPI})


def load_estimates():
    """Load GMM and Bayesian estimation results."""
    dfs = {}

    for label in ["gmm_oecd", "gmm_poland", "bayesian_oecd"]:
        path = RESULTS / f"{label}.csv"
        if path.exists():
            dfs[label] = pd.read_csv(path)
            print(f"  Loaded: {label} ({len(dfs[label])} rows)")
        else:
            print(f"  [WARN] Missing: {path}")
    return dfs


def build_comparison_table(dfs: dict) -> pd.DataFrame:
    """Merge all estimates into a single comparison table."""
    rows = []
    for sector in ABM_SECTORS:
        row = {
            "sector": sector,
            "sigma_calibrated": CALIBRATED_SIGMA[sector],
        }

        # GMM OECD
        if "gmm_oecd" in dfs:
            g = dfs["gmm_oecd"]
            s = g[g["sector"] == sector]
            if not s.empty:
                row["sigma_gmm_oecd"] = s.iloc[0]["sigma"]
                row["se_gmm_oecd"] = s.iloc[0]["se"]
                row["ci_lo_gmm_oecd"] = s.iloc[0]["ci_lo"]
                row["ci_hi_gmm_oecd"] = s.iloc[0]["ci_hi"]

        # GMM Poland
        if "gmm_poland" in dfs:
            g = dfs["gmm_poland"]
            s = g[g["sector"] == sector]
            if not s.empty:
                row["sigma_gmm_poland"] = s.iloc[0]["sigma"]
                row["se_gmm_poland"] = s.iloc[0]["se"]

        # Bayesian OECD
        if "bayesian_oecd" in dfs:
            b = dfs["bayesian_oecd"]
            s = b[b["sector"] == sector]
            if not s.empty:
                row["sigma_bayes_oecd"] = s.iloc[0]["sigma_mean"]
                row["sd_bayes_oecd"] = s.iloc[0]["sigma_sd"]
                row["hdi_lo_bayes_oecd"] = s.iloc[0]["sigma_hdi_lo"]
                row["hdi_hi_bayes_oecd"] = s.iloc[0]["sigma_hdi_hi"]

        # Ratio: empirical / calibrated
        if "sigma_gmm_oecd" in row and not pd.isna(row.get("sigma_gmm_oecd")):
            row["ratio_gmm"] = row["sigma_gmm_oecd"] / row["sigma_calibrated"]
        if "sigma_bayes_oecd" in row and not pd.isna(row.get("sigma_bayes_oecd")):
            row["ratio_bayes"] = row["sigma_bayes_oecd"] / row["sigma_calibrated"]

        # Source and recommended σ for ABM
        if sector in NON_MARKET_SECTORS:
            row["source"] = "prior-only"
            row["sigma_recommended"] = BAYESIAN_PRIORS[sector]["mean"]
        else:
            row["source"] = "data"
            # Prefer Bayesian (shrinkage toward literature), fall back to GMM
            row["sigma_recommended"] = row.get("sigma_bayes_oecd",
                                               row.get("sigma_gmm_oecd", np.nan))

        rows.append(row)

    df = pd.DataFrame(rows)
    out = RESULTS / "comparison_summary.csv"
    df.to_csv(out, index=False)
    print(f"\n=> Comparison table saved: {out}")
    return df


def fig_method_comparison(comp: pd.DataFrame):
    """Figure 5: GMM vs Bayesian sigma estimates (scatter + 45-degree line)."""
    fig, ax = plt.subplots(figsize=FIG_SIZE_WIDE)

    for sector in ABM_SECTORS:
        row = comp[comp["sector"] == sector].iloc[0]
        gmm = row.get("sigma_gmm_oecd")
        bayes = row.get("sigma_bayes_oecd")
        if pd.isna(gmm) or pd.isna(bayes):
            continue
        ax.scatter(gmm, bayes, s=100, color=SECTOR_COLORS[sector],
                   edgecolors="black", zorder=5, label=sector)

    # 45-degree line
    lims = ax.get_xlim()
    ax.plot([0, 100], [0, 100], "k--", alpha=0.3, label="45° line")
    ax.set_xlabel("GMM σ estimate")
    ax.set_ylabel("Bayesian σ estimate")
    ax.set_title("Method Comparison: GMM vs Bayesian")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    ax.set_aspect("equal", adjustable="datalim")

    fig.tight_layout()
    out = FIGURES / "fig_05_method_comparison.png"
    fig.savefig(out, dpi=FIG_DPI)
    plt.close(fig)
    print(f"Figure saved: {out}")


def fig_oecd_vs_poland(comp: pd.DataFrame):
    """Figure 6: OECD vs Poland sigma estimates."""
    fig, ax = plt.subplots(figsize=FIG_SIZE_WIDE)

    for sector in ABM_SECTORS:
        row = comp[comp["sector"] == sector].iloc[0]
        oecd = row.get("sigma_gmm_oecd")
        pol = row.get("sigma_gmm_poland")
        if pd.isna(oecd) or pd.isna(pol):
            continue
        ax.scatter(oecd, pol, s=100, color=SECTOR_COLORS[sector],
                   edgecolors="black", zorder=5, label=sector)

    lims = ax.get_xlim()
    ax.plot([0, 100], [0, 100], "k--", alpha=0.3, label="45° line")
    ax.set_xlabel("OECD pooled σ")
    ax.set_ylabel("Poland-specific σ")
    ax.set_title("OECD vs Poland: Sector-Level σ Estimates")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    ax.set_aspect("equal", adjustable="datalim")

    fig.tight_layout()
    out = FIGURES / "fig_06_oecd_vs_poland.png"
    fig.savefig(out, dpi=FIG_DPI)
    plt.close(fig)
    print(f"Figure saved: {out}")


def fig_threshold_mapping(comp: pd.DataFrame):
    """Figure 7: Calibrated vs recommended sigma (GMM for market, prior for non-market)."""
    fig, ax = plt.subplots(figsize=FIG_SIZE_WIDE)

    sectors = ABM_SECTORS
    x = np.arange(len(sectors))
    width = 0.3

    cal_vals = [CALIBRATED_SIGMA[s] for s in sectors]
    rec_vals = [
        comp[comp["sector"] == s].iloc[0].get("sigma_recommended", np.nan)
        for s in sectors
    ]
    sources = [
        comp[comp["sector"] == s].iloc[0].get("source", "data")
        for s in sectors
    ]

    bars1 = ax.bar(x - width / 2, cal_vals, width, label="Calibrated (Papers 01-02)",
                   color="lightcoral", edgecolor="black", alpha=0.7)

    # Color recommended bars differently for prior-only sectors
    for j, (s, val, src) in enumerate(zip(sectors, rec_vals, sources)):
        color = "lightgray" if src == "prior-only" else "steelblue"
        hatch = "//" if src == "prior-only" else None
        ax.bar(x[j] + width / 2, val, width, color=color,
               edgecolor="black", alpha=0.7, hatch=hatch)

    ax.axhline(y=1.0, color="gray", linestyle="--", alpha=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace("/", "/\n") for s in sectors], fontsize=9)
    ax.set_ylabel("Elasticity of Substitution (σ)")
    ax.set_title("Calibrated vs Recommended σ (Market: Data, Non-Market: Prior)")
    ax.set_yscale("log")

    from matplotlib.patches import Patch
    handles = [
        Patch(facecolor="lightcoral", edgecolor="black", alpha=0.7,
              label="Calibrated (Papers 01-02)"),
        Patch(facecolor="steelblue", edgecolor="black", alpha=0.7,
              label="Empirical (market sectors)"),
        Patch(facecolor="lightgray", edgecolor="black", alpha=0.7,
              hatch="//", label="Literature prior (non-market)"),
        plt.Line2D([0], [0], color="gray", linestyle="--",
                    alpha=0.5, label="Cobb-Douglas (σ=1)"),
    ]
    ax.legend(handles=handles, loc="upper right", frameon=False, fontsize=8)

    fig.tight_layout()
    out = FIGURES / "fig_07_threshold_mapping.png"
    fig.savefig(out, dpi=FIG_DPI)
    plt.close(fig)
    print(f"Figure saved: {out}")


if __name__ == "__main__":
    print("Paper-03: Comparison analysis...")
    dfs = load_estimates()
    comp = build_comparison_table(dfs)
    fig_method_comparison(comp)
    fig_oecd_vs_poland(comp)
    fig_threshold_mapping(comp)
    print("\nDone.")
