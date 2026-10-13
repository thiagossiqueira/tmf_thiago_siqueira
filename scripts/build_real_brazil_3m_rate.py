from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

FOCUS_FILE = (
    ROOT
    / "datos_y_modelos"
    / "db"
    / "brazil_macroeconomic_data"
    / "real_brazil_3m"
    / "focus_ipca_3m_expected_panel_dates.csv"
)

NOMINAL_FILE = (
    ROOT
    / "datos_y_modelos"
    / "db"
    / "brazil_macroeconomic_data"
    / "brazil_3m_di_forward"
    / "brazil_3m_di_ycsw0089_monthly.xlsx"
)

CANONICAL_DI_FILE = (
    ROOT
    / "datos_y_modelos"
    / "db"
    / "one-day_interbank_deposit_futures_contract_di"
    / "di_curve.v6.xlsx"
)

OUTPUT_FILE = (
    ROOT
    / "datos_y_modelos"
    / "db"
    / "brazil_macroeconomic_data"
    / "real_brazil_3m"
    / "real_brazil_3m_focus_panel_dates.csv"
)


def load_focus() -> pd.DataFrame:
    df = pd.read_csv(
        FOCUS_FILE,
        parse_dates=["obs_date"],
    )

    df["obs_date"] = df["obs_date"].dt.normalize()
    df["month"] = df["obs_date"].dt.to_period("M")

    if df["obs_date"].duplicated().any():
        raise ValueError(
            "Duplicate obs_date in Focus expected-inflation input."
        )

    if df["month"].duplicated().any():
        raise ValueError(
            "More than one frozen-panel observation date per calendar month."
        )

    return df


def load_nominal() -> pd.DataFrame:
    df = pd.read_excel(NOMINAL_FILE)

    required = [
        "obs_date",
        "curve",
        "tenor",
        "curve_rate",
        "member_ticker",
        "bloomberg_date",
        "status",
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing nominal-DI columns: {missing}"
        )

    df["ycsw_obs_date"] = pd.to_datetime(
        df["obs_date"],
        errors="coerce",
    ).dt.normalize()

    df["bloomberg_date"] = pd.to_datetime(
        df["bloomberg_date"],
        errors="coerce",
    ).dt.normalize()

    df["month"] = df["ycsw_obs_date"].dt.to_period("M")

    df["member_ticker"] = (
        df["member_ticker"]
        .astype(str)
        .str.strip()
    )

    df["curve_rate"] = pd.to_numeric(
        df["curve_rate"],
        errors="coerce",
    )

    if df["month"].duplicated().any():
        duplicates = df.loc[
            df["month"].duplicated(keep=False),
            [
                "ycsw_obs_date",
                "member_ticker",
                "curve_rate",
            ],
        ]

        raise ValueError(
            "Duplicate YCSW0089 calendar months:\n"
            + duplicates.to_string(index=False)
        )

    return df[
        [
            "month",
            "ycsw_obs_date",
            "curve",
            "tenor",
            "curve_rate",
            "member_ticker",
            "bloomberg_date",
            "status",
        ]
    ].copy()


def load_canonical_di() -> pd.DataFrame:
    df = pd.read_excel(
        CANONICAL_DI_FILE,
        sheet_name="only_values",
    )

    df["canonical_curve_date"] = pd.to_datetime(
        df["Curve date"],
        errors="coerce",
    ).dt.normalize()

    df["Specific ticker"] = (
        df["Specific ticker"]
        .astype(str)
        .str.strip()
    )

    df["px_last"] = pd.to_numeric(
        df["px_last"],
        errors="coerce",
    )

    df["Term"] = pd.to_numeric(
        df["Term"],
        errors="coerce",
    )

    df = df.loc[
        df["Specific ticker"].notna()
        & df["Specific ticker"].ne(""),
        [
            "canonical_curve_date",
            "Specific ticker",
            "Term",
            "px_last",
            "Type",
        ],
    ].copy()

    duplicate_key = df.duplicated(
        [
            "canonical_curve_date",
            "Specific ticker",
        ],
        keep=False,
    )

    if duplicate_key.any():
        duplicates = df.loc[
            duplicate_key,
            [
                "canonical_curve_date",
                "Specific ticker",
                "Term",
                "px_last",
                "Type",
            ],
        ]

        raise ValueError(
            "Duplicate exact-date/ticker rows in canonical DI file:\n"
            + duplicates.to_string(index=False)
        )

    return df


