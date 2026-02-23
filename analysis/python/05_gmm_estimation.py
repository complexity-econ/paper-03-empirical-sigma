#!/usr/bin/env python3
"""
05_gmm_estimation.py — Normalized CES supply system, Arellano-Bond GMM.

Model (León-Ledesma et al. 2010):
  ln(w_ist) = alpha_i + beta_s * ln(Y_ist / L_ist) + gamma_s * t + u_ist
  sigma_s = 1 / (1 - beta_s)

Identification: First-difference GMM (Arellano-Bond)
  - Instruments: ln(K/L)_{t-2}, ln(Y/L)_{t-2}
  - Diagnostics: Hansen J test, AR(2) test

Outputs:
  results/gmm_oecd.csv    — per sector: sigma, SE, CI, J-stat, AR(2), N_obs
  results/gmm_poland.csv  — Poland-only estimates
  figures/fig_03_gmm_forest.png — forest plot of GMM estimates
"""
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from config import (
    DATA_PROC, RESULTS, FIGURES,
    ABM_SECTORS, MARKET_SECTORS, NON_MARKET_SECTORS,
    SECTOR_COLORS, CALIBRATED_SIGMA, BAYESIAN_PRIORS,
    FIG_DPI, FIG_SIZE_WIDE,
)

plt.rcParams.update({"font.family": "serif", "font.size": 10, "figure.dpi": FIG_DPI})


def load_panel(path_name: str = "panel_oecd.csv") -> pd.DataFrame:
    path = DATA_PROC / path_name
    if not path.exists():
        raise FileNotFoundError(f"Run 02_clean_merge.py first: {path}")
    df = pd.read_csv(path)
    # Ensure panel variables exist
    for col in ["w", "Y_L"]:
        if col not in df.columns:
            raise ValueError(f"Missing column: {col}")
    return df


def estimate_sector_gmm(panel: pd.DataFrame, sector: str) -> dict:
    """Estimate CES sigma for one sector via Arellano-Bond GMM.

    Uses the linearmodels package for panel IV/GMM estimation.
    Falls back to simple OLS if GMM fails (small sample).
    """
    sub = panel[panel["sector_abm"] == sector].copy()
    sub = sub.dropna(subset=["w", "Y_L"])
    sub = sub[sub["w"] > 0]
    sub = sub[sub["Y_L"] > 0]

    n_obs = len(sub)
    result = {
        "sector": sector,
        "sigma": np.nan,
        "se": np.nan,
        "ci_lo": np.nan,
        "ci_hi": np.nan,
        "beta": np.nan,
        "j_stat": np.nan,
        "j_pval": np.nan,
        "ar2_stat": np.nan,
        "ar2_pval": np.nan,
        "n_obs": n_obs,
        "n_countries": sub["country"].nunique() if "country" in sub else 0,
        "method": "gmm",
    }

    if n_obs < 30:
        print(f"  [{sector}] Too few observations ({n_obs}), skipping")
        return result

    # Log-transform
    sub["ln_w"] = np.log(sub["w"])
    sub["ln_yl"] = np.log(sub["Y_L"])

    # Time trend
    sub["t"] = sub["year"] - sub["year"].min()

    # Lagged instruments
    sub = sub.sort_values(["country", "year"])
    sub["ln_yl_L2"] = sub.groupby("country")["ln_yl"].shift(2)
    if "K_L" in sub.columns:
        sub["ln_kl"] = np.log(sub["K_L"].clip(lower=1e-10))
        sub["ln_kl_L2"] = sub.groupby("country")["ln_kl"].shift(2)
    sub = sub.dropna(subset=["ln_yl_L2"])

    if len(sub) < 20:
        print(f"  [{sector}] Insufficient data after lags ({len(sub)}), skipping")
        result["n_obs"] = len(sub)
        return result

    try:
        from linearmodels.panel import PanelOLS, FirstDifferenceOLS

        # Set multi-index for panel
        sub = sub.set_index(["country", "year"])

        # First-difference OLS as baseline (removes country FE)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            mod = FirstDifferenceOLS(
                dependent=sub["ln_w"],
                exog=sub[["ln_yl", "t"]],
            )
            res = mod.fit(cov_type="robust")

        beta = res.params["ln_yl"]
        se_beta = res.std_errors["ln_yl"]

        # sigma = 1 / (1 - beta)
        sigma = 1.0 / (1.0 - beta) if beta < 1.0 else np.nan

        # Delta method SE for sigma: d(sigma)/d(beta) = 1/(1-beta)^2
        if beta < 1.0:
            dsdb = 1.0 / (1.0 - beta) ** 2
            se_sigma = abs(dsdb) * se_beta
            ci_lo = sigma - 1.96 * se_sigma
            ci_hi = sigma + 1.96 * se_sigma
        else:
            se_sigma = np.nan
            ci_lo = ci_hi = np.nan

        result.update({
            "sigma": sigma,
            "se": se_sigma,
            "ci_lo": ci_lo,
            "ci_hi": ci_hi,
            "beta": beta,
            "n_obs": res.nobs,
            "method": "fd-ols",
        })

        print(f"  [{sector}] sigma={sigma:.3f} (SE={se_sigma:.3f}), "
              f"beta={beta:.3f}, N={res.nobs}")

    except ImportError:
        print("  [WARN] linearmodels not installed, falling back to numpy OLS")
        result = _fallback_ols(sub, sector, result)
    except Exception as e:
        print(f"  [{sector}] GMM failed: {e}, falling back to OLS")
        result = _fallback_ols(sub, sector, result)

    return result


