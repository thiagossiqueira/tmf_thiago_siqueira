from __future__ import annotations
import sys

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from calendars.daycounts import DayCounts


# ---------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
# Allow this file to be executed directly as:
# python scripts\build_econometrics_panel.py
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from finmath.termstructure.curve_models import CurveBootstrap, flat_forward_interpolation
from src.config import CONFIG
from src.core.curve_builder import (
    build_real_curve_for_date,
    build_real_curve_for_obs_date,
    load_real_curve_support,
    wla_max_tenor_for_date,
    wla_yield_for_date,
)
from src.core.spread_calculator import (
    compute_spreads,
    compute_spreads_ltn,
    geometric_spread_bps_from_pct,
)
from src.core.windowing import build_observation_windows
from src.utils.file_io import (
    load_corp_bond_data,
    load_corp_ipca_monthly_yields,
    load_di_surface,
    load_govt_bond_data,
    load_ipca_surface,
    load_yield_surface,
)
from src.utils.filters import (
    anomaly_filtering_results,
    filter_corporate_universe,
    filter_government_universe,
)
from src.utils.interpolation import (
    interpolate_di_surface,
    interpolate_raw_di_yield_for_tenor,
    interpolate_surface,
)

ECONOMETRICS_DIR = ROOT / "datos_y_modelos" / "db" / "econometrics_db"
FUNDAMENTALS_DIR = ROOT / "datos_y_modelos" / "db" / "issuers_fundamental_data"
MACRO_DIR = ROOT / "datos_y_modelos" / "db" / "brazil_macroeconomic_data"

PUBLIC_DEBT_GDP_DIR = MACRO_DIR / "public_debt_gdp"

PUBLIC_DEBT_GDP = (
    PUBLIC_DEBT_GDP_DIR
    / "sgs_13762_public_debt_gdp.csv"
)

PUBLIC_DEBT_GDP_README = (
    PUBLIC_DEBT_GDP_DIR
    / "README_SGS_13762.md"
)

DOMESTIC_DIR = ROOT / "datos_y_modelos" / "Domestic"
GOVT_DIR = ROOT / "datos_y_modelos" / "db" / "brazil_domestic_govt_bonds"

LEGACY_PANEL = ECONOMETRICS_DIR / "panel_main_and_robustness.xlsx"

# IMPORTANT:
# Never overwrite the frozen legacy panel during development/reconciliation.
OUTPUT_PANEL = ECONOMETRICS_DIR / "panel_main_and_robustness_rebuilt_v2.xlsx"

BOND_METADATA = DOMESTIC_DIR / "universo_brazil_deb_des.xlsx"
MACRO_WORKBOOK = MACRO_DIR / "macro_explanatory_variables.xlsx"

FED_3M_FORWARD = (
    MACRO_DIR
    / "fed_3m_forward"
    / "ussoc_monthly_2010_2025.csv"
)

GOVT_YAS = GOVT_DIR / "govt_ya_ande.v6.xlsx"

CF_CASH_FROM_OPER = FUNDAMENTALS_DIR / "CF_CASH_FROM_OPER.xlsx"
BS_TOT_ASSET = FUNDAMENTALS_DIR / "BS_TOT_ASSET.xlsx"
SHORT_AND_LONG_TERM_DEBT = FUNDAMENTALS_DIR / "SHORT_AND_LONG_TERM_DEBT.xlsx"
EBITDA = FUNDAMENTALS_DIR / "EBITDA.xlsx"

WLA_CURVE = (
    ROOT
    / "datos_y_modelos"
    / "db"
    / "id_x_ipca_spread_futures"
    / "hist_ipca_curve_contracts_db.xlsx"
)

GOVT_METADATA = (
    DOMESTIC_DIR
    / "domestic_sovereign_curve_brazil.v5.xlsx"
)


LEGACY_TS_COLUMNS = [
    "bond_id",
    "issuer",
    "maturity",
    "bond_type",
    "exchange id",
    "sector",
    "obs_date",
    "month",
    "spread",
    "vix",
    "fed_3m_forward",
    "usd_brl",
    "gdp_yoy",
    "debt_gdp",
    "cf_cash_oper_to_tot_asset",
    "amount_issued_to_bs_tot_asset",
    "tot_debt_to_ebitda",
    "days_to_maturity",
    "synthetic_cds_brl",
]


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def require_file(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"Required input not found: {path}")
    return path


def find_unique(filename: str, search_root: Path = ROOT) -> Path:
    """
    Resolve a canonical file whose filename is already known but whose exact
    subdirectory should not be guessed.

    The build fails if zero or multiple copies exist.
    """
    matches = sorted(
        p for p in search_root.rglob(filename)
        if p.is_file()
    )

    if not matches:
        raise FileNotFoundError(
            f"Could not find required canonical input: {filename}"
        )

    if len(matches) > 1:
        formatted = "\n".join(f"  - {p}" for p in matches)
        raise RuntimeError(
            f"Expected exactly one copy of {filename}, found {len(matches)}:\n"
            f"{formatted}"
        )

    return matches[0]


def find_unique_pattern(pattern: str, search_root: Path = ROOT) -> Path:
    matches = sorted(
        p for p in search_root.rglob(pattern)
        if p.is_file()
    )

    if not matches:
        raise FileNotFoundError(
            f"Could not find required canonical input matching: {pattern}"
        )

    if len(matches) > 1:
        formatted = "\n".join(f"  - {p}" for p in matches)
        raise RuntimeError(
            f"Expected exactly one match for {pattern}, found {len(matches)}:\n"
            f"{formatted}"
        )

    return matches[0]


def inspect_excel(path: Path) -> list[str]:
    require_file(path)
    return pd.ExcelFile(path).sheet_names


# ---------------------------------------------------------------------
# Canonical input registry
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class Inputs:
    legacy_panel: Path
    corporate_monthly: Path
    bond_metadata: Path
    macro_workbook: Path
    fed_3m_forward: Path
    public_debt_gdp: Path
    wla_curve: Path
    govt_metadata: Path
    govt_yas: Path
    cf_cash_from_oper: Path
    bs_tot_asset: Path
    short_and_long_term_debt: Path
    ebitda: Path


def resolve_inputs() -> Inputs:
    return Inputs(
        legacy_panel=require_file(LEGACY_PANEL),

        # Revised corporate pricing series frozen in WP-01.
        # We deliberately resolve the known canonical filename rather
        # than guess its directory.
        corporate_monthly=find_unique(
            "corp_yld_ytm_mid_revised_monthly.v1.xlsx"
        ),

        bond_metadata=require_file(BOND_METADATA),
        macro_workbook=require_file(MACRO_WORKBOOK),

        # Audited thesis baseline U.S. short-rate control:
        # USSOC Curncy / PX_LAST at calendar month-end.
        fed_3m_forward=require_file(FED_3M_FORWARD),

        # SGS 13762 replaced the incorrectly labelled EHBBBR fiscal series.
        # Exact local filename will be locked after this inventory step.
        public_debt_gdp=require_file(
            MACRO_DIR
            / "public_debt_gdp"
            / "sgs_13762_public_debt_gdp.csv"
        ),

        wla_curve=require_file(WLA_CURVE),
        govt_metadata=require_file(GOVT_METADATA),
        govt_yas=require_file(GOVT_YAS),

        cf_cash_from_oper=require_file(CF_CASH_FROM_OPER),
        bs_tot_asset=require_file(BS_TOT_ASSET),
        short_and_long_term_debt=require_file(SHORT_AND_LONG_TERM_DEBT),
        ebitda=require_file(EBITDA),
    )



def validate_real_curve_path_contract(inputs: Inputs) -> None:
    """
    Ensure that the production real-curve helpers, which currently read
    paths from CONFIG, use the same files declared in the builder's
    canonical input registry.
    """

    expected = {
        "WLA_CURVE_PATH": inputs.wla_curve,
        "GOVT_PATH": inputs.govt_metadata,
        "GOVT_YA_PATH": inputs.govt_yas,
    }

    mismatches: list[str] = []

    for config_key, declared_path in expected.items():
        configured_path = Path(CONFIG[config_key]).resolve()
        declared_path = declared_path.resolve()

        if configured_path != declared_path:
            mismatches.append(
                f"{config_key}\n"
                f"  CONFIG : {configured_path}\n"
                f"  builder: {declared_path}"
            )

    if mismatches:
        raise AssertionError(
            "Production real-curve paths differ from the canonical "
            "builder registry:\n\n"
            + "\n\n".join(mismatches)
        )

# ---------------------------------------------------------------------
# Legacy panel contract
# ---------------------------------------------------------------------

def load_legacy_panel(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="ts")

    raw_columns = list(df.columns)
    df.columns = [str(column).strip() for column in df.columns]

    if len(df.columns) != len(set(df.columns)):
        raise AssertionError(
            "Column-name normalization created duplicate headers.\n"
            f"Raw columns: {raw_columns}\n"
            f"Normalized columns: {list(df.columns)}"
        )

    if list(df.columns) != LEGACY_TS_COLUMNS:
        raise AssertionError(
            "Legacy ts schema differs from the frozen 19-column contract.\n"
            f"Expected:\n{LEGACY_TS_COLUMNS}\n\n"
            f"Observed:\n{list(df.columns)}"
        )

    df["bond_id"] = df["bond_id"].astype(str).str.strip()
    df["obs_date"] = pd.to_datetime(df["obs_date"], errors="raise")
    df["maturity"] = pd.to_datetime(df["maturity"], errors="coerce")

    duplicated = df.duplicated(["bond_id", "obs_date"], keep=False)

    if duplicated.any():
        bad = (
            df.loc[duplicated, ["bond_id", "obs_date"]]
            .sort_values(["bond_id", "obs_date"])
        )
        raise AssertionError(
            "Legacy panel contains duplicate bond-month keys:\n"
            f"{bad.to_string(index=False)}"
        )

    return df


