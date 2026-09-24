from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_RAW_YTM = Path(
    "datos_y_modelos/db/brazil_domestic_corp_bonds/"
    "corp_yld_ytm_mid_revised_raw.v1.xlsx"
)
DEFAULT_REAL_CURVE = Path("data/real_curve_surface_corp.xlsx")
DEFAULT_PANEL = Path(
    "datos_y_modelos/db/econometrics_db/"
    "panel_main_and_robustness.xlsx"
)
DEFAULT_OUTPUT = Path(
    "datos_y_modelos/db/brazil_domestic_corp_bonds/"
    "corp_yld_ytm_mid_revised_monthly.v1.xlsx"
)

EXPECTED_BONDS = 103
EXPECTED_CURVE_DATES = 186

ZERO_AS_INVALID_BONDS = {
    "AP304401 Corp",
    "EJ493748 Corp",
    "EK141999 Corp",
    "EK142053 Corp",
    "EK142311 Corp",
    "EK142341 Corp",
}

class MonthlyYieldBuildError(RuntimeError):
    """Raised when an input or integrity check fails."""


def _read_inputs(
    raw_path: Path,
    curve_path: Path,
    panel_path: Path,
) -> tuple[pd.DataFrame, pd.DatetimeIndex, pd.DataFrame]:
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw YTM workbook not found: {raw_path}")

    if not curve_path.exists():
        raise FileNotFoundError(f"Real-curve surface not found: {curve_path}")

    if not panel_path.exists():
        raise FileNotFoundError(f"Submitted panel workbook not found: {panel_path}")

    raw = pd.read_excel(raw_path, sheet_name="raw_daily_yield")
    curve = pd.read_excel(curve_path)
    panel = pd.read_excel(panel_path, sheet_name="ts")

    required_raw = {
        "bond_id",
        "DATE",
        "YLD_YTM_MID",
        "revised_selected_source",
        "revised_security_with_source",
        "selected_source",
        "security_with_source",
        "source_overridden",
        "override_reason",
    }
    missing_raw = required_raw.difference(raw.columns)
    if missing_raw:
        raise MonthlyYieldBuildError(
            f"Raw YTM workbook is missing columns: {sorted(missing_raw)}"
        )

    if "obs_date" not in curve.columns:
        raise MonthlyYieldBuildError(
            "Real-curve surface is missing column 'obs_date'."
        )

    required_panel = {"bond_id", "maturity"}
    missing_panel = required_panel.difference(panel.columns)
    if missing_panel:
        raise MonthlyYieldBuildError(
            f"Submitted panel is missing columns: {sorted(missing_panel)}"
        )

    raw["bond_id"] = raw["bond_id"].astype(str).str.strip()
    raw["DATE"] = pd.to_datetime(raw["DATE"], errors="coerce")
    raw["YLD_YTM_MID"] = pd.to_numeric(
        raw["YLD_YTM_MID"],
        errors="coerce",
    )

    raw["quote_invalid_reason"] = pd.NA

    raw.loc[
        raw["YLD_YTM_MID"].eq(-100),
        "quote_invalid_reason",
    ] = "sentinel_minus_100"

    raw.loc[
        raw["bond_id"].isin(ZERO_AS_INVALID_BONDS)
        & raw["YLD_YTM_MID"].eq(0),
        "quote_invalid_reason",
    ] = "audited_invalid_zero"

    raw["quote_is_valid"] = raw["quote_invalid_reason"].isna()


    if raw["DATE"].isna().any():
        raise MonthlyYieldBuildError(
            f"Raw YTM has {int(raw['DATE'].isna().sum())} unparseable DATE values."
        )

    if raw["YLD_YTM_MID"].isna().any():
        raise MonthlyYieldBuildError(
            "raw_daily_yield should contain non-null YLD_YTM_MID only, "
            f"but found {int(raw['YLD_YTM_MID'].isna().sum())} missing values."
        )

    curve_dates = pd.DatetimeIndex(
        pd.to_datetime(curve["obs_date"], errors="coerce")
        .dropna()
        .drop_duplicates()
        .sort_values()
    )

    maturity = (
        panel[["bond_id", "maturity"]]
        .drop_duplicates()
        .copy()
    )
    maturity["bond_id"] = maturity["bond_id"].astype(str).str.strip()
    maturity["maturity"] = pd.to_datetime(
        maturity["maturity"],
        errors="coerce",
    )

    if maturity["maturity"].isna().any():
        raise MonthlyYieldBuildError(
            f"Found {int(maturity['maturity'].isna().sum())} unparseable maturities."
        )

    multi_maturity = (
        maturity.groupby("bond_id")["maturity"].nunique().gt(1)
    )
    if multi_maturity.any():
        bad = multi_maturity[multi_maturity].index.tolist()
        raise MonthlyYieldBuildError(
            f"Bonds with multiple maturities: {bad}"
        )

    maturity = maturity.drop_duplicates("bond_id")

    return raw, curve_dates, maturity


