#!/bin/bash
set -euo pipefail

# ============================================================
# Minimal PythonAnywhere deployment for the thesis dashboard
# ============================================================

PA_USER="tsiqueira"
PA_HOME="/home/${PA_USER}"
APP_DIR="${PA_HOME}/tmf_thiago_siqueira"
VENV_DIR="${PA_HOME}/.virtualenvs/tmf-web"
WSGI_FILE="/var/www/${PA_USER}_pythonanywhere_com_wsgi.py"
BRANCH="${DEPLOY_BRANCH:-jury-revision-recalculate-corporate-spread}"

echo "=== TFM dashboard: minimal PythonAnywhere deploy ==="

# Safety: never apply sparse-checkout to the local Windows thesis repo.
if [ "${HOME:-}" != "${PA_HOME}" ]; then
    echo "ERROR: This script is intended only for PythonAnywhere (${PA_HOME})."
    echo "Current HOME: ${HOME:-<unset>}"
    exit 1
fi

cd "${APP_DIR}"

echo
echo "=== Updating deployment branch: ${BRANCH} ==="
git fetch origin "${BRANCH}"
git checkout "${BRANCH}"

echo
echo "=== Applying minimal sparse checkout ==="
git sparse-checkout init --no-cone

git sparse-checkout set --no-cone --stdin <<'EOF'
/app.py
/requirements-web.txt
/post-pull.sh

/templates/
/static/

/data/real_curve_surface_govt.xlsx
/data/di_surface_with_provenance.xlsx
/data/wla_ntnb_surface_with_provenance.xlsx
/data/corp_bonds_di_summary.xlsx
/data/final_spread_backing_v4.xlsx
/data/govt_bonds_di_summary.xlsx
/data/govt_bonds_ipca_summary.xlsx
/data/govt_bonds_all_consolidated.xlsx
/data/variable_provenance_manifest.json
/data/thesis_figure_manifest.csv

/datos_y_modelos/db/econometrics_db/panel_main_and_robustness_rebuilt_v4.xlsx

/src/econometrics/wp12c_final_m1_m8_total_debt_assets_fe_dk.do
/src/econometrics/wp12c_reestimation/Table5_Final_Eight_Models_Total_Debt_Assets_FE_DK.txt
/src/econometrics/wp12c_reestimation/WP12C_Final_M1_M8_Total_Debt_Assets_FE_DK.log
/output/Informes jurado/wp12c_director_specified_leverage_fallback_audit.txt
/output/Informes jurado/wp12c_total_debt_to_total_assets_coverage_audit.txt
/output/Informes jurado/WP12C_total_debt_to_total_assets_4648.csv

/src/econometrics/wp12a_final_m1_m8_no_trading_days_fe_dk.do
/src/econometrics/wp12a_reestimation/Table5_Final_Eight_Models_No_Trading_Days_FE_DK.txt
/src/econometrics/wp12a_reestimation/WP12A_Final_M1_M8_No_Trading_Days_FE_DK.log

/src/econometrics/wp12b_snd_liquidity_annex_fe_dk.do
/src/econometrics/wp12b_reestimation/WP12B_SND_Liquidity_Annex_M1_M8_FE_DK.txt
/src/econometrics/wp12b_reestimation/WP12B_SND_Liquidity_Annex_FE_DK.log

/src/econometrics/wp07_dk_bandwidth_sensitivity.do
/src/econometrics/wp07_reestimation/Table5_WP07_FE_DK.txt
/src/econometrics/wp07_reestimation/wp07_dk_bandwidth_sensitivity.log
/output/Informes jurado/wp07_dk_bandwidth_sensitivity_audit.txt
EOF

git pull --ff-only origin "${BRANCH}"

echo
echo "=== Python environment ==="
if [ ! -d "${VENV_DIR}" ]; then
    python3 -m venv "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements-web.txt

echo
echo "=== Flask import smoke test ==="
python - <<'PY'
from app import app

client = app.test_client()

for path in [
    "/",
    "/transparency",
    "/spread-transparency",
    "/econometrics",
    "/surface/di",
    "/surface/wla_ntnb",
]:
    response = client.get(path)
    assert response.status_code == 200, (
        f"{path}: unexpected status {response.status_code}"
    )
    print(f"PASS {path}: {response.status_code}")
PY

echo
echo "=== Storage used by deployed checkout ==="
du -sh "${APP_DIR}"

echo
echo "=== Reloading PythonAnywhere web app ==="
if [ -f "${WSGI_FILE}" ]; then
    touch "${WSGI_FILE}"
    echo "Reloaded: https://${PA_USER}.pythonanywhere.com"
else
    echo "WARNING: WSGI file not found yet:"
    echo "  ${WSGI_FILE}"
    echo "Create/configure the web app once in the PythonAnywhere Web tab."
fi

echo
echo "=== Deploy complete ==="
