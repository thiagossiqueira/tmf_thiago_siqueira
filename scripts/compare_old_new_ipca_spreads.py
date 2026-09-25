from pathlib import Path
import sys

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.core.spread_calculator import DAYCOUNT


OLD_SPREAD_PATH = (
    REPO_ROOT
    / "datos_y_modelos"
    / "db"
    / "output_calculated_spreads"
    / "output_spreads_di_and_ipca.xlsx"
)

NEW_SPREAD_PATH = (
    REPO_ROOT
    / "data"
    / "corp_bonds_ipca_summary.xlsx"
)

MONTHLY_YTM_PATH = (
    REPO_ROOT
    / "datos_y_modelos"
    / "db"
    / "brazil_domestic_corp_bonds"
    / "corp_yld_ytm_mid_revised_monthly.v1.xlsx"
)

WLA_PATH = (
    REPO_ROOT
    / "datos_y_modelos"
    / "db"
    / "id_x_ipca_spread_futures"
    / "hist_ipca_curve_contracts_db.xlsx"
)

OUTPUT_PATH = (
    REPO_ROOT
    / "data"
    / "audit_old_new_ipca_spreads.xlsx"
)


def main():
    # ---------------------------------------------------------
    # 1. LOAD
    # ---------------------------------------------------------
    old = pd.read_excel(
        OLD_SPREAD_PATH,
        sheet_name="values_only",
    )

    new = pd.read_excel(
        NEW_SPREAD_PATH,
    )

    monthly = pd.read_excel(
        MONTHLY_YTM_PATH,
        sheet_name="monthly_asof",
        usecols=[
            "bond_id",
            "obs_date",
            "maturity",
        ],
    )

    wla = pd.read_excel(
        WLA_PATH,
        sheet_name="only_values",
    )

    # ---------------------------------------------------------
    # 2. BASIC CLEANING
    # ---------------------------------------------------------
    old = old[old["Benchmark"].eq("IPCA")].copy()

    old["Obs Date"] = pd.to_datetime(old["Obs Date"])
    new["Obs Date"] = pd.to_datetime(new["Obs Date"])

    old["month"] = old["Obs Date"].dt.to_period("M")
    new["month"] = new["Obs Date"].dt.to_period("M")

    final_bonds = set(new["Bond ID"])

    old_final = old[
        old["Bond ID"].isin(final_bonds)
    ].copy()

    # ---------------------------------------------------------
    # 3. VALIDATE LEGACY SPREAD FORMULA
    #
    # Legacy file labelled the result "Spread (bp)", but it is
    # actually:
    #
    #     corporate yield (%) - benchmark yield (%)
    #
    # i.e. percentage points, not basis points.
    # ---------------------------------------------------------
    old_final["legacy_arithmetic_spread_pp"] = (
        old_final["Corp Yield (%)"]
        - old_final["Yield (%)"]
    )

    old_final["legacy_formula_error"] = (
        old_final["Spread (bp)"]
        - old_final["legacy_arithmetic_spread_pp"]
    )

    legacy_formula_matches = np.isclose(
        old_final["Spread (bp)"],
        old_final["legacy_arithmetic_spread_pp"],
        atol=1e-10,
    ).sum()

    # ---------------------------------------------------------
    # 4. RECOMPUTE OLD INPUTS USING NEW GEOMETRIC FORMULA
    #
    # This isolates the effect of changing benchmark/data from
    # the mechanical effect of changing the spread formula.
    # ---------------------------------------------------------
    old_final["old_geometric_spread_bp"] = (
        (
            (1 + old_final["Corp Yield (%)"] / 100)
            / (1 + old_final["Yield (%)"] / 100)
        )
        - 1
    ) * 10000

    # ---------------------------------------------------------
    # 5. COVERAGE: OLD VS NEW BY BOND-MONTH
    # ---------------------------------------------------------
    old_keys = old_final[
        ["Bond ID", "month"]
    ].drop_duplicates()

    new_keys = new[
        ["Bond ID", "month"]
    ].drop_duplicates()

    coverage = old_keys.merge(
        new_keys,
        on=["Bond ID", "month"],
        how="outer",
        indicator=True,
    )

    common_count = int(
        (coverage["_merge"] == "both").sum()
    )
    old_only_count = int(
        (coverage["_merge"] == "left_only").sum()
    )
    new_only_count = int(
        (coverage["_merge"] == "right_only").sum()
    )

    # ---------------------------------------------------------
    # 6. COMMON BOND-MONTH COMPARISON
    # ---------------------------------------------------------
    common = old_final.merge(
        new[
            [
                "Bond ID",
                "month",
                "Corp Yield (%)",
                "IPCA Benchmark Yield (%)",
                "Spread (bp)",
                "Quote Date",
                "Staleness Days",
                "Exact Date Match",
                "Selected Source",
                "Original Selected Source",
                "Source Overridden",
                "Override Reason",
            ]
        ],
        on=["Bond ID", "month"],
        how="inner",
        suffixes=("_old", "_new"),
        validate="one_to_one",
    )

    common["corp_yield_diff_pp"] = (
        common["Corp Yield (%)_new"]
        - common["Corp Yield (%)_old"]
    )

    common["benchmark_diff_pp"] = (
        common["IPCA Benchmark Yield (%)"]
        - common["Yield (%)"]
    )

    common["spread_diff_bp"] = (
        common["Spread (bp)_new"]
        - common["old_geometric_spread_bp"]
    )

    common["abs_spread_diff_bp"] = (
        common["spread_diff_bp"].abs()
    )

    # ---------------------------------------------------------
    # 7. ISOLATE AN275276 SOURCE OVERRIDE
    # ---------------------------------------------------------
    common_ex_override = common[
        common["Bond ID"] != "AN275276 Corp"
    ].copy()

    material_corp_changes = common[
        common["corp_yield_diff_pp"].abs() > 0.10
    ].copy()

    # ---------------------------------------------------------
    # 8. BENCHMARK CHANGE BY TENOR
    # ---------------------------------------------------------
    common_ex_override["tenor_bucket"] = pd.cut(
        common_ex_override["Tenor (yrs)"],
        bins=[
            -1,
            0.25,
            1,
            3,
            5,
            10,
            100,
        ],
        labels=[
            "<=3m",
            "3m-1y",
            "1-3y",
            "3-5y",
            "5-10y",
            ">10y",
        ],
    )

    tenor_summary = (
        common_ex_override
        .groupby(
            "tenor_bucket",
            observed=True,
        )["benchmark_diff_pp"]
        .agg(
            [
                "count",
                "mean",
                "median",
                "std",
                "min",
                "max",
            ]
        )
        .reset_index()
    )

    # ---------------------------------------------------------
    # 9. NEW-ONLY BOND-MONTHS
    # ---------------------------------------------------------
    new_only = new.merge(
        old_keys,
        on=["Bond ID", "month"],
        how="left",
        indicator=True,
    )

    new_only = new_only[
        new_only["_merge"].eq("left_only")
    ].copy()

    new_only.drop(
        columns="_merge",
        inplace=True,
    )

    new_only["carry_forward"] = (
        ~new_only["Exact Date Match"]
    )

    # Add maturity to compute actual corporate tenor
    monthly["obs_date"] = pd.to_datetime(
        monthly["obs_date"]
    )
    monthly["maturity"] = pd.to_datetime(
        monthly["maturity"]
    )

    new_only = new_only.merge(
        monthly,
        left_on=[
            "Bond ID",
            "Obs Date",
        ],
        right_on=[
            "bond_id",
            "obs_date",
        ],
        how="left",
        validate="one_to_one",
    )

    new_only["tenor_yrs"] = new_only.apply(
        lambda r: DAYCOUNT.tf(
            r["Obs Date"],
            r["maturity"],
        ),
        axis=1,
    )

    # ---------------------------------------------------------
    # 10. WAS NEW COVERAGE BEYOND OLD WLA MAX TENOR?
    # ---------------------------------------------------------
    wla["Curve date"] = pd.to_datetime(
        wla["Curve date"]
    )

    wla["Term"] = pd.to_numeric(
        wla["Term"],
        errors="coerce",
    )

    wla_max = (
        wla.groupby("Curve date")["Term"]
        .max()
        .rename("wla_max_tenor")
    )

    new_only = new_only.merge(
        wla_max,
        left_on="Obs Date",
        right_index=True,
        how="left",
    )

    new_only["beyond_wla_max"] = (
        new_only["tenor_yrs"]
        > new_only["wla_max_tenor"]
    )

    # ---------------------------------------------------------
    # 11. NEW-ONLY SUMMARY BY BOND
    # ---------------------------------------------------------
    new_only_by_bond = (
        new_only.groupby("Bond ID")
        .agg(
            new_months=("month", "size"),
            exact_quotes=("Exact Date Match", "sum"),
            max_staleness=(
                "Staleness Days",
                "max",
            ),
            first_new_month=("month", "min"),
            last_new_month=("month", "max"),
            beyond_wla_max=(
                "beyond_wla_max",
                "sum",
            ),
        )
        .reset_index()
    )

    new_only_by_bond["carry_forward"] = (
        new_only_by_bond["new_months"]
        - new_only_by_bond["exact_quotes"]
    )

    # ---------------------------------------------------------
    # 12. NEW-ONLY SUMMARY BY MONTH
    # ---------------------------------------------------------
    new_only_by_month = (
        new_only.groupby("month")
        .agg(
            new_months=("Bond ID", "size"),
            exact_quotes=(
                "Exact Date Match",
                "sum",
            ),
            carry_forward=(
                "carry_forward",
                "sum",
            ),
            stale_gt30=(
                "Staleness Days",
                lambda z: (z > 30).sum(),
            ),
            max_staleness=(
                "Staleness Days",
                "max",
            ),
            beyond_wla_max=(
                "beyond_wla_max",
                "sum",
            ),
        )
        .reset_index()
    )

    # ---------------------------------------------------------
    # 13. OLD-ONLY BOND-MONTHS
    # ---------------------------------------------------------
    old_only = old_final.merge(
        new_keys,
        on=["Bond ID", "month"],
        how="left",
        indicator=True,
    )

    old_only = old_only[
        old_only["_merge"].eq("left_only")
    ].copy()

    old_only.drop(
        columns="_merge",
        inplace=True,
    )

    # ---------------------------------------------------------
    # 14. MONTHLY COVERAGE OLD VS NEW
    # ---------------------------------------------------------
    old_monthly = (
        old_final.groupby("month")
        .agg(
            old_rows=("Bond ID", "size"),
            old_bonds=("Bond ID", "nunique"),
        )
    )

    new_monthly = (
        new.groupby("month")
        .agg(
            new_rows=("Bond ID", "size"),
            new_bonds=("Bond ID", "nunique"),
        )
    )

    coverage_by_month = (
        old_monthly
        .join(
            new_monthly,
            how="outer",
        )
        .fillna(0)
        .reset_index()
    )

    # ---------------------------------------------------------
    # 15. HEADLINE SUMMARY
    # ---------------------------------------------------------
    summary_rows = [
        {
            "metric": "Old IPCA rows - final 103 bonds",
            "value": len(old_final),
        },
        {
            "metric": "New IPCA rows",
            "value": len(new),
        },
        {
            "metric": "Common bond-months",
            "value": common_count,
        },
        {
            "metric": "Old-only bond-months",
            "value": old_only_count,
        },
        {
            "metric": "New-only bond-months",
            "value": new_only_count,
        },
        {
            "metric": "Legacy arithmetic formula matches",
            "value": legacy_formula_matches,
        },
        {
            "metric": "New-only exact-date quotes",
            "value": int(
                new_only["Exact Date Match"].sum()
            ),
        },
        {
            "metric": "New-only carry-forward",
            "value": int(
                new_only["carry_forward"].sum()
            ),
        },
        {
            "metric": "New-only staleness >30 days",
            "value": int(
                (
                    new_only["Staleness Days"]
                    > 30
                ).sum()
            ),
        },
        {
            "metric": "New-only beyond WLA max tenor",
            "value": int(
                new_only[
                    "beyond_wla_max"
                ].sum()
            ),
        },
        {
            "metric": "Material corporate YTM changes >0.10pp",
            "value": len(
                material_corp_changes
            ),
        },
        {
            "metric": "Mean spread change excl. AN275276 (bp)",
            "value": float(
                common_ex_override[
                    "spread_diff_bp"
                ].mean()
            ),
        },
        {
            "metric": "Mean benchmark change excl. AN275276 (pp)",
            "value": float(
                common_ex_override[
                    "benchmark_diff_pp"
                ].mean()
            ),
        },
        {
            "metric": "Max abs corporate YTM change excl. AN275276 (pp)",
            "value": float(
                common_ex_override[
                    "corp_yield_diff_pp"
                ].abs().max()
            ),
        },
    ]

    summary = pd.DataFrame(
        summary_rows
    )

    # ---------------------------------------------------------
    # 16. LARGEST BENCHMARK/SPREAD CHANGES
    # ---------------------------------------------------------
    largest_changes = (
        common_ex_override
        .sort_values(
            "abs_spread_diff_bp",
            ascending=False,
        )
        .head(100)
        .copy()
    )

    # ---------------------------------------------------------
    # 17. WRITE AUDIT WORKBOOK
    # ---------------------------------------------------------
    with pd.ExcelWriter(
        OUTPUT_PATH,
        engine="openpyxl",
    ) as writer:

        summary.to_excel(
            writer,
            sheet_name="summary",
            index=False,
        )

        common.to_excel(
            writer,
            sheet_name="common_comparison",
            index=False,
        )

        material_corp_changes.to_excel(
            writer,
            sheet_name="corp_yield_changes",
            index=False,
        )

        tenor_summary.to_excel(
            writer,
            sheet_name="benchmark_by_tenor",
            index=False,
        )

        largest_changes.to_excel(
            writer,
            sheet_name="largest_changes",
            index=False,
        )

        new_only.to_excel(
            writer,
            sheet_name="new_only",
            index=False,
        )

        new_only_by_bond.to_excel(
            writer,
            sheet_name="new_only_by_bond",
            index=False,
        )

        new_only_by_month.to_excel(
            writer,
            sheet_name="new_only_by_month",
            index=False,
        )

        old_only.to_excel(
            writer,
            sheet_name="old_only",
            index=False,
        )

        coverage_by_month.to_excel(
            writer,
            sheet_name="coverage_by_month",
            index=False,
        )

    # ---------------------------------------------------------
    # 18. CONSOLE SUMMARY
    # ---------------------------------------------------------
    print("\n=== OLD VS NEW IPCA SPREAD AUDIT ===\n")

    print(summary.to_string(index=False))

    print(
        "\nMaterial corporate YTM changes by bond:"
    )

    if material_corp_changes.empty:
        print("None")
    else:
        print(
            material_corp_changes
            .groupby("Bond ID")
            .size()
            .sort_values(
                ascending=False
            )
            .to_string()
        )

    print(
        f"\nAudit workbook written to:\n{OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()