def build_monthly_asof_panel(
    raw: pd.DataFrame,
    curve_dates: pd.DatetimeIndex,
    maturity: pd.DataFrame,
) -> pd.DataFrame:
    raw_bonds = set(raw["bond_id"].unique())
    maturity_bonds = set(maturity["bond_id"].unique())

    if len(raw_bonds) != EXPECTED_BONDS:
        raise MonthlyYieldBuildError(
            f"Expected {EXPECTED_BONDS} raw-YTM bonds, found {len(raw_bonds)}."
        )

    if len(maturity_bonds) != EXPECTED_BONDS:
        raise MonthlyYieldBuildError(
            f"Expected {EXPECTED_BONDS} maturity bonds, found {len(maturity_bonds)}."
        )

    if raw_bonds != maturity_bonds:
        missing_in_raw = sorted(maturity_bonds - raw_bonds)
        missing_in_panel = sorted(raw_bonds - maturity_bonds)
        raise MonthlyYieldBuildError(
            "Bond universes do not match. "
            f"Missing in raw={missing_in_raw}; missing in panel={missing_in_panel}"
        )

    if len(curve_dates) != EXPECTED_CURVE_DATES:
        raise MonthlyYieldBuildError(
            f"Expected {EXPECTED_CURVE_DATES} curve obs_dates, "
            f"found {len(curve_dates)}."
        )

    maturity_map = maturity.set_index("bond_id")["maturity"]

    output_parts: list[pd.DataFrame] = []

    for bond_id in sorted(raw_bonds):
        quotes = (
            raw.loc[
                raw["bond_id"].eq(bond_id)
                & raw["quote_is_valid"]
                ]
            .sort_values("DATE")
            .drop_duplicates(subset=["DATE"], keep="last")
            .copy()
        )

        if quotes.empty:
            continue

        first_quote_date = quotes["DATE"].min()
        bond_maturity = maturity_map.loc[bond_id]

        eligible_dates = curve_dates[
            (curve_dates >= first_quote_date)
            & (curve_dates <= bond_maturity)
        ]

        if len(eligible_dates) == 0:
            continue

        calendar = pd.DataFrame({"obs_date": eligible_dates})

        quote_cols = [
            "DATE",
            "YLD_YTM_MID",
            "revised_selected_source",
            "revised_security_with_source",
            "selected_source",
            "security_with_source",
            "source_overridden",
            "override_reason",
        ]

        monthly = pd.merge_asof(
            calendar.sort_values("obs_date"),
            quotes[quote_cols].sort_values("DATE"),
            left_on="obs_date",
            right_on="DATE",
            direction="backward",
            allow_exact_matches=True,
        )

        monthly = monthly.rename(
            columns={
                "DATE": "quote_date",
                "YLD_YTM_MID": "corporate_yield_pct",
            }
        )

        monthly.insert(0, "bond_id", bond_id)
        monthly["maturity"] = bond_maturity
        monthly["first_valid_quote_date"] = first_quote_date

        monthly["staleness_days"] = (
            monthly["obs_date"] - monthly["quote_date"]
        ).dt.days

        monthly["exact_date_match"] = (
            monthly["obs_date"].eq(monthly["quote_date"])
        )

        monthly["days_to_maturity_calendar"] = (
            bond_maturity - monthly["obs_date"]
        ).dt.days

        output_parts.append(monthly)

    if not output_parts:
        raise MonthlyYieldBuildError("No monthly bond observations were created.")

    out = (
        pd.concat(output_parts, ignore_index=True)
        .sort_values(["bond_id", "obs_date"])
        .reset_index(drop=True)
    )

    if out["quote_date"].isna().any():
        raise MonthlyYieldBuildError(
            "Unexpected missing quote_date after filtering obs_date >= first quote."
        )

    if (out["quote_date"] > out["obs_date"]).any():
        raise MonthlyYieldBuildError(
            "Found quote_date later than obs_date."
        )

    if (out["obs_date"] > out["maturity"]).any():
        raise MonthlyYieldBuildError(
            "Found obs_date after bond maturity."
        )

    duplicates = out.duplicated(subset=["bond_id", "obs_date"]).sum()
    if duplicates:
        raise MonthlyYieldBuildError(
            f"Found {duplicates} duplicate bond_id/obs_date rows."
        )

    return out