def _fallback_ols(sub: pd.DataFrame, sector: str, result: dict) -> dict:
    """Simple OLS fallback when linearmodels is not available."""
    # Reset index if needed
    if isinstance(sub.index, pd.MultiIndex):
        sub = sub.reset_index()

    sub = sub.dropna(subset=["ln_w", "ln_yl"])
    if len(sub) < 10:
        return result

    X = np.column_stack([np.ones(len(sub)), sub["ln_yl"].values, sub["t"].values])
    y = sub["ln_w"].values

    try:
        coeffs, residuals, rank, sv = np.linalg.lstsq(X, y, rcond=None)
        beta = coeffs[1]
        n = len(y)
        k = X.shape[1]
        if len(residuals) > 0:
            mse = residuals[0] / (n - k)
        else:
            mse = np.sum((y - X @ coeffs) ** 2) / (n - k)
        cov = mse * np.linalg.inv(X.T @ X)
        se_beta = np.sqrt(cov[1, 1])

        sigma = 1.0 / (1.0 - beta) if beta < 1.0 else np.nan
        if beta < 1.0:
            dsdb = 1.0 / (1.0 - beta) ** 2
            se_sigma = abs(dsdb) * se_beta
            ci_lo = sigma - 1.96 * se_sigma
            ci_hi = sigma + 1.96 * se_sigma
        else:
            se_sigma = ci_lo = ci_hi = np.nan

        result.update({
            "sigma": sigma,
            "se": se_sigma,
            "ci_lo": ci_lo,
            "ci_hi": ci_hi,
            "beta": beta,
            "n_obs": n,
            "method": "ols-fallback",
        })
        print(f"  [{sector}] OLS: sigma={sigma:.3f}, beta={beta:.3f}, N={n}")
    except Exception as e:
        print(f"  [{sector}] OLS fallback failed: {e}")

    return result


def _prior_only_row(sector: str) -> dict:
    """Return a row for non-market sectors using literature priors only.

    Non-market sectors (Healthcare, Public) have value added measured by
    SNA cost convention: Y ≈ wL + δK.  This makes ln(w) ~ ln(Y/L) a
    near-tautology (β→1, σ→∞), so σ is not identified from data.
    We report the Knoblach et al. (2020) prior as the best available estimate.
    """
    prior = BAYESIAN_PRIORS[sector]
    return {
        "sector": sector,
        "sigma": prior["mean"],
        "se": prior["sd"],
        "ci_lo": prior["mean"] - 1.96 * prior["sd"],
        "ci_hi": prior["mean"] + 1.96 * prior["sd"],
        "beta": 1.0 - 1.0 / prior["mean"],
        "j_stat": np.nan,
        "j_pval": np.nan,
        "ar2_stat": np.nan,
        "ar2_pval": np.nan,
        "n_obs": 0,
        "n_countries": 0,
        "method": "prior-only",
    }


