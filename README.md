# Empirical Estimation of CES Elasticity of Substitution

**Paper-03** in the complexity-econ series: estimates sector-specific CES elasticity of substitution ($\sigma$) from OECD panel data + Polish GUS data, then tests whether Paper-01's key findings survive with empirically grounded parameters.

## Summary

Papers 01-02 use calibrated sector-specific $\sigma$ values (BPO=50, Manufacturing=10, ...). Literature suggests these are 5-10x too high. This paper:

1. Builds an OECD panel (30 countries x 6 sectors x 2000-2023) with IFR robot density + ICT CAPEX as AI proxies
2. Estimates $\sigma$ via normalized CES supply system + Arellano-Bond GMM
3. Cross-validates with hierarchical Bayesian estimation (PyMC)
4. Re-runs the ABM with empirical $\sigma$ to test robustness of bimodality and critical points

## Reproduce

```bash
# Install dependencies
pip install -r requirements.txt

# Full pipeline
make all

# Or step by step
make data       # Download + clean + merge
make estimate   # GMM + Bayesian estimation
make sensitivity # ABM sensitivity analysis
make figures    # All figures
make paper      # Compile LaTeX
```

## Structure

```
analysis/python/        8 pipeline scripts + config
data/raw/               Downloaded data (gitignored)
data/processed/         Cleaned panels (gitignored)
figures/                8 PNG figures
latex/                  Paper (XeLaTeX)
results/                Estimation CSVs + ABM sensitivity
simulations/scripts/    ABM sensitivity runner
```

## Dependencies

- **Data**: Python 3 (pandas, requests, eurostat)
- **Estimation**: linearmodels, pymc, arviz
- **Simulation**: [complexity-econ/core](https://github.com/complexity-econ/core) (Scala 3.5.2, sbt)
- **Paper**: XeLaTeX + biblatex

## License

MIT

## Related

- [Paper-01: The Acceleration Paradox](https://github.com/complexity-econ/paper-01-acceleration-paradox)
- [Paper-02: Monetary Regimes](https://github.com/complexity-econ/paper-02-monetary-regimes)
- [Core engine](https://github.com/complexity-econ/core)