def build_rate() -> pd.DataFrame:
    focus = load_focus()
    nominal = load_nominal()

    out = focus.merge(
        nominal,
        on="month",
        how="left",
        validate="one_to_one",
        indicator=True,
    )

    if not (out["_merge"] == "both").all():
        bad = out.loc[
            out["_merge"].ne("both"),
            [
                "obs_date",
                "month",
                "_merge",
            ],
        ]

        raise ValueError(
            "Focus and nominal DI inputs do not align one-to-one:\n"
            + bad.to_string(index=False)
        )

    out = out.drop(columns=["_merge"])

    if out["curve_rate"].isna().any():
        raise ValueError(
            "Missing nominal Brazil 3M DI rate after merge."
        )

    if out["member_ticker"].isna().any():
        raise ValueError(
            "Missing nominal DI member ticker after merge."
        )

    if not out["status"].astype(str).str.upper().eq("OK").all():
        bad = out.loc[
            ~out["status"].astype(str).str.upper().eq("OK"),
            [
                "obs_date",
                "member_ticker",
                "status",
            ],
        ]

        raise ValueError(
            "Non-OK nominal DI status detected:\n"
            + bad.to_string(index=False)
        )

    canonical = load_canonical_di()

    out = out.merge(
        canonical,
        left_on=[
            "obs_date",
            "member_ticker",
        ],
        right_on=[
            "canonical_curve_date",
            "Specific ticker",
        ],
        how="left",
        validate="one_to_one",
    )

    if out["px_last"].isna().any():
        bad = out.loc[
            out["px_last"].isna(),
            [
                "obs_date",
                "member_ticker",
                "curve_rate",
            ],
        ]

        raise ValueError(
            "Missing exact-date/ticker canonical DI verification:\n"
            + bad.to_string(index=False)
        )

    out["nominal_di_canonical_diff_bp"] = (
        out["curve_rate"]
        - out["px_last"]
    ).abs() * 100.0

    if (
        out["nominal_di_canonical_diff_bp"]
        > 1e-9
    ).any():
        bad = out.loc[
            out["nominal_di_canonical_diff_bp"] > 1e-9,
            [
                "obs_date",
                "member_ticker",
                "curve_rate",
                "px_last",
                "nominal_di_canonical_diff_bp",
            ],
        ]

        raise ValueError(
            "YCSW0089 nominal rate differs from exact-date canonical DI rate:\n"
            + bad.to_string(index=False)
        )

    out["nominal_brazil_3m_di_pct"] = out["curve_rate"]

    # Primary measure:
    # standard short-rate approximation r ~= i - E(pi).
    out["real_brazil_3m_focus"] = (
        out["nominal_brazil_3m_di_pct"]
        - out["expected_ipca_ann_pct"]
    )

    # Companion exact Fisher transformation.
    out["real_brazil_3m_focus_exact"] = (
        (
            (
                1.0
                + out["nominal_brazil_3m_di_pct"] / 100.0
            )
            /
            (
                1.0
                + out["expected_ipca_ann_pct"] / 100.0
            )
        )
        - 1.0
    ) * 100.0

    out = out.rename(
        columns={
            "Term": "di_tenor_bus252",
            "Type": "canonical_di_type",
            "px_last": "canonical_di_rate_pct",
        }
    )

    keep = [
        "obs_date",
        "month",
        "nominal_brazil_3m_di_pct",
        "member_ticker",
        "di_tenor_bus252",
        "ycsw_obs_date",
        "bloomberg_date",
        "canonical_curve_date",
        "canonical_di_rate_pct",
        "nominal_di_canonical_diff_bp",
        "expected_ipca_3m_pct",
        "expected_ipca_ann_pct",
        "ipca_exp_m1_pct",
        "ipca_exp_m2_pct",
        "ipca_exp_m3_pct",
        "target_m1",
        "target_m2",
        "target_m3",
        "real_brazil_3m_focus",
        "real_brazil_3m_focus_exact",
        "focus_indicator",
        "focus_base_calculo",
        "curve",
        "tenor",
        "status",
        "canonical_di_type",
    ]

    return out[keep].sort_values(
        "obs_date"
    ).reset_index(drop=True)


