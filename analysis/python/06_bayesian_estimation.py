#!/usr/bin/env python3
"""
06_bayesian_estimation.py — Hierarchical Bayesian CES estimation via PyMC.

Model:
  sigma_s ~ LogNormal(log(prior_mean_s), prior_sd_s)
  beta_s = 1 - 1/sigma_s
  ln(w_it) ~ N(alpha_i + beta_s * ln(Y/L)_it + gamma_s * t, sigma_e)
  alpha_i ~ N(0, sigma_alpha)       [hierarchical country effects]

Priors from Knoblach et al. (2020) meta-analysis.
NUTS sampler, 4000 samples × 4 chains, target_accept=0.95.

Outputs:
  results/bayesian_oecd.csv           — posterior summaries per sector
  results/bayesian_trace_{sector}.nc  — ArviZ InferenceData (NetCDF)
  figures/fig_04_bayesian_posteriors.png
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from config import (
    DATA_PROC, RESULTS, FIGURES,
    ABM_SECTORS, MARKET_SECTORS, NON_MARKET_SECTORS,
    SECTOR_COLORS, BAYESIAN_PRIORS, CALIBRATED_SIGMA,
    FIG_DPI, FIG_SIZE_PANEL,
)

plt.rcParams.update({"font.family": "serif", "font.size": 10, "figure.dpi": FIG_DPI})

N_SAMPLES = 4000
N_CHAINS = 4
TARGET_ACCEPT = 0.95


def load_panel() -> pd.DataFrame:
    path = DATA_PROC / "panel_oecd.csv"
    if not path.exists():
        raise FileNotFoundError(f"Run 02_clean_merge.py first: {path}")
    return pd.read_csv(path)


def estimate_sector_bayesian(panel: pd.DataFrame, sector: str) -> dict:
    """Estimate sigma for one sector using PyMC MCMC."""
    sub = panel[panel["sector_abm"] == sector].copy()
    sub = sub.dropna(subset=["w", "Y_L"])
    sub = sub[(sub["w"] > 0) & (sub["Y_L"] > 0)]

    result = {
        "sector": sector,
        "sigma_mean": np.nan,
        "sigma_sd": np.nan,
        "sigma_hdi_lo": np.nan,
        "sigma_hdi_hi": np.nan,
        "r_hat": np.nan,
        "ess_bulk": np.nan,
        "n_obs": len(sub),
        "method": "bayesian",
    }

    if len(sub) < 30:
        print(f"  [{sector}] Too few observations ({len(sub)}), skipping")
        return result

    # Prepare data
    sub["ln_w"] = np.log(sub["w"])
    sub["ln_yl"] = np.log(sub["Y_L"])
    sub["t"] = sub["year"] - sub["year"].min()

    # Country encoding
    countries = sub["country"].unique()
    country_idx = sub["country"].map({c: i for i, c in enumerate(countries)}).values
    n_countries = len(countries)

    prior = BAYESIAN_PRIORS[sector]

    try:
        import pymc as pm
        import arviz as az

        with pm.Model() as model:
            # Prior on sigma (CES elasticity)
            sigma_ces = pm.LogNormal(
                "sigma",
                mu=np.log(prior["mean"]),
                sigma=prior["sd"],
            )

            # Derived beta
            beta = pm.Deterministic("beta", 1.0 - 1.0 / sigma_ces)

            # Time trend coefficient
            gamma = pm.Normal("gamma", mu=0, sigma=0.1)

            # Hierarchical country effects
            sigma_alpha = pm.HalfNormal("sigma_alpha", sigma=1.0)
            alpha = pm.Normal("alpha", mu=0, sigma=sigma_alpha, shape=n_countries)

            # Observation noise
            sigma_e = pm.HalfNormal("sigma_e", sigma=1.0)

            # Likelihood
            mu = alpha[country_idx] + beta * sub["ln_yl"].values + gamma * sub["t"].values
            pm.Normal("ln_w_obs", mu=mu, sigma=sigma_e, observed=sub["ln_w"].values)

            # Sample
            trace = pm.sample(
                draws=N_SAMPLES,
                chains=N_CHAINS,
                target_accept=TARGET_ACCEPT,
                return_inferencedata=True,
                progressbar=True,
                random_seed=42,
            )

        # Extract posterior summary
        summary = az.summary(trace, var_names=["sigma", "beta"])
        sigma_post = trace.posterior["sigma"].values.flatten()

        hdi = az.hdi(trace, var_names=["sigma"], hdi_prob=0.95)
        hdi_vals = hdi["sigma"].values

        result.update({
            "sigma_mean": float(np.mean(sigma_post)),
            "sigma_sd": float(np.std(sigma_post)),
            "sigma_hdi_lo": float(hdi_vals[0]),
            "sigma_hdi_hi": float(hdi_vals[1]),
            "r_hat": float(summary.loc["sigma", "r_hat"]),
            "ess_bulk": float(summary.loc["sigma", "ess_bulk"]),
        })

        # Save trace
        trace_path = RESULTS / f"bayesian_trace_{sector.lower().replace('/', '_')}.nc"
        trace.to_netcdf(str(trace_path))
        print(f"  [{sector}] sigma={result['sigma_mean']:.3f} "
              f"(HDI [{result['sigma_hdi_lo']:.3f}, {result['sigma_hdi_hi']:.3f}]), "
              f"R-hat={result['r_hat']:.4f}, ESS={result['ess_bulk']:.0f}")

    except ImportError:
        print(f"  [{sector}] PyMC not installed — using analytic approximation")
        result = _analytic_fallback(sub, sector, prior, result)
    except Exception as e:
        print(f"  [{sector}] Bayesian estimation failed: {e}")
        result = _analytic_fallback(sub, sector, prior, result)

    return result


def _analytic_fallback(sub: pd.DataFrame, sector: str,
                       prior: dict, result: dict) -> dict:
    """Approximate posterior using first-differenced OLS + prior update."""
    # Reset multi-index if needed
    if isinstance(sub.index, pd.MultiIndex):
        sub = sub.reset_index()

    # First-difference within country to remove FE (same as GMM approach)
    sub = sub.sort_values(["country", "year"])
    sub["d_ln_w"] = sub.groupby("country")["ln_w"].diff()
    sub["d_ln_yl"] = sub.groupby("country")["ln_yl"].diff()
    sub = sub.dropna(subset=["d_ln_w", "d_ln_yl"])

    if len(sub) < 10:
        return result

    X = np.column_stack([np.ones(len(sub)), sub["d_ln_yl"].values])
    y = sub["d_ln_w"].values

    try:
        coeffs = np.linalg.lstsq(X, y, rcond=None)[0]
        beta_ols = coeffs[1]
        resid = y - X @ coeffs
        n, k = len(y), X.shape[1]
        mse = np.sum(resid ** 2) / (n - k)
        se_beta = np.sqrt(mse * np.linalg.inv(X.T @ X)[1, 1])

        # Prior-data compromise (simplified normal posterior)
        prior_beta = 1.0 - 1.0 / prior["mean"]
        prior_var = (prior["sd"] / prior["mean"] ** 2) ** 2  # delta method
        data_var = se_beta ** 2

        post_var = 1.0 / (1.0 / prior_var + 1.0 / data_var)
        post_mean = post_var * (prior_beta / prior_var + beta_ols / data_var)

        sigma_est = 1.0 / (1.0 - post_mean) if post_mean < 1.0 else np.nan
        dsdb = 1.0 / (1.0 - post_mean) ** 2 if post_mean < 1.0 else np.nan
        sigma_sd = abs(dsdb) * np.sqrt(post_var) if dsdb else np.nan

        result.update({
            "sigma_mean": sigma_est,
            "sigma_sd": sigma_sd,
            "sigma_hdi_lo": sigma_est - 1.96 * sigma_sd if sigma_sd else np.nan,
            "sigma_hdi_hi": sigma_est + 1.96 * sigma_sd if sigma_sd else np.nan,
            "r_hat": 1.0,  # analytic, no convergence issue
            "ess_bulk": float(n),
            "method": "analytic-fallback",
        })
        print(f"  [{sector}] Analytic: sigma={sigma_est:.3f} (SD={sigma_sd:.3f})")
    except Exception as e:
        print(f"  [{sector}] Analytic fallback failed: {e}")

    return result


def _prior_only_row(sector: str) -> dict:
    """Non-market sector: report prior as-is (no data update)."""
    prior = BAYESIAN_PRIORS[sector]
    return {
        "sector": sector,
        "sigma_mean": prior["mean"],
        "sigma_sd": prior["sd"],
        "sigma_hdi_lo": prior["mean"] - 1.96 * prior["sd"],
        "sigma_hdi_hi": prior["mean"] + 1.96 * prior["sd"],
        "r_hat": np.nan,
        "ess_bulk": np.nan,
        "n_obs": 0,
        "method": "prior-only",
    }


def estimate_all(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sector in ABM_SECTORS:
        if sector in NON_MARKET_SECTORS:
            row = _prior_only_row(sector)
            print(f"  [{sector}] prior-only: sigma={row['sigma_mean']:.3f} "
                  f"(SD={row['sigma_sd']:.3f}) — SNA cost convention")
        else:
            row = estimate_sector_bayesian(panel, sector)
        rows.append(row)
    df = pd.DataFrame(rows)
    out = RESULTS / "bayesian_oecd.csv"
    df.to_csv(out, index=False)
    print(f"\n=> Bayesian results saved: {out}")
    return df


def fig_posteriors(bayes_df: pd.DataFrame):
    """Figure 4: Posterior distributions of sigma per sector."""
    fig, axes = plt.subplots(2, 3, figsize=FIG_SIZE_PANEL)
    axes = axes.flatten()

    from scipy.stats import norm

    for i, sector in enumerate(ABM_SECTORS):
        ax = axes[i]
        row = bayes_df[bayes_df["sector"] == sector].iloc[0]
        is_prior = row.get("method") == "prior-only"

        if pd.isna(row["sigma_mean"]):
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    transform=ax.transAxes)
            ax.set_title(sector)
            continue

        # Try loading full trace for density plot
        trace_path = RESULTS / f"bayesian_trace_{sector.lower().replace('/', '_')}.nc"
        trace_loaded = False
        if not is_prior:
            try:
                import arviz as az
                trace = az.from_netcdf(str(trace_path))
                sigma_samples = trace.posterior["sigma"].values.flatten()
                ax.hist(sigma_samples, bins=60, density=True, alpha=0.6,
                        color=SECTOR_COLORS[sector], edgecolor="none")
                trace_loaded = True
            except Exception:
                pass

        if not trace_loaded:
            # Plot normal approximation (posterior or prior-only)
            x = np.linspace(
                max(0.01, row["sigma_mean"] - 3 * row["sigma_sd"]),
                row["sigma_mean"] + 3 * row["sigma_sd"],
                200,
            )
            pdf = norm.pdf(x, row["sigma_mean"], row["sigma_sd"])
            ls = "--" if is_prior else "-"
            ax.fill_between(x, pdf, alpha=0.3 if is_prior else 0.6,
                            color=SECTOR_COLORS[sector])
            ax.plot(x, pdf, color=SECTOR_COLORS[sector], linewidth=1.5,
                    linestyle=ls)

        # Mark calibrated value
        cal = CALIBRATED_SIGMA[sector]
        if cal <= row["sigma_mean"] + 4 * row["sigma_sd"]:
            ax.axvline(cal, color="red", linestyle="--", alpha=0.7, linewidth=1.5)

        # Mark posterior/prior mean
        ax.axvline(row["sigma_mean"], color="black", linestyle="-", linewidth=1.5)

        title = f"{sector} (prior only)" if is_prior else sector
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("σ")
        if i % 3 == 0:
            ax.set_ylabel("Density")

    fig.suptitle("Bayesian Posterior Distributions of σ", fontsize=12, y=1.02)
    fig.tight_layout()
    out = FIGURES / "fig_04_bayesian_posteriors.png"
    fig.savefig(out, dpi=FIG_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Figure saved: {out}")


if __name__ == "__main__":
    print("Paper-03: Bayesian estimation...")
    panel = load_panel()
    bayes_df = estimate_all(panel)
    fig_posteriors(bayes_df)
    print("\nDone.")
