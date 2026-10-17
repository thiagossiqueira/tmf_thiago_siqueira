#!/bin/bash
set -euo pipefail

echo "=== Thesis reproducible rebuild ==="

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

BRANCH="$(git branch --show-current)"
if [ -z "$BRANCH" ]; then
    echo "ERROR: detached HEAD."
    exit 1
fi

echo "Repository: $REPO_ROOT"
echo "Branch:     $BRANCH"

echo
echo "=== Updating current branch ==="
git fetch origin "$BRANCH"
git pull --rebase --autostash origin "$BRANCH"

echo
echo "=== Python environment ==="
if [ -z "${VIRTUAL_ENV:-}" ]; then
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    elif [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    fi
fi

python -m pip install -e . --quiet
python -m pip install -r requirements.txt --quiet

echo
echo "=== Canonical input checks ==="
test -f "datos_y_modelos/db/brazil_domestic_govt_bonds/govt_ya_ande.v6.xlsx"
test -f "datos_y_modelos/Domestic/domestic_sovereign_curve_brazil.v5.xlsx"

echo "PASS - sovereign YAS v6 found"
echo "PASS - sovereign metadata v5 found"

echo
echo "=== Syntax validation ==="
python -m py_compile scripts/build_econometrics_panel.py
echo "PASS - build_econometrics_panel.py compiles"

echo
echo "=== Rebuilding econometrics panel ==="
python scripts/build_econometrics_panel.py

OUTPUT="datos_y_modelos/db/econometrics_db/panel_main_and_robustness_rebuilt_v2.xlsx"

echo
echo "=== Final output validation ==="
test -f "$OUTPUT"

python - <<'PY'
import pandas as pd
from pathlib import Path

p = Path(
    "datos_y_modelos/db/econometrics_db/"
    "panel_main_and_robustness_rebuilt_v2.xlsx"
)

df = pd.read_excel(p, sheet_name="ts")

assert len(df) == 4648, f"Unexpected rows: {len(df)}"
assert len(df.columns) == 19, f"Unexpected columns: {len(df.columns)}"
assert df["sovereign_spread_brl"].notna().sum() == 4648
assert df["sovereign_spread_brl"].isna().sum() == 0
assert not df.duplicated(["bond_id", "month"]).any()

print("PASS - final panel validation")
print(f"rows: {len(df):,}")
print(f"columns: {len(df.columns)}")
print(f"bonds: {df['bond_id'].nunique():,}")
print(f"issuers: {df['issuer'].nunique():,}")
print(f"sovereign nonmissing: {df['sovereign_spread_brl'].notna().sum():,}")
print(f"output: {p}")
PY

echo
echo "=== Thesis rebuild completed successfully ==="