def validate(out: pd.DataFrame) -> None:
    if len(out) != 175:
        raise ValueError(
            f"Expected 175 rows, got {len(out)}."
        )

    if out["obs_date"].duplicated().any():
        raise ValueError(
            "Duplicate output obs_date detected."
        )

    required = [
        "nominal_brazil_3m_di_pct",
        "expected_ipca_ann_pct",
        "real_brazil_3m_focus",
        "real_brazil_3m_focus_exact",
        "member_ticker",
        "di_tenor_bus252",
        "canonical_di_rate_pct",
    ]

    if out[required].isna().any().any():
        raise ValueError(
            "Missing required values in Real Brazil 3M output."
        )

    if not np.allclose(
        out["nominal_brazil_3m_di_pct"],
        out["canonical_di_rate_pct"],
        rtol=0.0,
        atol=1e-12,
    ):
        raise ValueError(
            "Nominal YCSW0089 and canonical DI rates are not identical."
        )

    checks = {
        "2011-04-29": {
            "nominal": 12.05,
            "inflation": 3.99084520276192,
            "approx": 8.059154797238081,
            "exact": 7.74986950199732,
        },
        "2020-04-30": {
            "nominal": 2.958,
            "inflation": 0.237564862178874,
            "approx": 2.7204351378211262,
            "exact": 2.713987656784722,
        },
        "2024-04-30": {
            "nominal": 10.341,
            "inflation": 2.303863418,
            "approx": 8.037136581999999,
            "exact": 7.856141804890915,
        },
    }

    indexed = out.set_index(
        out["obs_date"].dt.strftime("%Y-%m-%d")
    )

    for date_text, expected in checks.items():
        row = indexed.loc[date_text]

        tests = {
            "nominal_brazil_3m_di_pct": expected["nominal"],
            "expected_ipca_ann_pct": expected["inflation"],
            "real_brazil_3m_focus": expected["approx"],
            "real_brazil_3m_focus_exact": expected["exact"],
        }

        for column, target in tests.items():
            actual = float(row[column])

            if abs(actual - target) > 1e-8:
                raise ValueError(
                    f"{date_text} {column}: "
                    f"expected {target}, got {actual}"
                )


def main() -> None:
    out = build_rate()
    validate(out)

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    out.to_csv(
        OUTPUT_FILE,
        index=False,
        date_format="%Y-%m-%d",
    )

    print("REAL BRAZIL 3M FOCUS RATE BUILDER")
    print("---------------------------------")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Rows: {len(out)}")
    print(
        "Range:",
        out["obs_date"].min().date(),
        "to",
        out["obs_date"].max().date(),
    )
    print(
        "Missing required values:",
        int(
            out[
                [
                    "nominal_brazil_3m_di_pct",
                    "expected_ipca_ann_pct",
                    "real_brazil_3m_focus",
                    "real_brazil_3m_focus_exact",
                ]
            ]
            .isna()
            .sum()
            .sum()
        ),
    )
    print(
        "Max nominal-vs-canonical DI difference (bp):",
        out["nominal_di_canonical_diff_bp"].max(),
    )
    print()
    print("Validation checkpoints:")
    print(
        out.loc[
            out["obs_date"].isin(
                pd.to_datetime(
                    [
                        "2011-04-29",
                        "2020-04-30",
                        "2024-04-30",
                    ]
                )
            ),
            [
                "obs_date",
                "member_ticker",
                "di_tenor_bus252",
                "nominal_brazil_3m_di_pct",
                "expected_ipca_ann_pct",
                "real_brazil_3m_focus",
                "real_brazil_3m_focus_exact",
            ],
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
