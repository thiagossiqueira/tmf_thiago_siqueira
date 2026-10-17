$ErrorActionPreference = "Stop"

Write-Host "=== Thesis reproducible rebuild ==="

$repoRoot = (git rev-parse --show-toplevel).Trim()
Set-Location $repoRoot

$branch = (git branch --show-current).Trim()
if ([string]::IsNullOrWhiteSpace($branch)) {
    throw "Detached HEAD."
}

Write-Host "Repository: $repoRoot"
Write-Host "Branch:     $branch"

Write-Host ""
Write-Host "=== Python environment ==="

if (-not $env:VIRTUAL_ENV) {
    if (Test-Path ".\.venv\Scripts\Activate.ps1") {
        & ".\.venv\Scripts\Activate.ps1"
    }
    elseif (Test-Path ".\venv\Scripts\Activate.ps1") {
        & ".\venv\Scripts\Activate.ps1"
    }
}

Write-Host ""
Write-Host "=== Canonical input checks ==="

$yas = ".\datos_y_modelos\db\brazil_domestic_govt_bonds\govt_ya_ande.v6.xlsx"
$meta = ".\datos_y_modelos\Domestic\domestic_sovereign_curve_brazil.v5.xlsx"

if (-not (Test-Path $yas)) { throw "Missing sovereign YAS v6: $yas" }
if (-not (Test-Path $meta)) { throw "Missing sovereign metadata v5: $meta" }

Write-Host "PASS - sovereign YAS v6 found"
Write-Host "PASS - sovereign metadata v5 found"

Write-Host ""
Write-Host "=== Syntax validation ==="

python -m py_compile .\scripts\build_econometrics_panel.py
if ($LASTEXITCODE -ne 0) {
    throw "build_econometrics_panel.py failed to compile"
}

Write-Host "PASS - build_econometrics_panel.py compiles"

Write-Host ""
Write-Host "=== Rebuilding econometrics panel ==="

python .\scripts\build_econometrics_panel.py
if ($LASTEXITCODE -ne 0) {
    throw "Econometrics panel rebuild failed"
}

$output = ".\datos_y_modelos\db\econometrics_db\panel_main_and_robustness_rebuilt_v2.xlsx"

Write-Host ""
Write-Host "=== Final output validation ==="

if (-not (Test-Path $output)) {
    throw "Expected output not found: $output"
}

$validationCode = @(
    "import pandas as pd"
    "from pathlib import Path"
    "p = Path('datos_y_modelos/db/econometrics_db/panel_main_and_robustness_rebuilt_v2.xlsx')"
    "df = pd.read_excel(p, sheet_name='ts')"
    "assert len(df) == 4648, f'Unexpected rows: {len(df)}'"
    "assert len(df.columns) == 19, f'Unexpected columns: {len(df.columns)}'"
    "assert df['sovereign_spread_brl'].notna().sum() == 4648"
    "assert df['sovereign_spread_brl'].isna().sum() == 0"
    "assert not df.duplicated(['bond_id','month']).any()"
    "print('PASS - final panel validation')"
    "print(f'rows: {len(df):,}')"
    "print(f'columns: {len(df.columns)}')"
    "print(f'bonds: {df[`"bond_id`"].nunique():,}')"
    "print(f'issuers: {df[`"issuer`"].nunique():,}')"
    "print(f'sovereign nonmissing: {df[`"sovereign_spread_brl`"].notna().sum():,}')"
    "print(f'output: {p}')"
)

($validationCode -join "`n") | python -
if ($LASTEXITCODE -ne 0) {
    throw "Final panel validation failed"
}

Write-Host ""
Write-Host "=== Thesis rebuild completed successfully ==="