def build_summary(monthly: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary = pd.DataFrame(
        {
            "metric": [
                "monthly_rows",
                "unique_bonds",
                "first_obs_date",
                "last_obs_date",
                "exact_date_matches",
                "exact_date_match_share_pct",
                "staleness_mean_days",
                "staleness_median_days",
                "staleness_max_days",
                "staleness_le_3_days",
                "staleness_le_7_days",
                "staleness_le_30_days",
                "staleness_gt_30_days",
                "source_overridden_rows",
            ],
            "value": [
                len(monthly),
                monthly["bond_id"].nunique(),
                monthly["obs_date"].min(),
                monthly["obs_date"].max(),
                int(monthly["exact_date_match"].sum()),
                100.0 * monthly["exact_date_match"].mean(),
                monthly["staleness_days"].mean(),
                monthly["staleness_days"].median(),
                monthly["staleness_days"].max(),
                int(monthly["staleness_days"].le(3).sum()),
                int(monthly["staleness_days"].le(7).sum()),
                int(monthly["staleness_days"].le(30).sum()),
                int(monthly["staleness_days"].gt(30).sum()),
                int(monthly["source_overridden"].fillna(False).sum()),
            ],
        }
    )

    by_bond = (
        monthly.groupby(
            [
                "bond_id",
                "revised_selected_source",
                "revised_security_with_source",
            ],
            dropna=False,
        )
        .agg(
            monthly_obs=("obs_date", "size"),
            first_obs_date=("obs_date", "min"),
            last_obs_date=("obs_date", "max"),
            first_quote_date=("quote_date", "min"),
            last_quote_date=("quote_date", "max"),
            mean_staleness_days=("staleness_days", "mean"),
            median_staleness_days=("staleness_days", "median"),
            max_staleness_days=("staleness_days", "max"),
            exact_date_matches=("exact_date_match", "sum"),
            min_corporate_yield_pct=("corporate_yield_pct", "min"),
            max_corporate_yield_pct=("corporate_yield_pct", "max"),
        )
        .reset_index()
    )

    return summary, by_bond


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Map raw daily revised corporate YLD_YTM_MID observations "
            "to the authoritative monthly real-curve obs_date calendar "
            "using backward as-of matching. No staleness cutoff is applied; "
            "audited invalid quotes are excluded before carry-forward."
        )
    )

    parser.add_argument("--raw-path", type=Path, default=DEFAULT_RAW_YTM)
    parser.add_argument("--curve-path", type=Path, default=DEFAULT_REAL_CURVE)
    parser.add_argument("--panel-path", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT)

    args = parser.parse_args()

    raw, curve_dates, maturity = _read_inputs(
        raw_path=args.raw_path,
        curve_path=args.curve_path,
        panel_path=args.panel_path,
    )

    invalid_quote_audit = (
        raw.loc[
            ~raw["quote_is_valid"],
            [
                "bond_id",
                "DATE",
                "YLD_YTM_MID",
                "quote_invalid_reason",
                "selected_source",
                "security_with_source",
                "revised_selected_source",
                "revised_security_with_source",
                "source_overridden",
                "override_reason",
            ],
        ]
        .sort_values(["bond_id", "DATE"])
        .reset_index(drop=True)
    )


    monthly = build_monthly_asof_panel(
        raw=raw,
        curve_dates=curve_dates,
        maturity=maturity,
    )

    summary, by_bond = build_summary(monthly)

    args.output_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(
        args.output_path,
        engine="openpyxl",
    ) as writer:
        monthly.to_excel(
            writer,
            sheet_name="monthly_asof",
            index=False,
        )
        summary.to_excel(
            writer,
            sheet_name="summary",
            index=False,
        )
        by_bond.to_excel(
            writer,
            sheet_name="by_bond",
            index=False,
        )

        invalid_quote_audit.to_excel(
            writer,
            sheet_name="invalid_quote_audit",
            index=False,
        )

    print("Corporate monthly YTM table created successfully.")
    print(f"Output: {args.output_path.resolve()}")
    print(f"Monthly rows: {len(monthly)}")
    print(f"Unique bonds: {monthly['bond_id'].nunique()}")
    print(
        "Obs-date range: "
        f"{monthly['obs_date'].min().date()} -> "
        f"{monthly['obs_date'].max().date()}"
    )
    print(
        "Staleness days: "
        f"mean={monthly['staleness_days'].mean():.2f}, "
        f"median={monthly['staleness_days'].median():.2f}, "
        f"max={monthly['staleness_days'].max()}"
    )
    print(
        "Exact-date matches: "
        f"{int(monthly['exact_date_match'].sum())} "
        f"({100.0 * monthly['exact_date_match'].mean():.2f}%)"
    )
    print(
        "Rows with staleness > 30 days: "
        f"{int(monthly['staleness_days'].gt(30).sum())}"
    )
    print(
        "Rows using a documented source override: "
        f"{int(monthly['source_overridden'].fillna(False).sum())}"
    )
    print(
        "No staleness cutoff was applied; "
        "audited invalid quotes were excluded before carry-forward."
    )


if __name__ == "__main__":
    main()
