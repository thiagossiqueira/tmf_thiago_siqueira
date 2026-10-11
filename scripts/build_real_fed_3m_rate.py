from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

SPF_FILE = (
    ROOT
    / "datos_y_modelos"
    / "db"
    / "brazil_macroeconomic_data"
    / "real_fed_3m"
    / "spf_cpi_next_quarter_monthly.csv"
)

USSOC_FILE = (
    ROOT
    / "datos_y_modelos"
    / "db"
    / "brazil_macroeconomic_data"
    / "fed_3m_forward"
    / "ussoc_monthly_2010_2025.csv"
)

OUTPUT_FILE = (
    ROOT
    / "datos_y_modelos"
    / "db"
    / "brazil_macroeconomic_data"
    / "real_fed_3m"
    / "real_fed_3m_spf_monthly.csv"
)


def main() -> None:
    spf = pd.read_csv(
        SPF_FILE,
        parse_dates=["month_end", "release_date"],
    )

    ussoc = pd.read_csv(
        USSOC_FILE,
        parse_dates=["calendar_month_end"],
    )

    ussoc = ussoc[
        [
            "calendar_month_end",
            "ussoc_px_last",
        ]
    ].copy()

    ussoc = ussoc[
        ussoc["calendar_month_end"].between(
            spf["month_end"].min(),
            spf["month_end"].max(),
        )
    ].copy()

    if spf["month_end"].duplicated().any():
        raise ValueError("Duplicate month-end in SPF monthly input.")

    if ussoc["calendar_month_end"].duplicated().any():
        raise ValueError("Duplicate month-end in USSOC monthly input.")

    out = spf.merge(
        ussoc,
        left_on="month_end",
        right_on="calendar_month_end",
        how="outer",
        validate="one_to_one",
        indicator=True,
    )

    if not (out["_merge"] == "both").all():
        raise ValueError(
            "SPF and USSOC month-end series do not align one-to-one."
        )

    out = out.drop(columns=["calendar_month_end", "_merge"])

    if out["ussoc_px_last"].isna().any():
        raise ValueError("Missing USSOC values after merge.")

    if out["spf_cpi_next_quarter"].isna().any():
        raise ValueError("Missing SPF CPI values after merge.")

    # Primary robustness measure:
    # standard short-rate approximation r ~= i - E(pi).
    out["real_fed_3m_spf"] = (
        out["ussoc_px_last"]
        - out["spf_cpi_next_quarter"]
    )

    # Optional exact Fisher transformation.
    out["real_fed_3m_spf_exact"] = (
        (
            (1 + out["ussoc_px_last"] / 100)
            / (1 + out["spf_cpi_next_quarter"] / 100)
        )
        - 1
    ) * 100

    out = out[
        [
            "month_end",
            "ussoc_px_last",
            "spf_cpi_next_quarter",
            "real_fed_3m_spf",
            "real_fed_3m_spf_exact",
            "spf_survey",
            "survey_year",
            "survey_quarter",
            "release_date",
            "days_since_release",
        ]
    ].sort_values("month_end")

    if len(out) != 114:
        raise ValueError(f"Expected 114 rows, got {len(out)}.")

    checks = {
        "2016-01-31": -1.3594,
        "2016-02-29": -1.2792,
        "2019-02-28": -0.0177,
        "2019-03-31": 0.0909,
        "2025-06-30": 0.60127,
    }

    indexed = out.set_index(
        out["month_end"].dt.strftime("%Y-%m-%d")
    )

    for date_text, expected in checks.items():
        actual = float(
            indexed.loc[date_text, "real_fed_3m_spf"]
        )
        if abs(actual - expected) > 1e-10:
            raise ValueError(
                f"{date_text}: expected {expected}, got {actual}."
            )

    out.to_csv(
        OUTPUT_FILE,
        index=False,
        date_format="%Y-%m-%d",
    )

    print("REAL FED 3M SPF RATE BUILDER")
    print("----------------------------")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Rows: {len(out)}")
    print(
        "Range:",
        out["month_end"].min().date(),
        "to",
        out["month_end"].max().date(),
    )
    print(
        "Missing real rate:",
        int(out["real_fed_3m_spf"].isna().sum()),
    )
    print()
    print("Validation checkpoints:")
    print(
        out.loc[
            out["month_end"].isin(
                pd.to_datetime(
                    [
                        "2016-01-31",
                        "2016-02-29",
                        "2019-02-28",
                        "2019-03-31",
                        "2025-06-30",
                    ]
                )
            ),
            [
                "month_end",
                "ussoc_px_last",
                "spf_cpi_next_quarter",
                "real_fed_3m_spf",
                "real_fed_3m_spf_exact",
                "spf_survey",
            ],
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
