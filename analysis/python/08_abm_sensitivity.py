#!/usr/bin/env python3
"""
08_abm_sensitivity.py — Re-run ABM with empirical sigma and analyze results.

Scenarios (4 × 30 seeds at BDP=2000 PLN):
  1. Calibrated σ (baseline from Papers 01-02)
  2. Empirical σ (GMM point estimates)
  3. Empirical low (GMM CI lower bound)
  4. Empirical high (GMM CI upper bound)

Key question: Does bimodality at BDP=2000 survive with empirical σ?

Outputs:
  results/sensitivity_summary.csv    — scenario comparison
  figures/fig_08_abm_sensitivity.png — bimodality comparison
"""
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from config import (
    DATA_PROC, RESULTS, FIGURES, CORE_DIR,
    ABM_SECTORS, SECTOR_COLORS, CALIBRATED_SIGMA,
    SENSITIVITY_BDP, SENSITIVITY_SEEDS, SENSITIVITY_REGIME,
    FIG_DPI, FIG_SIZE_PANEL,
)

plt.rcParams.update({"font.family": "serif", "font.size": 10, "figure.dpi": FIG_DPI})

SCENARIOS = ["calibrated", "empirical", "empirical_low", "empirical_high"]


def load_gmm_estimates() -> dict:
    """Load estimates and build sigma vectors for each scenario.

    Market sectors (BPO, Mfg, Retail, Agri): use GMM point estimates + CI.
    Non-market sectors (Healthcare, Public): use literature priors from
    Knoblach et al. (2020) — σ not identified due to SNA cost convention.
    """
    path = RESULTS / "gmm_oecd.csv"
    if not path.exists():
        raise FileNotFoundError(f"Run 05_gmm_estimation.py first: {path}")

    gmm = pd.read_csv(path)
    sector_order = ABM_SECTORS  # must match core engine SECTORS order

    from config import BAYESIAN_PRIORS, NON_MARKET_SECTORS

    def _get(s, col, fallback):
        row = gmm[gmm["sector"] == s]
        if row.empty or pd.isna(row.iloc[0].get(col)):
            return fallback
        return max(0.1, row.iloc[0][col])

    sigma_vecs = {}

    # Scenario 1: calibrated (baseline)
    sigma_vecs["calibrated"] = [CALIBRATED_SIGMA[s] for s in sector_order]

    # Scenario 2: empirical (point estimates — GMM for market, prior for non-market)
    sigma_vecs["empirical"] = [
        BAYESIAN_PRIORS[s]["mean"] if s in NON_MARKET_SECTORS
        else _get(s, "sigma", CALIBRATED_SIGMA[s])
        for s in sector_order
    ]

    # Scenario 3: empirical low (CI lower bound / prior - 1.96*SD)
    sigma_vecs["empirical_low"] = [
        max(0.1, BAYESIAN_PRIORS[s]["mean"] - 1.96 * BAYESIAN_PRIORS[s]["sd"])
        if s in NON_MARKET_SECTORS
        else _get(s, "ci_lo", CALIBRATED_SIGMA[s])
        for s in sector_order
    ]

    # Scenario 4: empirical high (CI upper bound / prior + 1.96*SD)
    sigma_vecs["empirical_high"] = [
        BAYESIAN_PRIORS[s]["mean"] + 1.96 * BAYESIAN_PRIORS[s]["sd"]
        if s in NON_MARKET_SECTORS
        else _get(s, "ci_hi", CALIBRATED_SIGMA[s])
        for s in sector_order
    ]

    return sigma_vecs


def format_sigmas_env(sigma_vec: list) -> str:
    """Format sigma vector as comma-separated string for SIGMAS env var."""
    return ",".join(f"{s:.4f}" for s in sigma_vec)


def run_abm_scenario(scenario: str, sigma_vec: list) -> bool:
    """Run the ABM core engine with given sigma values."""
    env_sigmas = format_sigmas_env(sigma_vec)
    prefix = f"sens_{scenario}_{SENSITIVITY_BDP}"
    cmd = f'sbt "run {SENSITIVITY_BDP} {SENSITIVITY_SEEDS} {prefix} {SENSITIVITY_REGIME}"'

    print(f"\n  [{scenario}] SIGMAS={env_sigmas}")
    print(f"  [{scenario}] {cmd}")

    import os
    env = os.environ.copy()
    env["SIGMAS"] = env_sigmas

    try:
        result = subprocess.run(
            cmd, shell=True, cwd=str(CORE_DIR),
            capture_output=True, text=True, timeout=600, env=env,
        )
        if result.returncode == 0:
            print(f"  [{scenario}] OK")
            return True
        else:
            print(f"  [{scenario}] FAILED: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  [{scenario}] TIMEOUT")
        return False
    except FileNotFoundError:
        print(f"  [{scenario}] sbt not found — skipping simulation")
        return False


def load_scenario_results(scenario: str) -> pd.DataFrame | None:
    """Load terminal CSV from a sensitivity scenario.

    Core engine outputs semicolon-separated CSV with comma decimal (Polish locale).
    """
    prefix = f"sens_{scenario}_{SENSITIVITY_BDP}"
    for search_dir in [CORE_DIR / "mc", RESULTS]:
        candidates = list(search_dir.glob(f"{prefix}_terminal.csv"))
        if not candidates:
            candidates = list(search_dir.glob(f"{prefix}*.csv"))
        if candidates:
            # Terminal CSVs only (skip timeseries)
            for c in candidates:
                if "terminal" in c.name:
                    path = c
                    break
            else:
                path = candidates[0]
            df = pd.read_csv(path, sep=";", decimal=",")
            return df
    return None


