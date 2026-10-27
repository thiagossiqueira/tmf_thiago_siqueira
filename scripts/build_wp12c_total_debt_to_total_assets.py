from pathlib import Path
import pandas as pd

try:
    import scripts.build_econometrics_panel as b
except ModuleNotFoundError:
    import build_econometrics_panel as b


ROOT = Path(__file__).resolve().parents[1]

DIRECT_SOURCE = (
    ROOT
    / "datos_y_modelos"
    / "db"
    / "issuers_fundamental_data"
    / "TOT_DEBT_TO_TOT_ASSET.xlsx"
)

OUTPUT_CSV = (
    ROOT
    / "output"
    / "Informes jurado"
    / "WP12C_total_debt_to_total_assets_4648.csv"
)

OUTPUT_AUDIT = (
    ROOT
    / "output"
    / "Informes jurado"
    / "wp12c_total_debt_to_total_assets_coverage_audit.txt"
)


def main():
    inputs = b.resolve_inputs()

    spine = b.build_bond_month_spine(inputs)
    accounting = b.build_accounting_controls(inputs, spine)

    required_parents = set(
        accounting["accounting_parent"].dropna().unique()
    )

    direct = b._load_quarterly_fundamental(
        DIRECT_SOURCE,
        required_parents,
    )

    out = accounting[
        [
            "bond_id",
            "obs_date",
            "accounting_parent",
            "accounting_primary_quarter",
            "accounting_source_quarter",
            "accounting_fallback_quarters",
            "accounting_debt",
            "accounting_bs_tot_asset",
        ]
    ].copy()

    out["source_q"] = pd.PeriodIndex(
        out["accounting_source_quarter"],
        freq="Q",
    )

    out["total_debt_to_total_assets"] = [
        direct.get(
            (row.accounting_parent, row.source_q),
            float("nan"),
        )
        for row in out.itertuples(index=False)
    ]

    out["total_debt_to_total_assets_constructed"] = (
        100.0
        * out["accounting_debt"]
        / out["accounting_bs_tot_asset"]
    )

    out["direct_minus_constructed_pp"] = (
        out["total_debt_to_total_assets"]
        - out["total_debt_to_total_assets_constructed"]
    )

    out = out.drop(columns=["source_q"])

    panel_keys = spine[
        [
            "bond_id",
            "issuer",
            "obs_date",
            "month",
        ]
    ].copy()

    out = panel_keys.merge(
        out,
        on=["bond_id", "obs_date"],
        how="left",
        validate="one_to_one",
    )

    if len(out) != 4648:
        raise AssertionError(
            f"Expected 4,648 rows; found {len(out):,}."
        )

    if out[["bond_id", "obs_date"]].duplicated().any():
        raise AssertionError("Duplicate bond-date keys.")

    if out["total_debt_to_total_assets"].isna().any():
        raise AssertionError(
            "Direct Bloomberg leverage contains missing values."
        )

    max_abs_diff = (
        out["direct_minus_constructed_pp"]
        .abs()
        .max()
    )

    if max_abs_diff > 0.01:
        raise AssertionError(
            "Direct Bloomberg field differs from reconstructed "
            f"Debt/Assets by more than 0.01 pp: {max_abs_diff}"
        )

    n_bonds = out["bond_id"].nunique()
    n_issuers = out["issuer"].nunique()

    if n_bonds != 103 or n_issuers != 48:
        raise AssertionError(
            f"Unexpected panel dimensions: "
            f"{n_bonds} bonds / {n_issuers} issuers."
        )

    OUTPUT_CSV.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    out.to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8",
    )

    lev = out["total_debt_to_total_assets"]

    audit = f"""WP-12C DIRECTOR-SPECIFIED LEVERAGE FALLBACK AUDIT

Definition
----------
Main leverage field:
Bloomberg TOT_DEBT_TO_TOT_ASSET

Units:
Percent of total assets.

Historical Bloomberg query:
BDP(parent equity ticker, TOT_DEBT_TO_TOT_ASSET,
    FUND_PER=<quarter>, EQY_FUND_YEAR=<year>, fill=b)

PIT convention
--------------
Uses the frozen accounting_source_quarter selected by
scripts/build_econometrics_panel.py.

That convention is shared with CFO/assets and Debt/EBITDA:
latest eligible fiscal quarter at each exact corporate obs_date,
one-quarter fallback when required, and the already-frozen
two-quarter exception only where permitted by the canonical builder.

Coverage
--------
Observations: {len(out):,}
Nonmissing leverage observations: {lev.notna().sum():,}
Missing leverage observations: {lev.isna().sum():,}
Coverage: {100 * lev.notna().mean():.4f}%
Bonds: {n_bonds}
Issuers: {n_issuers}
First obs_date: {out['obs_date'].min().date()}
Last obs_date: {out['obs_date'].max().date()}

Distribution
------------
Minimum: {lev.min():.10f}
Median: {lev.median():.10f}
Maximum: {lev.max():.10f}

Lineage cross-check
-------------------
Constructed comparator:
100 * SHORT_AND_LONG_TERM_DEBT / BS_TOT_ASSET

Maximum absolute direct-vs-constructed difference:
{max_abs_diff:.10f} percentage points

Observations with absolute difference > 0.01 pp:
{int((out['direct_minus_constructed_pp'].abs() > 0.01).sum())}

Decision
--------
PASS.

Bloomberg TOT_DEBT_TO_TOT_ASSET is the director-specified
Total Debt / Total Assets fallback.

It preserves the full frozen panel:
4,648 observations / 103 bonds / 48 issuers.

Book Total Debt / Equity Market Cap remains a separate leverage
robustness measure and is not the main-table leverage.
"""

    OUTPUT_AUDIT.write_text(
        audit,
        encoding="utf-8",
    )

    print(audit)
    print(f"CSV:   {OUTPUT_CSV}")
    print(f"AUDIT: {OUTPUT_AUDIT}")


if __name__ == "__main__":
    main()