def build_bond_month_spine(inputs: Inputs) -> pd.DataFrame:
    """
    Build the canonical candidate bond-month population from the audited
    revised corporate monthly YTM file and canonical bond metadata.

    obs_date:
        Actual same-date corporate/benchmark observation date.

    month:
        Calendar month-end key used for monthly joins.
    """

    monthly = pd.read_excel(
        inputs.corporate_monthly,
        sheet_name="monthly_asof",
        usecols=[
            "bond_id",
            "obs_date",
            "corporate_yield_pct",
            "maturity",
            "days_to_maturity_calendar",
        ],
    )

    monthly.columns = [
        str(column).strip()
        for column in monthly.columns
    ]

    monthly["bond_id"] = (
        monthly["bond_id"]
        .astype(str)
        .str.strip()
    )

    monthly["obs_date"] = pd.to_datetime(
        monthly["obs_date"],
        errors="raise",
    ).dt.normalize()

    monthly["source_maturity"] = pd.to_datetime(
        monthly.pop("maturity"),
        errors="raise",
    ).dt.normalize()

    monthly["corporate_yield_pct"] = pd.to_numeric(
        monthly["corporate_yield_pct"],
        errors="raise",
    )

    monthly["source_days_to_maturity"] = pd.to_numeric(
        monthly.pop("days_to_maturity_calendar"),
        errors="raise",
    ).astype("int64")

    monthly["month"] = (
        monthly["obs_date"]
        .dt.to_period("M")
        .dt.to_timestamp("M")
    )

    duplicate_keys = monthly.duplicated(
        ["bond_id", "month"],
        keep=False,
    )

    if duplicate_keys.any():
        bad = (
            monthly.loc[
                duplicate_keys,
                ["bond_id", "obs_date", "month"],
            ]
            .sort_values(["bond_id", "month"])
        )

        raise AssertionError(
            "Corporate monthly source contains duplicate bond-month keys:\n"
            f"{bad.to_string(index=False)}"
        )

    metadata = pd.read_excel(
        inputs.bond_metadata,
        sheet_name="db_values_only",
        usecols=[
            "id",
            "ISSUER",
            "MATURITY",
            "CPN_TYP",
            "INFLATION_LINKED_INDICATOR",
            "ULT_PARENT_TICKER_EXCHANGE",
            "industry_group",
        ],
    )

    metadata["id"] = (
        metadata["id"]
        .astype(str)
        .str.strip()
    )

    duplicate_metadata = metadata.duplicated(
        "id",
        keep=False,
    )

    if duplicate_metadata.any():
        bad = (
            metadata.loc[duplicate_metadata, ["id"]]
            .sort_values("id")
        )

        raise AssertionError(
            "Bond metadata contains duplicate IDs:\n"
            f"{bad.to_string(index=False)}"
        )

    panel_bond_ids = set(monthly["bond_id"].unique())

    # Filter to the actual panel universe before parsing fields.
    # The full 6,926-security metadata workbook contains Bloomberg
    # placeholder values for securities outside our sample.
    metadata = metadata.loc[
        metadata["id"].isin(panel_bond_ids)
    ].copy()

    metadata["MATURITY"] = pd.to_datetime(
        metadata["MATURITY"],
        errors="raise",
    ).dt.normalize()

    metadata["CPN_TYP"] = (
        metadata["CPN_TYP"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    metadata["INFLATION_LINKED_INDICATOR"] = (
        metadata["INFLATION_LINKED_INDICATOR"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    metadata_bond_ids = set(metadata["id"].unique())
    missing_metadata = sorted(
        panel_bond_ids.difference(metadata_bond_ids)
    )

    if missing_metadata:
        raise AssertionError(
            "Canonical metadata is missing panel bonds:\n"
            + "\n".join(missing_metadata)
        )

    invalid_coupon = metadata.loc[
        metadata["CPN_TYP"] != "FIXED",
        ["id", "CPN_TYP"],
    ]

    if not invalid_coupon.empty:
        raise AssertionError(
            "Panel contains non-fixed-coupon bonds:\n"
            f"{invalid_coupon.to_string(index=False)}"
        )

    invalid_indexation = metadata.loc[
        metadata["INFLATION_LINKED_INDICATOR"] != "Y",
        ["id", "INFLATION_LINKED_INDICATOR"],
    ]

    if not invalid_indexation.empty:
        raise AssertionError(
            "Panel contains bonds not classified as inflation-linked:\n"
            f"{invalid_indexation.to_string(index=False)}"
        )

    metadata = metadata.rename(
        columns={
            "id": "bond_id",
            "ISSUER": "issuer",
            "MATURITY": "maturity",
            "ULT_PARENT_TICKER_EXCHANGE": "exchange id",
            "industry_group": "sector",
        }
    )

    spine = monthly.merge(
        metadata[
            [
                "bond_id",
                "issuer",
                "maturity",
                "exchange id",
                "sector",
            ]
        ],
        on="bond_id",
        how="left",
        validate="many_to_one",
    )

    maturity_mismatch = (
        spine["source_maturity"] != spine["maturity"]
    )

    if maturity_mismatch.any():
        bad = spine.loc[
            maturity_mismatch,
            [
                "bond_id",
                "source_maturity",
                "maturity",
            ],
        ].drop_duplicates()

        raise AssertionError(
            "Corporate source and canonical metadata disagree on maturity:\n"
            f"{bad.to_string(index=False)}"
        )

    calculated_days = (
        spine["maturity"] - spine["obs_date"]
    ).dt.days.astype("int64")

    day_mismatch = (
        calculated_days
        != spine["source_days_to_maturity"]
    )

    if day_mismatch.any():
        bad = spine.loc[
            day_mismatch,
            [
                "bond_id",
                "obs_date",
                "maturity",
                "source_days_to_maturity",
            ],
        ].copy()

        bad["calculated_days_to_maturity"] = (
            calculated_days.loc[day_mismatch]
        )

        raise AssertionError(
            "Days-to-maturity reconciliation failed:\n"
            f"{bad.head(25).to_string(index=False)}"
        )

    spine["bond_type"] = "BRAZIL IPCA+SPREAD"

    # -----------------------------------------------------
    # Econometric residual maturity
    #
    # Despite the legacy column name "days_to_maturity",
    # the thesis regressor is residual maturity in YEARS
    # under the canonical ANBIMA BUS/252 convention.
    #
    # The shared DayCounts implementation uses [start, end)
    # timing. This intentionally differs from the legacy
    # inclusive implementation by 1/252 whenever maturity
    # itself is an ANBIMA business day.
    #
    # The calendar-day calculation above is retained only
    # as a source-integrity check against the revised
    # corporate monthly input.
    # -----------------------------------------------------
    daycount_bus252 = DayCounts(
        "bus/252",
        calendar="cdr_anbima",
    )

    spine["days_to_maturity"] = spine.apply(
        lambda r: daycount_bus252.tf(
            r["obs_date"],
            r["maturity"],
        ),
        axis=1,
    )

    if spine["days_to_maturity"].isna().any():
        bad = spine.loc[
            spine["days_to_maturity"].isna(),
            [
                "bond_id",
                "obs_date",
                "maturity",
            ],
        ]

        raise AssertionError(
            "Missing BUS/252 residual maturity:\n"
            f"{bad.head(25).to_string(index=False)}"
        )

    if (spine["days_to_maturity"] < 0).any():
        bad = spine.loc[
            spine["days_to_maturity"] < 0,
            [
                "bond_id",
                "obs_date",
                "maturity",
                "days_to_maturity",
            ],
        ]

        raise AssertionError(
            "Negative BUS/252 residual maturity:\n"
            f"{bad.head(25).to_string(index=False)}"
        )

    spine = (
        spine.sort_values(["bond_id", "obs_date"])
        .reset_index(drop=True)
    )

    return spine[
        [
            "bond_id",
            "issuer",
            "maturity",
            "bond_type",
            "exchange id",
            "sector",
            "obs_date",
            "month",
            "corporate_yield_pct",
            "days_to_maturity",
        ]
    ]

# ---------------------------------------------------------------------
# Input audit
# ---------------------------------------------------------------------

def build_corporate_spread(inputs: Inputs) -> tuple[pd.DataFrame, list]:
    """
    Rebuild the corporate IPCA spread from canonical upstream inputs
    using the current production methodology shared with main.py.

    Returns
    -------
    spreads
        bond_id, obs_date, spread
    skipped
        Observations rejected by compute_spreads(), with reasons.
    """

    yields_ts = load_corp_ipca_monthly_yields(
        inputs.corporate_monthly
    )

    corp_base = load_corp_bond_data(
        inputs.bond_metadata
    )

    corp_base = corp_base[
        corp_base["id"].isin(yields_ts.columns)
    ].copy()

    corp_base = filter_corporate_universe(
        corp_base,
        inflation_linked="Y",
    )

    observation_windows = build_observation_windows(
        corp_base,
        yields_ts,
        CONFIG["OBS_WINDOW"],
    )

    ntnb_meta_df, ntnb_ya_df = load_real_curve_support()

    wla_dates = pd.DatetimeIndex(
        load_ipca_surface(inputs.wla_curve)["obs_date"].unique()
    )

    common_dates = (
        yields_ts.index
        .intersection(ntnb_ya_df.index)
        .intersection(wla_dates)
    )

    surface_list = []
    real_curve_cache = {}

    for obs_date in common_dates:
        if obs_date not in real_curve_cache:
            real_curve_cache[obs_date] = (
                build_real_curve_for_obs_date(
                    obs_date,
                    ntnb_meta_df,
                    ntnb_ya_df,
                )
            )

        real_curve = real_curve_cache[obs_date]

        # Same fallback used by main.py when the NTN-B NSS
        # cross-section is underidentified.
        if real_curve is None:
            max_wla_tenor = wla_max_tenor_for_date(
                obs_date
            )

            if pd.isna(max_wla_tenor):
                continue

            for label, tenor in CONFIG[
                "REAL_CURVE_TENORS"
            ].items():
                tenor = float(tenor)

                if tenor > max_wla_tenor:
                    continue

                surface_list.append(
                    {
                        "obs_date": obs_date,
                        "generic_ticker_id": label,
                        "yield": wla_yield_for_date(
                            obs_date,
                            tenor,
                        ),
                        "tenor": tenor,
                    }
                )

            continue

        for label, tenor in CONFIG[
            "REAL_CURVE_TENORS"
        ].items():
            surface_list.append(
                {
                    "obs_date": obs_date,
                    "generic_ticker_id": label,
                    "yield": real_curve.yield_at(
                        float(tenor)
                    ),
                    "tenor": float(tenor),
                }
            )

    surface = pd.DataFrame(surface_list)

    if surface.empty:
        raise AssertionError(
            "Corporate IPCA real-curve surface is empty."
        )

    yc_table = interpolate_surface(
        surface,
        CONFIG["REAL_CURVE_TENORS"],
    )

    corp_bonds, skipped = compute_spreads(
        corp_base,
        yields_ts,
        yc_table,
        observation_windows,
        CONFIG["REAL_CURVE_TENORS"],
        build_real_curve_for_date=build_real_curve_for_date,
        ntnb_meta_df=ntnb_meta_df,
        ntnb_ya_df=ntnb_ya_df,
        wla_yield_func_for_date=wla_yield_for_date,
        wla_max_tenor_func_for_date=wla_max_tenor_for_date,
        allow_curve_extrapolation=False,
        real_curve_cache=real_curve_cache,
    )

    spreads = corp_bonds[
        [
            "id",
            "OBS_DATE",
            "SPREAD",
        ]
    ].copy()

    spreads = spreads.rename(
        columns={
            "id": "bond_id",
            "OBS_DATE": "obs_date",
            "SPREAD": "spread",
        }
    )

    spreads["bond_id"] = (
        spreads["bond_id"]
        .astype(str)
        .str.strip()
    )

    spreads["obs_date"] = pd.to_datetime(
        spreads["obs_date"],
        errors="raise",
    ).dt.normalize()

    duplicate_keys = spreads.duplicated(
        ["bond_id", "obs_date"],
        keep=False,
    )

    if duplicate_keys.any():
        bad = spreads.loc[
            duplicate_keys,
            ["bond_id", "obs_date"],
        ]

        raise AssertionError(
            "Rebuilt corporate spread contains duplicate keys:\n"
            f"{bad.to_string(index=False)}"
        )

    if spreads["spread"].isna().any():
        raise AssertionError(
            "Rebuilt corporate spread contains missing spreads."
        )

    return (
        spreads
        .sort_values(["bond_id", "obs_date"])
        .reset_index(drop=True),
        skipped,
    )

def build_macro_controls(
    inputs: Inputs,
    required_months: pd.Series,
) -> pd.DataFrame:
    """
    Build the frozen baseline monthly macro controls:

      vix
          VIX Index from macro_explanatory_variables.xlsx.

      fed_3m_forward
          USSOC Curncy / PX_LAST from the audited monthly CSV.

      usd_brl
          USDBRL Curncy from macro_explanatory_variables.xlsx.

      gdp_yoy
          BZGDYOY% Index. The workbook stores the quarterly
          observation in the release/quarter month and zero
          placeholders in intervening months; the last valid
          quarterly observation is carried forward.
    """

    macro = pd.read_excel(
        inputs.macro_workbook,
        sheet_name="values_only",
    )

    date_col = macro.columns[0]

    vix_col = "Global Risk Aversion (Volatility Index)"
    usd_brl_col = (
        "USDBRL Spot Exchange Rate - Price of 1 USD in BRL"
    )
    gdp_col = "Real GDP (yoy %)"

    required_columns = {
        date_col,
        vix_col,
        usd_brl_col,
        gdp_col,
    }

    missing_columns = required_columns.difference(
        macro.columns
    )

    if missing_columns:
        raise AssertionError(
            "Macro workbook is missing required columns: "
            f"{sorted(missing_columns)}"
        )

    source = macro[
        [
            date_col,
            vix_col,
            usd_brl_col,
            gdp_col,
        ]
    ].copy()

    source.columns = [
        "source_date",
        "vix",
        "usd_brl",
        "gdp_raw",
    ]

    # First workbook row contains Bloomberg ticker labels rather
    # than observations. Date coercion deliberately removes it.
    source["source_date"] = pd.to_datetime(
        source["source_date"],
        errors="coerce",
    )

    for column in [
        "vix",
        "usd_brl",
        "gdp_raw",
    ]:
        source[column] = pd.to_numeric(
            source[column],
            errors="coerce",
        )

    source = source[
        source["source_date"].notna()
    ].copy()

    source["month"] = (
        source["source_date"]
        .dt.to_period("M")
        .dt.to_timestamp("M")
    )

    duplicate_macro_months = source.duplicated(
        ["month"],
        keep=False,
    )

    if duplicate_macro_months.any():
        bad = source.loc[
            duplicate_macro_months,
            ["month", "source_date"],
        ]

        raise AssertionError(
            "Macro workbook contains duplicate month keys:\n"
            f"{bad.to_string(index=False)}"
        )

    if source[
        ["vix", "usd_brl", "gdp_raw"]
    ].isna().any().any():
        raise AssertionError(
            "Macro workbook contains missing/non-numeric values "
            "after removing its ticker-label row."
        )

    # Audited GDP convention:
    # zero is a non-release placeholder in this Bloomberg monthly
    # workbook. Carry the latest quarterly YoY observation through
    # the intervening months.
    source["gdp_yoy"] = (
        source["gdp_raw"]
        .mask(source["gdp_raw"].eq(0))
        .ffill()
    )

    macro_monthly = source[
        [
            "month",
            "vix",
            "usd_brl",
            "gdp_yoy",
        ]
    ].copy()

    # -------------------------------------------------------------
    # Fed 3M Forward: audited USSOC Curncy / PX_LAST monthly source
    # -------------------------------------------------------------
    fed = pd.read_csv(
        inputs.fed_3m_forward
    )

    fed_required = {
        "ID",
        "calendar_month_end",
        "ussoc_px_last",
    }

    fed_missing = fed_required.difference(
        fed.columns
    )

    if fed_missing:
        raise AssertionError(
            "Fed 3M Forward source is missing required columns: "
            f"{sorted(fed_missing)}"
        )

    fed["ID"] = (
        fed["ID"]
        .astype(str)
        .str.strip()
    )

    unexpected_ids = sorted(
        set(fed["ID"].dropna())
        - {"USSOC Curncy"}
    )

    if unexpected_ids:
        raise AssertionError(
            "Unexpected securities in Fed 3M Forward source: "
            f"{unexpected_ids}"
        )

    fed["month"] = pd.to_datetime(
        fed["calendar_month_end"],
        errors="raise",
    ).dt.normalize()

    fed["fed_3m_forward"] = pd.to_numeric(
        fed["ussoc_px_last"],
        errors="raise",
    )

    if fed["fed_3m_forward"].isna().any():
        raise AssertionError(
            "Fed 3M Forward source contains missing values."
        )

    duplicate_fed_months = fed.duplicated(
        ["month"],
        keep=False,
    )

    if duplicate_fed_months.any():
        bad = fed.loc[
            duplicate_fed_months,
            ["month", "fed_3m_forward"],
        ]

        raise AssertionError(
            "Fed 3M Forward source contains duplicate months:\n"
            f"{bad.to_string(index=False)}"
        )

    fed_monthly = fed[
        [
            "month",
            "fed_3m_forward",
        ]
    ].copy()

    # -------------------------------------------------------------
    # Restrict to the canonical bond-month spine
    # -------------------------------------------------------------
    required = pd.DataFrame(
        {
            "month": pd.to_datetime(
                required_months,
                errors="raise",
            )
        }
    )

    required["month"] = (
        required["month"]
        .dt.to_period("M")
        .dt.to_timestamp("M")
    )

    required = (
        required
        .drop_duplicates()
        .sort_values("month")
        .reset_index(drop=True)
    )

    controls = required.merge(
        macro_monthly,
        on="month",
        how="left",
        validate="one_to_one",
    )

    controls = controls.merge(
        fed_monthly,
        on="month",
        how="left",
        validate="one_to_one",
    )

    controls = controls[
        [
            "month",
            "vix",
            "fed_3m_forward",
            "usd_brl",
            "gdp_yoy",
        ]
    ]

    missing = controls[
        [
            "vix",
            "fed_3m_forward",
            "usd_brl",
            "gdp_yoy",
        ]
    ].isna()

    if missing.any().any():
        bad = controls.loc[
            missing.any(axis=1)
        ]

        raise AssertionError(
            "Baseline macro controls are incomplete on canonical "
            "panel months:\n"
            f"{bad.to_string(index=False)}"
        )

    if controls.duplicated(["month"]).any():
        raise AssertionError(
            "Rebuilt macro controls contain duplicate month keys."
        )

    return (
        controls
        .sort_values("month")
        .reset_index(drop=True)
    )


def build_public_debt_gdp(
    inputs: Inputs,
    required_months: pd.Series,
) -> pd.DataFrame:
    """
    Build the baseline Brazilian public-debt control from
    BCB/SGS series 13762:

        Gross General Government Debt (% GDP)

    The canonical SGS file is monthly. Under the frozen Data Freeze
    timing convention, panel month t uses SGS reference month t-2.
    No interpolation or carry-forward transformation is applied.
    """

    raw = pd.read_csv(
        inputs.public_debt_gdp,
        sep=";",
        encoding="cp1252",
        dtype=str,
    )

    if raw.shape[1] != 2:
        raise AssertionError(
            "SGS 13762 source should contain exactly two columns; "
            f"found {raw.shape[1]}."
        )

    date_col = raw.columns[0]
    value_col = raw.columns[1]

    if "13762" not in str(value_col):
        raise AssertionError(
            "Public-debt source does not appear to be SGS 13762: "
            f"{value_col}"
        )

    # SGS export includes a final source/footer row
    # ("Fonte;BCB-DSTAT"). Keep only MM/YYYY observations.
    monthly = raw[
        raw[date_col]
        .astype(str)
        .str.fullmatch(r"\d{2}/\d{4}")
    ].copy()

    monthly["month"] = (
        pd.to_datetime(
            monthly[date_col],
            format="%m/%Y",
            errors="raise",
        )
        .dt.to_period("M")
        .dt.to_timestamp("M")
    )

    monthly["debt_gdp"] = pd.to_numeric(
        monthly[value_col]
        .str.replace(",", ".", regex=False)
        .str.strip(),
        errors="raise",
    )

    monthly = (
        monthly[
            [
                "month",
                "debt_gdp",
            ]
        ]
        .sort_values("month")
        .reset_index(drop=True)
    )

    if monthly.duplicated(["month"]).any():
        bad = monthly.loc[
            monthly.duplicated(
                ["month"],
                keep=False,
            )
        ]

        raise AssertionError(
            "SGS 13762 contains duplicate month keys:\n"
            f"{bad.to_string(index=False)}"
        )

    if monthly["debt_gdp"].isna().any():
        raise AssertionError(
            "SGS 13762 contains missing debt/GDP values."
        )

    # Validate that the SGS history itself is monthly without gaps.
    expected_source_months = pd.date_range(
        monthly["month"].min(),
        monthly["month"].max(),
        freq="ME",
    )

    missing_source_months = (
        expected_source_months.difference(
            pd.DatetimeIndex(monthly["month"])
        )
    )

    if len(missing_source_months):
        raise AssertionError(
            "SGS 13762 contains gaps in its monthly history: "
            f"{missing_source_months.tolist()}"
        )

    required = pd.DataFrame(
        {
            "month": pd.to_datetime(
                required_months,
                errors="raise",
            )
        }
    )

    required["month"] = (
        required["month"]
        .dt.to_period("M")
        .dt.to_timestamp("M")
    )

    required = (
        required
        .drop_duplicates()
        .sort_values("month")
        .reset_index(drop=True)
    )

    # Frozen Data Freeze convention:
    # use SGS 13762 with a uniform two-month reference lag.
    #
    # Example:
    # panel month 2010-12-31 -> SGS reference month 2010-10-31
    monthly_l2 = monthly.copy()
    monthly_l2["month"] = (
        monthly_l2["month"]
        + pd.offsets.MonthEnd(2)
    )

    debt = required.merge(
        monthly_l2,
        on="month",
        how="left",
        validate="one_to_one",
    )

    if debt["debt_gdp"].isna().any():
        bad = debt.loc[
            debt["debt_gdp"].isna(),
            ["month"],
        ]

        raise AssertionError(
            "SGS 13762 does not cover all canonical panel months:\n"
            f"{bad.to_string(index=False)}"
        )

    return debt


def _load_quarterly_fundamental(
    path: Path,
    required_parents: set[str],
) -> dict[tuple[str, pd.Period], float]:
    """
    Read one Bloomberg quarterly fundamental workbook.

    Returns:
        (parent ticker, fiscal quarter) -> numeric value
    """

    df = pd.read_excel(
        path,
        sheet_name="value_only",
    )

    year = pd.to_numeric(
        df.iloc[1:, 0],
        errors="coerce",
    )

    quarter = (
        df.iloc[1:, 1]
        .astype(str)
        .str.strip()
    )

    valid = (
        year.notna()
        & quarter.isin(
            ["Q1", "Q2", "Q3", "Q4"]
        )
    )

    rows = df.iloc[1:, :].loc[valid].copy()

    periods = pd.PeriodIndex(
        year.loc[valid]
        .astype(int)
        .astype(str)
        + quarter.loc[valid],
        freq="Q",
    )

    normalized_columns: dict[str, list[str]] = {}

    for col in df.columns[2:]:
        parent = (
            str(col)
            .replace(" Equity", "")
            .strip()
        )

        normalized_columns.setdefault(
            parent,
            [],
        ).append(col)

    missing_parents = sorted(
        required_parents
        - set(normalized_columns)
    )

    if missing_parents:
        raise AssertionError(
            "Fundamental workbook is missing required "
            f"parent tickers: {missing_parents}"
        )

    result: dict[
        tuple[str, pd.Period],
        float,
    ] = {}

    for parent in sorted(required_parents):
        cols = normalized_columns[parent]

        if len(cols) != 1:
            raise AssertionError(
                "Expected exactly one fundamental column "
                f"for {parent}; found {cols}"
            )

        values = pd.to_numeric(
            rows[cols[0]],
            errors="coerce",
        ).to_numpy()

        for fiscal_quarter, value in zip(
            periods,
            values,
        ):
            result[
                (
                    parent,
                    fiscal_quarter,
                )
            ] = value

    return result


def build_accounting_controls(
    inputs: Inputs,
    spine: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build the two issuer accounting controls using the
    frozen observation-date timing convention.

    Controls
    --------
    cf_cash_oper_to_tot_asset
        1000 * CF_CASH_FROM_OPER / BS_TOT_ASSET
        Units: per mille.

    tot_debt_to_ebitda
        SHORT_AND_LONG_TERM_DEBT / EBITDA
        Units: x-times.

    Timing
    ------
    For each exact corporate obs_date:

    1. Determine the latest fiscal quarter whose calendar
       quarter-end has occurred by obs_date.

    2. Use that quarter only when CFO, assets, debt and
       EBITDA are jointly numeric.

    3. Otherwise permit one-quarter fallback.

    4. A second-quarter fallback is permitted only when
       BOTH more-recent candidate quarters have all four
       fields jointly absent. In the frozen canonical
       sample this occurs exactly once:
       IVPR3B BZ, obs_date 2025-06-30, using 2024Q4.

    The selected fiscal quarter is shared by both ratios,
    preventing cross-variable accounting-date mismatch.
    """

    required_columns = {
        "bond_id",
        "obs_date",
        "exchange id",
    }

    missing_columns = (
        required_columns
        - set(spine.columns)
    )

    if missing_columns:
        raise AssertionError(
            "Accounting-control builder requires spine "
            f"columns: {sorted(missing_columns)}"
        )

    base = spine[
        [
            "bond_id",
            "obs_date",
            "exchange id",
        ]
    ].copy()

    base["bond_id"] = (
        base["bond_id"]
        .astype(str)
        .str.strip()
    )

    base["obs_date"] = pd.to_datetime(
        base["obs_date"],
        errors="raise",
    ).dt.normalize()

    base["accounting_parent"] = (
        base["exchange id"]
        .astype(str)
        .str.strip()
    )

    required_parents = set(
        base["accounting_parent"]
        .dropna()
        .unique()
    )

    sources = {
        "cfo": _load_quarterly_fundamental(
            inputs.cf_cash_from_oper,
            required_parents,
        ),
        "assets": _load_quarterly_fundamental(
            inputs.bs_tot_asset,
            required_parents,
        ),
        "debt": _load_quarterly_fundamental(
            inputs.short_and_long_term_debt,
            required_parents,
        ),
        "ebitda": _load_quarterly_fundamental(
            inputs.ebitda,
            required_parents,
        ),
    }

    issuer_dates = (
        base[
            [
                "accounting_parent",
                "obs_date",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            [
                "obs_date",
                "accounting_parent",
            ]
        )
        .reset_index(drop=True)
    )

    records = []

    for row in issuer_dates.itertuples(
        index=False
    ):
        parent = row.accounting_parent
        obs_date = row.obs_date

        current_q = obs_date.to_period("Q")

        if (
            current_q.end_time.normalize()
            <= obs_date
        ):
            primary_q = current_q
        else:
            primary_q = current_q - 1

        candidates = []

        for fallback in [0, 1, 2]:
            fiscal_quarter = (
                primary_q - fallback
            )

            values = {
                name: source.get(
                    (
                        parent,
                        fiscal_quarter,
                    ),
                    float("nan"),
                )
                for name, source
                in sources.items()
            }

            all_numeric = all(
                pd.notna(value)
                for value
                in values.values()
            )

            usable = (
                all_numeric
                and values["assets"] != 0
                and values["ebitda"] != 0
            )

            candidates.append(
                {
                    "fallback": fallback,
                    "fiscal_quarter":
                        fiscal_quarter,
                    "values": values,
                    "usable": usable,
                    "all_missing": all(
                        pd.isna(value)
                        for value
                        in values.values()
                    ),
                }
            )

        selected = None

        # Normal rule: primary quarter, then one-quarter
        # fallback.
        for candidate in candidates[:2]:
            if candidate["usable"]:
                selected = candidate
                break

        # Narrow frozen-sample extension:
        # two-quarter fallback is allowed only when BOTH
        # more-recent quarters have all four fields absent.
        if (
            selected is None
            and candidates[0]["all_missing"]
            and candidates[1]["all_missing"]
            and candidates[2]["usable"]
        ):
            selected = candidates[2]

        if selected is None:
            diagnostic = [
                {
                    "quarter": str(
                        candidate[
                            "fiscal_quarter"
                        ]
                    ),
                    "fallback":
                        candidate["fallback"],
                    **candidate["values"],
                }
                for candidate in candidates
            ]

            raise AssertionError(
                "No valid jointly complete accounting "
                "quarter for "
                f"{parent} at {obs_date.date()}:\n"
                f"{diagnostic}"
            )

        values = selected["values"]

        records.append(
            {
                "accounting_parent":
                    parent,
                "obs_date":
                    obs_date,
                "accounting_primary_quarter":
                    str(primary_q),
                "accounting_source_quarter":
                    str(
                        selected[
                            "fiscal_quarter"
                        ]
                    ),
                "accounting_fallback_quarters":
                    int(
                        selected["fallback"]
                    ),
                "accounting_cfo":
                    float(values["cfo"]),
                "accounting_bs_tot_asset":
                    float(values["assets"]),
                "accounting_debt":
                    float(values["debt"]),
                "accounting_ebitda":
                    float(values["ebitda"]),
                "cf_cash_oper_to_tot_asset":
                    (
                        1000.0
                        * float(values["cfo"])
                        / float(values["assets"])
                    ),
                "tot_debt_to_ebitda":
                    (
                        float(values["debt"])
                        / float(values["ebitda"])
                    ),
            }
        )

    issuer_controls = pd.DataFrame(
        records
    )

    if issuer_controls.duplicated(
        [
            "accounting_parent",
            "obs_date",
        ]
    ).any():
        raise AssertionError(
            "Accounting controls contain duplicate "
            "issuer-date keys."
        )

    # Freeze guard for the sole two-quarter exception.
    two_q = issuer_controls.loc[
        issuer_controls[
            "accounting_fallback_quarters"
        ].eq(2)
    ]

    expected_two_q = (
        len(two_q) == 1
        and two_q.iloc[0][
            "accounting_parent"
        ] == "IVPR3B BZ"
        and two_q.iloc[0][
            "obs_date"
        ] == pd.Timestamp("2025-06-30")
        and two_q.iloc[0][
            "accounting_source_quarter"
        ] == "2024Q4"
    )

    if not expected_two_q:
        raise AssertionError(
            "Unexpected two-quarter accounting fallback "
            "pattern. Frozen expectation is exactly "
            "IVPR3B BZ / 2025-06-30 / 2024Q4."
        )

    controls = base.merge(
        issuer_controls,
        on=[
            "accounting_parent",
            "obs_date",
        ],
        how="left",
        validate="many_to_one",
    )

    if controls.duplicated(
        [
            "bond_id",
            "obs_date",
        ]
    ).any():
        raise AssertionError(
            "Accounting controls contain duplicate "
            "bond-date keys."
        )

    required_values = [
        "cf_cash_oper_to_tot_asset",
        "tot_debt_to_ebitda",
        "accounting_bs_tot_asset",
    ]

    if controls[
        required_values
    ].isna().any().any():
        bad = controls.loc[
            controls[
                required_values
            ].isna().any(axis=1),
            [
                "bond_id",
                "accounting_parent",
                "obs_date",
            ],
        ]

        raise AssertionError(
            "Accounting controls are incomplete:\n"
            f"{bad.to_string(index=False)}"
        )

    return controls[
        [
            "bond_id",
            "obs_date",
            "accounting_parent",
            "accounting_primary_quarter",
            "accounting_source_quarter",
            "accounting_fallback_quarters",
            "accounting_cfo",
            "accounting_bs_tot_asset",
            "accounting_debt",
            "accounting_ebitda",
            "cf_cash_oper_to_tot_asset",
            "tot_debt_to_ebitda",
        ]
    ].copy()


def build_relative_issue_size(
    inputs: Inputs,
    spine: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build the baseline relative issue-size control:

        amount_issued_to_bs_tot_asset
        = ((AMT_ISSUED / 1e6) / BS_TOT_ASSET) * 1000

    Units are per mille.

    Frozen baseline timing:
      - use BS_TOT_ASSET from the same calendar quarter;
      - if unavailable, use q-1;
      - if still unavailable, use q-2 only.

    This fallback only fills source gaps. It does not replace
    the separately documented one-quarter-lagged denominator
    robustness specification.
    """

    required_columns = {
        "bond_id",
        "obs_date",
        "exchange id",
    }

    missing_columns = (
        required_columns - set(spine.columns)
    )

    if missing_columns:
        raise AssertionError(
            "Relative issue-size builder requires spine "
            f"columns: {sorted(missing_columns)}"
        )

    meta = pd.read_excel(
        inputs.bond_metadata,
        sheet_name="db_values_only",
        usecols=[
            "ID",
            "ULT_PARENT_TICKER_EXCHANGE",
            "AMT_ISSUED",
        ],
    )

    meta["ID"] = (
        meta["ID"]
        .astype(str)
        .str.strip()
    )

    meta["issue_size_parent"] = (
        meta["ULT_PARENT_TICKER_EXCHANGE"]
        .astype(str)
        .str.strip()
    )

    meta["amount_issued"] = pd.to_numeric(
        meta["AMT_ISSUED"],
        errors="coerce",
    )

    if meta["ID"].duplicated().any():
        bad = meta.loc[
            meta["ID"].duplicated(keep=False),
            ["ID"],
        ]

        raise AssertionError(
            "Duplicate bond IDs in issue-size metadata:\n"
            f"{bad.to_string(index=False)}"
        )

    base = spine[
        [
            "bond_id",
            "obs_date",
            "exchange id",
        ]
    ].copy()

    base["bond_id"] = (
        base["bond_id"]
        .astype(str)
        .str.strip()
    )

    base["obs_date"] = pd.to_datetime(
        base["obs_date"],
        errors="raise",
    ).dt.normalize()

    base = base.merge(
        meta[
            [
                "ID",
                "issue_size_parent",
                "amount_issued",
            ]
        ],
        left_on="bond_id",
        right_on="ID",
        how="left",
        validate="many_to_one",
    )

    if base["amount_issued"].isna().any():
        bad = base.loc[
            base["amount_issued"].isna(),
            ["bond_id"],
        ].drop_duplicates()

        raise AssertionError(
            "Missing AMT_ISSUED for canonical bonds:\n"
            f"{bad.to_string(index=False)}"
        )

    required_parents = set(
        base["issue_size_parent"]
        .dropna()
        .unique()
    )

    assets = _load_quarterly_fundamental(
        inputs.bs_tot_asset,
        required_parents,
    )

    records = []

    for row in base.itertuples(index=False):

        primary_q = row.obs_date.to_period("Q")

        selected_q = None
        selected_assets = float("nan")
        fallback = None

        for lag in [0, 1, 2]:

            q = primary_q - lag

            value = assets.get(
                (
                    row.issue_size_parent,
                    q,
                ),
                float("nan"),
            )

            if (
                pd.notna(value)
                and value != 0
            ):
                selected_q = q
                selected_assets = float(value)
                fallback = lag
                break

        if selected_q is None:
            raise AssertionError(
                "No BS_TOT_ASSET within q/q-1/q-2 "
                f"for {row.bond_id} / "
                f"{row.issue_size_parent} / "
                f"{row.obs_date.date()}."
            )

        ratio = (
            (
                float(row.amount_issued)
                / 1_000_000.0
            )
            / selected_assets
            * 1000.0
        )

        records.append(
            {
                "bond_id":
                    row.bond_id,
                "obs_date":
                    row.obs_date,
                "issue_size_parent":
                    row.issue_size_parent,
                "amount_issued":
                    float(row.amount_issued),
                "issue_size_primary_quarter":
                    str(primary_q),
                "issue_size_source_quarter":
                    str(selected_q),
                "issue_size_fallback_quarters":
                    int(fallback),
                "issue_size_bs_tot_asset":
                    selected_assets,
                "amount_issued_to_bs_tot_asset":
                    ratio,
            }
        )

    result = pd.DataFrame(records)

    if result.duplicated(
        [
            "bond_id",
            "obs_date",
        ]
    ).any():
        raise AssertionError(
            "Relative issue-size output contains "
            "duplicate bond-date keys."
        )

    if result[
        "amount_issued_to_bs_tot_asset"
    ].isna().any():
        raise AssertionError(
            "Relative issue-size output contains "
            "missing final ratios."
        )

    # Frozen revised-sample coverage guards.
    fallback_counts = (
        result[
            "issue_size_fallback_quarters"
        ]
        .value_counts()
        .to_dict()
    )

    expected_counts = {
        0: 4602,
        1: 35,
        2: 11,
    }

    if fallback_counts != expected_counts:
        raise AssertionError(
            "Unexpected relative issue-size fallback "
            f"counts: {fallback_counts}; "
            f"expected {expected_counts}."
        )

    two_q = (
        result.loc[
            result[
                "issue_size_fallback_quarters"
            ].eq(2),
            [
                "issue_size_parent",
                "issue_size_primary_quarter",
                "issue_size_source_quarter",
            ],
        ]
        .drop_duplicates()
    )

    expected_two_q = pd.DataFrame(
        {
            "issue_size_parent": [
                "IVPR3B BZ"
            ],
            "issue_size_primary_quarter": [
                "2025Q2"
            ],
            "issue_size_source_quarter": [
                "2024Q4"
            ],
        }
    )

    if not (
        len(two_q) == 1
        and two_q.reset_index(drop=True)
        .equals(expected_two_q)
    ):
        raise AssertionError(
            "Unexpected two-quarter issue-size "
            "fallback pattern:\n"
            f"{two_q.to_string(index=False)}"
        )

    within = (
        result.groupby("bond_id")[
            "amount_issued_to_bs_tot_asset"
        ]
        .nunique(dropna=True)
    )

    if int((within > 1).sum()) != 98:
        raise AssertionError(
            "Relative issue-size within-bond "
            "variation changed unexpectedly: "
            f"{int((within > 1).sum())} varying bonds."
        )

    return result


def validate_corporate_spread_against_spine(
    spine: pd.DataFrame,
    spreads: pd.DataFrame,
) -> None:
    """
    Require a one-to-one key match between the canonical bond-month
    spine and the rebuilt corporate IPCA spread.
    """

    spine_keys = spine[
        ["bond_id", "obs_date"]
    ].copy()

    spread_keys = spreads[
        ["bond_id", "obs_date"]
    ].copy()

    reconciliation = spine_keys.merge(
        spread_keys,
        on=["bond_id", "obs_date"],
        how="outer",
        indicator=True,
        validate="one_to_one",
    )

    unmatched = reconciliation[
        reconciliation["_merge"] != "both"
    ]

    if not unmatched.empty:
        raise AssertionError(
            "Corporate spread keys do not match the canonical "
            "bond-month spine:\n"
            f"{unmatched.to_string(index=False)}"
        )

    if len(spreads) != len(spine):
        raise AssertionError(
            "Corporate spread row count differs from canonical spine: "
            f"{len(spreads):,} vs {len(spine):,}."
        )


def print_input_audit(inputs: Inputs, legacy: pd.DataFrame) -> None:
    print("=" * 78)
    print("ECONOMETRICS PANEL BUILDER - INPUT AUDIT")
    print("=" * 78)

    print("\nProject root:")
    print(f"  {ROOT}")

    print("\nOutput policy:")
    print(f"  Legacy panel     : {inputs.legacy_panel}")
    print(f"  Validation output: {OUTPUT_PANEL}")
    print("  Legacy overwrite : NO")

    print("\nResolved canonical inputs:")
    for field_name, path in vars(inputs).items():
        print(f"  {field_name:28s} -> {path}")

    print("\nExcel sheets:")
    for field_name, path in vars(inputs).items():
        if path.suffix.lower() in {".xlsx", ".xls"}:
            print(f"  {field_name:28s} -> {inspect_excel(path)}")

    print("\nLegacy panel:")
    print(f"  rows             : {len(legacy):,}")
    print(f"  columns          : {len(legacy.columns)}")
    print(f"  bonds            : {legacy['bond_id'].nunique():,}")
    print(f"  issuers          : {legacy['issuer'].nunique():,}")
    print(f"  first obs_date   : {legacy['obs_date'].min().date()}")
    print(f"  last obs_date    : {legacy['obs_date'].max().date()}")
    print(
        "  unique bond-month: "
        f"{legacy[['bond_id', 'obs_date']].drop_duplicates().shape[0]:,}"
    )

    print("\nLegacy variable non-null counts:")
    for col in LEGACY_TS_COLUMNS:
        print(f"  {col:32s} {legacy[col].notna().sum():>6,}")

    print("\nStatus:")
    print("  PASS - canonical input registry resolved")
    print("  PASS - legacy ts schema validated")
    print("  PASS - legacy panel left untouched")
    print("  NEXT - map each canonical source into deterministic builder functions")
    print("=" * 78)



# ---------------------------------------------------------------------
# Sovereign spread BRL
# ---------------------------------------------------------------------

def build_sovereign_spread(
    inputs: Inputs,
    spine: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build the nominal BRL sovereign zero curve from LTN and NTN-F
    securities and map the sovereign-vs-DI spread to each corporate
    bond-date observation at its exact BUS/252 residual tenor.

    LTNs are direct zero-coupon anchors. Multi-cash-flow NTN-Fs extend
    the sovereign zero curve by cash-flow stripping. An NTN-F with only
    one remaining cash flow is retained as a zero node only when no LTN
    exists at the same BUS/252 tenor.

    Sovereign zero and DI zero yields are interpolated separately at
    the corporate residual tenor. The final spread is geometric.
    """

    dc = DayCounts(
        "bus/252",
        calendar="cdr_anbima",
    )

    govt_base_raw = load_govt_bond_data(
        inputs.govt_metadata
    ).copy()

    yields_ts = load_yield_surface(
        inputs.govt_yas
    ).copy()

    di_surface = load_di_surface(
        CONFIG["HIST_CURVE_PATH"]
    )

    yields_ts.index = pd.to_datetime(
        yields_ts.index,
        errors="raise",
    ).normalize()

    if yields_ts.index.duplicated().any():
        raise AssertionError(
            "Duplicate observation dates in sovereign YAS surface."
        )

    for column in ["ISSUE_DT", "MATURITY"]:
        govt_base_raw[column] = pd.to_datetime(
            govt_base_raw[column],
            errors="coerce",
        )

    eligible_ids = set(yields_ts.columns)

    govt_base_raw = govt_base_raw[
        govt_base_raw["id"].isin(eligible_ids)
    ].copy()

    ltn_base = filter_government_universe(
        govt_base_raw.copy(),
        inflation_linked="N",
        bond_type="LTN",
    ).copy()

    ntnf_base = filter_government_universe(
        govt_base_raw.copy(),
        inflation_linked="N",
        bond_type="NTNF",
    ).copy()

    ltn_base["TYPE"] = "LTN"
    ntnf_base["TYPE"] = "NTNF"

    nominal_base = pd.concat(
        [ltn_base, ntnf_base],
        ignore_index=True,
    )

    required = {
        "id",
        "TYPE",
        "ISSUE_DT",
        "MATURITY",
        "CPN",
        "CPN_FREQ",
    }

    missing = required.difference(
        nominal_base.columns
    )

    if missing:
        raise AssertionError(
            "Missing sovereign metadata fields: "
            f"{sorted(missing)}"
        )

    nominal_base = nominal_base[
        nominal_base["ISSUE_DT"].notna()
        & nominal_base["MATURITY"].notna()
    ].copy()

    nominal_base = nominal_base.sort_values(
        ["MATURITY", "TYPE", "id"]
    ).reset_index(drop=True)

    spine_dates = sorted(
        pd.to_datetime(
            spine["obs_date"],
            errors="raise",
        )
        .dt.normalize()
        .unique()
    )

    curves = {}
    curve_stats = {}

    raw_valid_points = 0
    used_bootstrap_inputs = 0
    kept_single_cf_ntnf = 0
    dropped_single_cf_ntnf = 0

    for obs_date_value in spine_dates:
        obs_date = pd.Timestamp(
            obs_date_value
        ).normalize()

        if obs_date not in yields_ts.index:
            continue

        active = nominal_base[
            (nominal_base["ISSUE_DT"] <= obs_date)
            & (nominal_base["MATURITY"] > obs_date)
        ].copy()

        candidates = []

        for _, bond in active.iterrows():
            bond_id = bond["id"]

            if bond_id not in yields_ts.columns:
                continue

            ytm_pct = pd.to_numeric(
                yields_ts.at[obs_date, bond_id],
                errors="coerce",
            )

            if pd.isna(ytm_pct) or float(ytm_pct) == 0.0:
                continue

            candidates.append(
                (bond, float(ytm_pct) / 100.0)
            )

        raw_valid_points += len(candidates)

        ltn_tenors = set()

        for bond, _ in candidates:
            if bond["TYPE"] != "LTN":
                continue

            payment_date = dc.following(
                bond["MATURITY"].date()
            )

            ltn_tenors.add(
                dc.tf(
                    obs_date.date(),
                    payment_date,
                )
            )

        cash_flows = []
        rates = []

        used_ltn = 0
        used_ntnf = 0

        for bond, ytm_dec in candidates:

            if bond["TYPE"] == "LTN":
                payment_date = dc.following(
                    bond["MATURITY"].date()
                )

                cf = pd.Series(
                    [100.0],
                    index=[payment_date],
                    dtype=float,
                )

                used_ltn += 1

            else:
                coupon_pct = pd.to_numeric(
                    bond["CPN"],
                    errors="coerce",
                )

                frequency = pd.to_numeric(
                    bond["CPN_FREQ"],
                    errors="coerce",
                )

                if pd.isna(coupon_pct) or pd.isna(frequency):
                    raise AssertionError(
                        f"Missing NTN-F coupon metadata for {bond['id']}."
                    )

                frequency = int(frequency)

                if frequency != 2:
                    raise AssertionError(
                        f"Unexpected NTN-F coupon frequency "
                        f"{frequency} for {bond['id']}."
                    )

                coupon_cash_flow = (
                    (
                        1.0 + float(coupon_pct) / 100.0
                    )
                    ** (1.0 / frequency)
                    - 1.0
                ) * 100.0

                expiry = bond["MATURITY"].date()

                payment_dates = [
                    dc.following(expiry)
                ]

                payment_date = dc.workday(
                    dc.eom(
                        dc.following(expiry),
                        offset=-7,
                    ),
                    1,
                )

                while payment_date > dc.following(
                    obs_date.date()
                ):
                    payment_dates.append(
                        payment_date
                    )

                    payment_date = dc.workday(
                        dc.eom(
                            payment_date,
                            offset=-7,
                        ),
                        1,
                    )

                payment_dates = sorted(
                    payment_dates
                )

                cf = pd.Series(
                    coupon_cash_flow,
                    index=payment_dates,
                    dtype=float,
                )

                cf.iloc[-1] += 100.0

                if len(cf) == 1:
                    tenor = dc.tf(
                        obs_date.date(),
                        max(cf.index),
                    )

                    if tenor in ltn_tenors:
                        dropped_single_cf_ntnf += 1
                        continue

                    kept_single_cf_ntnf += 1

                used_ntnf += 1

            cash_flows.append(cf)
            rates.append(ytm_dec)

        used_bootstrap_inputs += len(cash_flows)

        if not cash_flows:
            continue

        if used_ltn == 0:
            raise AssertionError(
                "No valid LTN anchor on sovereign curve date "
                f"{obs_date.date()}."
            )

        bootstrap = CurveBootstrap(
            cash_flows=cash_flows,
            rates=rates,
            day_count_convention="bus/252",
            calendar="cdr_anbima",
            ref_date=obs_date.date(),
        )

        zero_curve = (
            bootstrap.zero_curve
            .dropna()
            .astype(float)
            .sort_index()
        )

        duplicate_tenors = zero_curve.index[
            zero_curve.index.duplicated()
        ].tolist()

        if duplicate_tenors:
            raise AssertionError(
                "Duplicate sovereign zero-curve tenors on "
                f"{obs_date.date()}: {duplicate_tenors}"
            )

        curves[obs_date] = zero_curve

        curve_stats[obs_date] = {
            "raw_inputs": len(candidates),
            "used_inputs": len(cash_flows),
            "used_ltn": used_ltn,
            "used_ntnf": used_ntnf,
            "zero_nodes": len(zero_curve),
        }

    rows = []

    for row in spine[
        [
            "bond_id",
            "obs_date",
            "days_to_maturity",
        ]
    ].itertuples(index=False):

        obs_date = pd.Timestamp(
            row.obs_date
        ).normalize()

        target_tenor = float(
            row.days_to_maturity
        )

        zero_curve = curves.get(
            obs_date
        )

        if zero_curve is None or zero_curve.empty:
            rows.append(
                {
                    "bond_id": row.bond_id,
                    "obs_date": obs_date,
                    "sovereign_spread_brl": np.nan,
                    "sovereign_zero_yield_pct": np.nan,
                    "di_zero_yield_pct": np.nan,
                    "sovereign_mapping_method": "no_same_date_curve",
                    "sovereign_nodes_on_date": 0,
                    "sovereign_unique_tenors_on_date": 0,
                    "sovereign_min_tenor": np.nan,
                    "sovereign_max_tenor": np.nan,
                }
            )
            continue

        tenor_values = zero_curve.index.to_numpy(
            dtype=float
        )

        min_tenor = float(
            tenor_values.min()
        )
        max_tenor = float(
            tenor_values.max()
        )

        nearest_pos = int(
            np.argmin(
                np.abs(
                    tenor_values - target_tenor
                )
            )
        )

        if np.isclose(
            tenor_values[nearest_pos],
            target_tenor,
            rtol=0.0,
            atol=1e-12,
        ):
            sovereign_zero_dec = float(
                zero_curve.iloc[nearest_pos]
            )

            method = "exact_zero_node"

        else:
            sovereign_zero_dec = float(
                flat_forward_interpolation(
                    target_tenor,
                    zero_curve,
                )
            )

            if len(zero_curve) == 1:
                method = "single_zero_node_flat"
            elif target_tenor < min_tenor:
                method = "zero_curve_flat_below_range"
            elif target_tenor > max_tenor:
                method = "zero_curve_flat_above_range"
            else:
                method = "zero_curve_flat_forward"

        sovereign_zero_pct = (
            sovereign_zero_dec * 100.0
        )

        di_zero_pct = (
            interpolate_raw_di_yield_for_tenor(
                surface=di_surface,
                obs_date=obs_date,
                target_tenor=target_tenor,
            )
        )

        if pd.isna(di_zero_pct):
            mapped_bps = np.nan
            method = "no_same_date_di_curve"
        else:
            mapped_bps = (
                geometric_spread_bps_from_pct(
                    corporate_yield_pct=sovereign_zero_pct,
                    benchmark_yield_pct=di_zero_pct,
                )
            )

        stats = curve_stats[obs_date]

        rows.append(
            {
                "bond_id": row.bond_id,
                "obs_date": obs_date,
                "sovereign_spread_brl": mapped_bps,
                "sovereign_zero_yield_pct": sovereign_zero_pct,
                "di_zero_yield_pct": di_zero_pct,
                "sovereign_mapping_method": method,
                "sovereign_nodes_on_date": stats["used_inputs"],
                "sovereign_unique_tenors_on_date": len(zero_curve),
                "sovereign_min_tenor": min_tenor,
                "sovereign_max_tenor": max_tenor,
            }
        )

    mapped = pd.DataFrame(rows)

    if len(mapped) != len(spine):
        raise AssertionError(
            "Sovereign mapping changed the bond-month row count: "
            f"{len(spine)} -> {len(mapped)}."
        )

    if mapped.duplicated(
        ["bond_id", "obs_date"]
    ).any():
        raise AssertionError(
            "Duplicate bond-date keys in sovereign mapping."
        )

    exact_curve_dates = set(curves)

    expected_nonmissing = int(
        spine["obs_date"]
        .map(
            lambda x: (
                pd.Timestamp(x).normalize()
                in exact_curve_dates
            )
        )
        .sum()
    )

    actual_nonmissing = int(
        mapped["sovereign_spread_brl"]
        .notna()
        .sum()
    )

    if actual_nonmissing != expected_nonmissing:
        raise AssertionError(
            "Same-date sovereign/DI mapping coverage mismatch: "
            f"expected {expected_nonmissing:,}, "
            f"got {actual_nonmissing:,}."
        )

    mapped.attrs["sovereign_raw_points"] = raw_valid_points
    mapped.attrs["sovereign_bootstrap_inputs"] = used_bootstrap_inputs
    mapped.attrs["sovereign_zero_nodes"] = sum(
        len(curve)
        for curve in curves.values()
    )
    mapped.attrs["sovereign_curve_dates"] = len(curves)
    mapped.attrs["duplicate_date_tenor_groups"] = 0
    mapped.attrs["single_cf_ntnf_kept"] = kept_single_cf_ntnf
    mapped.attrs["single_cf_ntnf_dropped"] = dropped_single_cf_ntnf
    mapped.attrs["ntnf_skipped"] = dropped_single_cf_ntnf

    return mapped


# ---------------------------------------------------------------------
# Final panel assembly / validation
# ---------------------------------------------------------------------

def assemble_rebuilt_panel(
    spine: pd.DataFrame,
    corporate_spread: pd.DataFrame,
    macro_controls: pd.DataFrame,
    public_debt_gdp: pd.DataFrame,
    accounting_controls: pd.DataFrame,
    relative_issue_size: pd.DataFrame,
    sovereign_spread: pd.DataFrame,
) -> pd.DataFrame:
    """
    Assemble the authoritative candidate econometrics panel from the
    frozen canonical components.

    The rebuilt schema preserves the legacy 19-column structure except
    that synthetic_cds_brl is replaced by sovereign_spread_brl.
    """

    panel = spine[
        [
            "bond_id",
            "issuer",
            "maturity",
            "bond_type",
            "exchange id",
            "sector",
            "obs_date",
            "month",
            "days_to_maturity",
        ]
    ].copy()

    panel = panel.merge(
        corporate_spread[
            [
                "bond_id",
                "obs_date",
                "spread",
            ]
        ],
        on=[
            "bond_id",
            "obs_date",
        ],
        how="left",
        validate="one_to_one",
    )

    panel = panel.merge(
        macro_controls[
            [
                "month",
                "vix",
                "fed_3m_forward",
                "usd_brl",
                "gdp_yoy",
            ]
        ],
        on="month",
        how="left",
        validate="many_to_one",
    )

    panel = panel.merge(
        public_debt_gdp[
            [
                "month",
                "debt_gdp",
            ]
        ],
        on="month",
        how="left",
        validate="many_to_one",
    )

    panel = panel.merge(
        accounting_controls[
            [
                "bond_id",
                "obs_date",
                "cf_cash_oper_to_tot_asset",
                "tot_debt_to_ebitda",
            ]
        ],
        on=[
            "bond_id",
            "obs_date",
        ],
        how="left",
        validate="one_to_one",
    )

    panel = panel.merge(
        relative_issue_size[
            [
                "bond_id",
                "obs_date",
                "amount_issued_to_bs_tot_asset",
            ]
        ],
        on=[
            "bond_id",
            "obs_date",
        ],
        how="left",
        validate="one_to_one",
    )

    panel = panel.merge(
        sovereign_spread[
            [
                "bond_id",
                "obs_date",
                "sovereign_spread_brl",
            ]
        ],
        on=[
            "bond_id",
            "obs_date",
        ],
        how="left",
        validate="one_to_one",
    )

    columns = [
        "bond_id",
        "issuer",
        "maturity",
        "bond_type",
        "exchange id",
        "sector",
        "obs_date",
        "month",
        "spread",
        "vix",
        "fed_3m_forward",
        "usd_brl",
        "gdp_yoy",
        "debt_gdp",
        "cf_cash_oper_to_tot_asset",
        "amount_issued_to_bs_tot_asset",
        "tot_debt_to_ebitda",
        "days_to_maturity",
        "sovereign_spread_brl",
    ]

    panel = (
        panel[columns]
        .sort_values(
            [
                "bond_id",
                "obs_date",
            ]
        )
        .reset_index(drop=True)
    )

    # ----------------------------------------------------------
    # Freeze-gate assertions
    # ----------------------------------------------------------

    if len(panel) != 4648:
        raise AssertionError(
            f"Expected 4,648 rows; got {len(panel):,}."
        )

    if panel["bond_id"].nunique() != 103:
        raise AssertionError(
            "Expected 103 unique bonds."
        )

    if panel["issuer"].nunique() != 48:
        raise AssertionError(
            "Expected 48 unique issuers."
        )

    if panel.duplicated(
        [
            "bond_id",
            "month",
        ]
    ).any():
        raise AssertionError(
            "Duplicate bond-month keys in rebuilt panel."
        )

    if panel.duplicated(
        [
            "bond_id",
            "obs_date",
        ]
    ).any():
        raise AssertionError(
            "Duplicate bond-date keys in rebuilt panel."
        )

    if panel["obs_date"].min() != pd.Timestamp(
        "2010-12-30"
    ):
        raise AssertionError(
            "Unexpected first obs_date."
        )

    if panel["obs_date"].max() != pd.Timestamp(
        "2025-06-30"
    ):
        raise AssertionError(
            "Unexpected last obs_date."
        )

    complete_columns = [
        c
        for c in columns
        if c != "sovereign_spread_brl"
    ]

    missing_complete = (
        panel[complete_columns]
        .isna()
        .sum()
    )

    missing_complete = missing_complete[
        missing_complete > 0
    ]

    if not missing_complete.empty:
        raise AssertionError(
            "Unexpected missing values in rebuilt panel:\n"
            f"{missing_complete.to_string()}"
        )

    sovereign_nonmissing = int(
        panel["sovereign_spread_brl"]
        .notna()
        .sum()
    )

    sovereign_missing = int(
        panel["sovereign_spread_brl"]
        .isna()
        .sum()
    )

    if sovereign_nonmissing != 4648:
        raise AssertionError(
            "Expected 4,648 non-missing sovereign spreads; "
            f"got {sovereign_nonmissing:,}."
        )

    if sovereign_missing != 0:
        raise AssertionError(
            "Expected 0 missing sovereign spreads; "
            f"got {sovereign_missing:,}."
        )

    pre_2016 = (
        panel["obs_date"]
        < pd.Timestamp("2016-01-01")
    )

    if panel.loc[
        pre_2016,
        "sovereign_spread_brl",
    ].isna().any():
        raise AssertionError(
            "Missing sovereign spread in pre-2016 sample."
        )

    post_2016 = ~pre_2016

    if panel.loc[
        post_2016,
        "sovereign_spread_brl",
    ].isna().any():
        raise AssertionError(
            "Missing sovereign spread in 2016+ sample."
        )

    return panel


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> None:
    if OUTPUT_PANEL.resolve() == LEGACY_PANEL.resolve():
        raise RuntimeError("Safety violation: output path equals legacy panel.")

    inputs = resolve_inputs()
    validate_real_curve_path_contract(inputs)
    print("PASS - real-curve CONFIG paths match canonical registry")

    legacy = load_legacy_panel(inputs.legacy_panel)

    spine = build_bond_month_spine(inputs)

    corporate_spread, corporate_spread_skipped = (
        build_corporate_spread(inputs)
    )

    validate_corporate_spread_against_spine(
        spine,
        corporate_spread,
    )

    macro_controls = build_macro_controls(
        inputs,
        spine["month"],
    )

    public_debt_gdp = build_public_debt_gdp(
        inputs,
        spine["month"],
    )

    accounting_controls = build_accounting_controls(
        inputs,
        spine,
    )

    relative_issue_size = build_relative_issue_size(
        inputs,
        spine,
    )

    sovereign_spread = build_sovereign_spread(
        inputs,
        spine,
    )

    rebuilt_panel = assemble_rebuilt_panel(
        spine,
        corporate_spread,
        macro_controls,
        public_debt_gdp,
        accounting_controls,
        relative_issue_size,
        sovereign_spread,
    )

    print("\nREBUILT CORPORATE SPREAD")
    print(f"  rows             : {len(corporate_spread):,}")
    print(
        f"  bonds            : "
        f"{corporate_spread['bond_id'].nunique():,}"
    )
    print(
        f"  first obs_date   : "
        f"{corporate_spread['obs_date'].min().date()}"
    )
    print(
        f"  last obs_date    : "
        f"{corporate_spread['obs_date'].max().date()}"
    )
    print(
        f"  duplicate keys   : "
        f"{corporate_spread.duplicated(['bond_id', 'obs_date']).sum():,}"
    )
    print(
        f"  skipped records  : "
        f"{len(corporate_spread_skipped):,}"
    )

    print_input_audit(inputs, legacy)

    print("\nCANONICAL BOND-MONTH SPINE")
    print(f"  rows             : {len(spine):,}")
    print(f"  bonds            : {spine['bond_id'].nunique():,}")
    print(f"  issuers          : {spine['issuer'].nunique():,}")
    print(f"  first obs_date   : {spine['obs_date'].min().date()}")
    print(f"  last obs_date    : {spine['obs_date'].max().date()}")
    print(
        "  duplicate keys   : "
        f"{spine.duplicated(['bond_id', 'month']).sum():,}"
    )
    print(
        "  corporate yields : "
        f"{spine['corporate_yield_pct'].notna().sum():,}"
    )
    print(
        "  maturity days    : "
        f"{spine['days_to_maturity'].notna().sum():,}"
    )

    print("\nBASELINE MACRO CONTROLS")
    print(f"  months           : {len(macro_controls):,}")
    print(
        f"  first month      : "
        f"{macro_controls['month'].min().date()}"
    )
    print(
        f"  last month       : "
        f"{macro_controls['month'].max().date()}"
    )
    print(
        "  duplicate months : "
        f"{macro_controls.duplicated(['month']).sum():,}"
    )
    print(
        "  complete rows    : "
        f"{macro_controls.dropna().shape[0]:,}"
    )

    print("\nPUBLIC DEBT / GDP - SGS 13762")
    print(f"  months           : {len(public_debt_gdp):,}")
    print(
        f"  first month      : "
        f"{public_debt_gdp['month'].min().date()}"
    )
    print(
        f"  last month       : "
        f"{public_debt_gdp['month'].max().date()}"
    )
    print(
        "  missing values   : "
        f"{public_debt_gdp['debt_gdp'].isna().sum():,}"
    )
    print(
        "  min debt/GDP     : "
        f"{public_debt_gdp['debt_gdp'].min():.2f}"
    )
    print(
        "  max debt/GDP     : "
        f"{public_debt_gdp['debt_gdp'].max():.2f}"
    )

    accounting_pairs = (
        accounting_controls[
            [
                "accounting_parent",
                "obs_date",
                "accounting_fallback_quarters",
            ]
        ]
        .drop_duplicates()
    )

    print("\nISSUER ACCOUNTING CONTROLS")
    print(
        f"  bond-date rows     : "
        f"{len(accounting_controls):,}"
    )
    print(
        f"  issuer-date pairs  : "
        f"{len(accounting_pairs):,}"
    )
    print(
        "  primary quarter    : "
        f"{(accounting_pairs['accounting_fallback_quarters'] == 0).sum():,}"
    )
    print(
        "  one-Q fallback     : "
        f"{(accounting_pairs['accounting_fallback_quarters'] == 1).sum():,}"
    )
    print(
        "  two-Q fallback     : "
        f"{(accounting_pairs['accounting_fallback_quarters'] == 2).sum():,}"
    )
    print(
        "  missing CFO/assets : "
        f"{accounting_controls['cf_cash_oper_to_tot_asset'].isna().sum():,}"
    )
    print(
        "  missing Debt/EBITDA: "
        f"{accounting_controls['tot_debt_to_ebitda'].isna().sum():,}"
    )

    issue_within = (
        relative_issue_size
        .groupby("bond_id")[
            "amount_issued_to_bs_tot_asset"
        ]
        .nunique(dropna=True)
    )

    print("\nRELATIVE ISSUE SIZE")
    print(
        f"  bond-date rows     : "
        f"{len(relative_issue_size):,}"
    )
    print(
        "  primary quarter    : "
        f"{(relative_issue_size['issue_size_fallback_quarters'] == 0).sum():,}"
    )
    print(
        "  one-Q fallback     : "
        f"{(relative_issue_size['issue_size_fallback_quarters'] == 1).sum():,}"
    )
    print(
        "  two-Q fallback     : "
        f"{(relative_issue_size['issue_size_fallback_quarters'] == 2).sum():,}"
    )
    print(
        "  missing ratios     : "
        f"{relative_issue_size['amount_issued_to_bs_tot_asset'].isna().sum():,}"
    )
    print(
        "  varying bonds      : "
        f"{(issue_within > 1).sum():,}"
    )

    print("\nSOVEREIGN SPREAD BRL")
    print(
        "  raw sovereign inputs: "
        f"{sovereign_spread.attrs['sovereign_raw_points']:,}"
    )
    print(
        "  bootstrap inputs    : "
        f"{sovereign_spread.attrs['sovereign_bootstrap_inputs']:,}"
    )
    print(
        "  zero-curve nodes    : "
        f"{sovereign_spread.attrs['sovereign_zero_nodes']:,}"
    )
    print(
        "  sovereign dates     : "
        f"{sovereign_spread.attrs['sovereign_curve_dates']:,}"
    )
    print(
        "  single-CF NTN-F kept: "
        f"{sovereign_spread.attrs['single_cf_ntnf_kept']:,}"
    )
    print(
        "  single-CF NTN-F drop: "
        f"{sovereign_spread.attrs['single_cf_ntnf_dropped']:,}"
    )
    print(
        "  mapped bond-dates    : "
        f"{sovereign_spread['sovereign_spread_brl'].notna().sum():,}"
    )
    print(
        "  missing bond-dates   : "
        f"{sovereign_spread['sovereign_spread_brl'].isna().sum():,}"
    )

    print("  mapping methods:")
    for method, count in (
        sovereign_spread[
            "sovereign_mapping_method"
        ]
        .value_counts(dropna=False)
        .sort_index()
        .items()
    ):
        print(
            f"    {str(method):28s} {count:>6,}"
        )

    print("\nREBUILT PANEL - FREEZE-GATE VALIDATION")
    print(f"  rows              : {len(rebuilt_panel):,}")
    print(
        f"  columns           : "
        f"{len(rebuilt_panel.columns):,}"
    )
    print(
        f"  bonds             : "
        f"{rebuilt_panel['bond_id'].nunique():,}"
    )
    print(
        f"  issuers           : "
        f"{rebuilt_panel['issuer'].nunique():,}"
    )
    print(
        "  duplicate b-m keys: "
        f"{rebuilt_panel.duplicated(['bond_id', 'month']).sum():,}"
    )
    print(
        "  sovereign present : "
        f"{rebuilt_panel['sovereign_spread_brl'].notna().sum():,}"
    )
    print(
        "  sovereign missing : "
        f"{rebuilt_panel['sovereign_spread_brl'].isna().sum():,}"
    )

    # Safe candidate write only.
    # The frozen legacy workbook is never overwritten here.
    if OUTPUT_PANEL.resolve() == LEGACY_PANEL.resolve():
        raise RuntimeError(
            "Safety violation: candidate output equals legacy panel."
        )

    OUTPUT_PANEL.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    rebuilt_panel.to_excel(
        OUTPUT_PANEL,
        sheet_name="ts",
        index=False,
    )

    print(
        "\nPASS - rebuilt panel validated and written:"
    )
    print(f"  {OUTPUT_PANEL}")
    print("PASS - legacy panel remains untouched")


if __name__ == "__main__":
    main()