def analyze_bimodality(data: pd.Series) -> dict:
    """Test for bimodality using Hartigan's dip test."""
    result = {"n": len(data), "mean": data.mean(), "std": data.std()}

    try:
        from diptest import diptest
        dip_stat, dip_pval = diptest(data.values)
        result["dip_stat"] = dip_stat
        result["dip_pval"] = dip_pval
        result["bimodal"] = dip_pval < 0.05
    except ImportError:
        # Fallback: check if distribution is spread enough to suggest bimodality
        result["dip_stat"] = np.nan
        result["dip_pval"] = np.nan
        # Use coefficient of variation as rough proxy
        cv = data.std() / data.mean() if data.mean() != 0 else 0
        result["cv"] = cv
        result["bimodal"] = cv > 0.3  # heuristic

    return result


def analyze_all_scenarios(sigma_vecs: dict) -> pd.DataFrame:
    """Analyze terminal results from all scenarios."""
    rows = []
    for scenario in SCENARIOS:
        df = load_scenario_results(scenario)
        if df is None:
            print(f"  [{scenario}] No results found")
            rows.append({"scenario": scenario, "available": False})
            continue

        # Key metrics from terminal CSV (column names from core engine)
        # Typical columns: Adoption, Unemployment, Inflation, ...
        metrics = {}
        metrics["scenario"] = scenario
        metrics["available"] = True
        metrics["sigma_vector"] = format_sigmas_env(sigma_vecs[scenario])

        for col in ["TotalAdoption", "Unemployment", "Inflation", "MarketWage", "GovDebt"]:
            if col in df.columns:
                vals = df[col].dropna()
                metrics[f"{col}_mean"] = vals.mean()
                metrics[f"{col}_std"] = vals.std()

                # Bimodality test for adoption
                if col == "TotalAdoption" and len(vals) >= 10:
                    bim = analyze_bimodality(vals)
                    metrics["adoption_dip_stat"] = bim.get("dip_stat")
                    metrics["adoption_dip_pval"] = bim.get("dip_pval")
                    metrics["adoption_bimodal"] = bim.get("bimodal")

        rows.append(metrics)

    df = pd.DataFrame(rows)
    out = RESULTS / "sensitivity_summary.csv"
    df.to_csv(out, index=False)
    print(f"\n=> Sensitivity summary saved: {out}")
    return df


def fig_sensitivity(sigma_vecs: dict):
    """Figure 8: ABM sensitivity — adoption distributions by scenario."""
    fig, axes = plt.subplots(2, 2, figsize=FIG_SIZE_PANEL)
    axes = axes.flatten()
    colors = ["lightcoral", "steelblue", "lightgreen", "mediumpurple"]

    for i, scenario in enumerate(SCENARIOS):
        ax = axes[i]
        df = load_scenario_results(scenario)

        if df is None or "TotalAdoption" not in df.columns:
            ax.text(0.5, 0.5, f"No data\n({scenario})",
                    ha="center", va="center", transform=ax.transAxes)
            ax.set_title(scenario.replace("_", " ").title())
            continue

        vals = df["TotalAdoption"].dropna()
        ax.hist(vals, bins=20, density=True, alpha=0.7,
                color=colors[i], edgecolor="black")
        ax.axvline(vals.mean(), color="red", linestyle="--", linewidth=1.5)

        # Sigma values annotation
        sigmas = sigma_vecs[scenario]
        sigma_str = ", ".join(f"{s:.1f}" for s in sigmas)
        ax.text(0.02, 0.98, f"σ = [{sigma_str}]",
                transform=ax.transAxes, fontsize=7, va="top",
                bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))

        title = scenario.replace("_", " ").title()
        ax.set_title(f"({chr(97+i)}) {title}")
        ax.set_xlabel("Total Adoption Rate")
        ax.set_ylabel("Density")

    fig.suptitle(f"ABM Sensitivity: Adoption at BDP={SENSITIVITY_BDP} PLN",
                 fontsize=12, y=1.02)
    fig.tight_layout()
    out = FIGURES / "fig_08_abm_sensitivity.png"
    fig.savefig(out, dpi=FIG_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Figure saved: {out}")


if __name__ == "__main__":
    print("Paper-03: ABM sensitivity analysis...")

    sigma_vecs = load_gmm_estimates()

    # Print sigma vectors
    print("\nScenario sigma vectors:")
    for scenario, vec in sigma_vecs.items():
        print(f"  {scenario:20s} → [{', '.join(f'{s:.2f}' for s in vec)}]")

    # Run simulations (if core engine available)
    print("\n--- Running ABM simulations ---")
    for scenario in SCENARIOS:
        run_abm_scenario(scenario, sigma_vecs[scenario])

    # Analyze results
    print("\n--- Analyzing results ---")
    summary = analyze_all_scenarios(sigma_vecs)

    # Figure
    fig_sensitivity(sigma_vecs)
    print("\nDone.")
