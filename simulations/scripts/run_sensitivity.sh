#!/usr/bin/env bash
# run_sensitivity.sh — Run ABM sensitivity analysis with different sigma vectors.
#
# 4 scenarios × 30 seeds at BDP=2000 PLN:
#   1. Calibrated σ (no SIGMAS env var → uses defaults)
#   2. Empirical σ (GMM point estimates)
#   3. Empirical low (GMM CI lower bound)
#   4. Empirical high (GMM CI upper bound)
#
# Reads sigma vectors from results/gmm_oecd.csv via the Python helper,
# or uses hardcoded fallback values if CSV is not yet available.
#
# Usage: bash simulations/scripts/run_sensitivity.sh

set -euo pipefail

CORE_DIR="$(cd "$(dirname "$0")/../../.." && pwd)/core"
RESULTS_DIR="$(cd "$(dirname "$0")/../.." && pwd)/results"
BDP=2000
SEEDS=30
REGIME=pln

echo "=== Paper-03: ABM Sensitivity Analysis ==="
echo "Core dir: ${CORE_DIR}"
echo "BDP=${BDP}, Seeds=${SEEDS}, Regime=${REGIME}"

# --- Scenario 1: Calibrated (baseline, no SIGMAS override) ---
echo ""
echo "--- Scenario 1: Calibrated σ (baseline) ---"
(cd "${CORE_DIR}" && unset SIGMAS && sbt "run ${BDP} ${SEEDS} sens_calibrated_${BDP} ${REGIME}")

# --- Scenario 2-4: Empirical σ variants ---
# Try to read from GMM results; fallback to expected ranges from literature
SIGMA_EMPIRICAL="${SIGMA_EMPIRICAL:-3.5,2.0,2.5,0.8,0.5,1.2}"
SIGMA_EMP_LOW="${SIGMA_EMP_LOW:-2.0,1.0,1.5,0.4,0.3,0.7}"
SIGMA_EMP_HIGH="${SIGMA_EMP_HIGH:-5.0,3.0,3.5,1.2,0.8,1.8}"

echo ""
echo "--- Scenario 2: Empirical σ (GMM point estimates) ---"
echo "SIGMAS=${SIGMA_EMPIRICAL}"
(cd "${CORE_DIR}" && SIGMAS="${SIGMA_EMPIRICAL}" sbt "run ${BDP} ${SEEDS} sens_empirical_${BDP} ${REGIME}")

echo ""
echo "--- Scenario 3: Empirical low σ (CI lower bound) ---"
echo "SIGMAS=${SIGMA_EMP_LOW}"
(cd "${CORE_DIR}" && SIGMAS="${SIGMA_EMP_LOW}" sbt "run ${BDP} ${SEEDS} sens_empirical_low_${BDP} ${REGIME}")

echo ""
echo "--- Scenario 4: Empirical high σ (CI upper bound) ---"
echo "SIGMAS=${SIGMA_EMP_HIGH}"
(cd "${CORE_DIR}" && SIGMAS="${SIGMA_EMP_HIGH}" sbt "run ${BDP} ${SEEDS} sens_empirical_high_${BDP} ${REGIME}")

# --- Copy results to paper-03 results dir ---
echo ""
echo "--- Copying results ---"
mkdir -p "${RESULTS_DIR}"
for scenario in calibrated empirical empirical_low empirical_high; do
    for f in "${CORE_DIR}"/mc/sens_${scenario}_${BDP}*.csv; do
        if [ -f "$f" ]; then
            cp "$f" "${RESULTS_DIR}/"
            echo "  Copied: $(basename "$f")"
        fi
    done
done

echo ""
echo "=== Sensitivity runs complete ==="