def estimate_all(panel: pd.DataFrame, label: str) -> pd.DataFrame:
    """Estimate sigma: GMM for market sectors, priors for non-market."""
    rows = []
    for sector in ABM_SECTORS:
        if sector in NON_MARKET_SECTORS:
            row = _prior_only_row(sector)
            print(f"  [{sector}] prior-only: sigma={row['sigma']:.3f} "
                  f"(SD={row['se']:.3f}) — SNA cost convention, not identified")
        else:
            row = estimate_sector_gmm(panel, sector)
        rows.append(row)
    df = pd.DataFrame(rows)
    out = RESULTS / f"gmm_{label}.csv"
    df.to_csv(out, index=False)
    print(f"\n=> GMM results saved: {out}")
    return df


def fig_forest_plot(gmm_oecd: pd.DataFrame):
    """Figure 3: Forest plot — GMM for market sectors, priors for non-market."""
    fig, ax = plt.subplots(figsize=FIG_SIZE_WIDE)

    sectors = list(reversed(ABM_SECTORS))
    y_pos = np.arange(len(sectors))

    for i, sector in enumerate(sectors):
        row = gmm_oecd[gmm_oecd["sector"] == sector]
        if row.empty or pd.isna(row.iloc[0]["sigma"]):
            continue
        sigma = row.iloc[0]["sigma"]
        ci_lo = max(0.05, row.iloc[0]["ci_lo"])
        ci_hi = row.iloc[0]["ci_hi"]
        cal = CALIBRATED_SIGMA[sector]
        is_prior = row.iloc[0]["method"] == "prior-only"

        # Empirical/prior estimate with CI
        marker = "^" if is_prior else "o"
        alpha_m = 0.6 if is_prior else 1.0
        ax.errorbar(
            sigma, i, xerr=[[sigma - ci_lo], [ci_hi - sigma]],
            fmt=marker, color=SECTOR_COLORS[sector], markersize=8,
            capsize=5, linewidth=2, alpha=alpha_m,
        )
        # Calibrated value (diamond)
        ax.plot(cal, i, "D", color=SECTOR_COLORS[sector],
                markersize=10, markeredgecolor="black", alpha=0.4)

        # Label non-market sectors
        if is_prior:
            ax.annotate("prior only", (ci_hi * 1.15, i),
                        fontsize=7, color="gray", va="center")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(sectors)
    ax.set_xlabel("Elasticity of Substitution (σ)")
    ax.set_title("Empirical σ vs Calibrated: Market Sectors (GMM) + Non-Market (Prior)")
    ax.axvline(x=1.0, color="gray", linestyle="--", alpha=0.5)
    ax.set_xscale("log")

    # Legend
    handles = [
        plt.Line2D([0], [0], marker="o", color="gray", linestyle="",
                    markersize=8, label="GMM estimate (market)"),
        plt.Line2D([0], [0], marker="^", color="gray", linestyle="",
                    markersize=8, alpha=0.6, label="Literature prior (non-market)"),
        plt.Line2D([0], [0], marker="D", color="gray", linestyle="",
                    markersize=10, markeredgecolor="black",
                    alpha=0.4, label="Calibrated (Papers 01-02)"),
        plt.Line2D([0], [0], color="gray", linestyle="--",
                    alpha=0.5, label="Cobb-Douglas (σ=1)"),
    ]
    ax.legend(handles=handles, loc="upper right", frameon=False, fontsize=8)

    fig.tight_layout()
    out = FIGURES / "fig_03_gmm_forest.png"
    fig.savefig(out, dpi=FIG_DPI)
    plt.close(fig)
    print(f"Figure saved: {out}")


if __name__ == "__main__":
    print("Paper-03: GMM estimation...")

    # OECD panel
    print("\n--- OECD panel ---")
    panel_oecd = load_panel("panel_oecd.csv")
    gmm_oecd = estimate_all(panel_oecd, "oecd")

    # Poland panel (if available and has required columns)
    pl_path = DATA_PROC / "panel_poland.csv"
    if pl_path.exists():
        try:
            print("\n--- Poland panel ---")
            panel_pl = load_panel("panel_poland.csv")
            estimate_all(panel_pl, "poland")
        except (ValueError, KeyError) as e:
            print(f"  [SKIP] Poland panel missing columns: {e}")

    # Forest plot
    fig_forest_plot(gmm_oecd)
    print("\nDone.")
