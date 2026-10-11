from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

INPUT_DIR = (
    ROOT
    / "datos_y_modelos"
    / "db"
    / "brazil_macroeconomic_data"
    / "real_fed_3m"
)

CPI_FILE = INPUT_DIR / "Mean_CPI_Level.xlsx"
RELEASE_FILE = INPUT_DIR / "spf-release-dates.txt"

OUTPUT_FILE = INPUT_DIR / "spf_cpi_next_quarter_monthly.csv"

START_MONTH = "2016-01-31"
END_MONTH = "2025-06-30"


def parse_release_dates(path: Path) -> pd.DataFrame:
    """
    Parse Philadelphia Fed SPF official release dates.

    The source format prints the year only on the first survey row for each year.
    Q2-Q4 rows inherit the most recently observed year.

    Footnote markers such as *, **, *** are stripped before date parsing.
    """
    pattern = re.compile(
        r"^\s*(?:(\d{4})\s+)?Q([1-4])\s+"
        r"(\d{1,2}/\d{1,2}/\d{2})\**\s+"
        r"(\d{1,2}/\d{1,2}/\d{2})\**"
    )

    rows = []
    current_year = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(raw_line)
        if not match:
            continue

        year_text, quarter_text, deadline_text, release_text = match.groups()

        if year_text is not None:
            current_year = int(year_text)

        if current_year is None:
            raise ValueError(
                f"Quarter encountered before a year could be determined: {raw_line!r}"
            )

        release_date = pd.to_datetime(
            release_text,
            format="%m/%d/%y",
        )

        rows.append(
            {
                "survey_year": current_year,
                "survey_quarter": int(quarter_text),
                "release_date": release_date,
            }
        )

    out = pd.DataFrame(rows)

    if out.empty:
        raise ValueError("No SPF release-date rows were parsed.")

    if out.duplicated(["survey_year", "survey_quarter"]).any():
        duplicates = out.loc[
            out.duplicated(["survey_year", "survey_quarter"], keep=False)
        ]
        raise ValueError(
            "Duplicate survey YEAR-QUARTER keys in release-date source:\n"
            + duplicates.to_string(index=False)
        )

    return out.sort_values(
        ["survey_year", "survey_quarter"]
    ).reset_index(drop=True)


def load_cpi3(path: Path) -> pd.DataFrame:
    """
    Load Philadelphia Fed SPF mean next-quarter CPI inflation forecast.

    CPI3 is the mean forecast of headline CPI inflation for quarter t+1,
    expressed at an annualized quarterly rate in percentage points.
    """
    df = pd.read_excel(
        path,
        sheet_name="Mean_Level",
        usecols=["YEAR", "QUARTER", "CPI3"],
    )

    df = df.rename(
        columns={
            "YEAR": "survey_year",
            "QUARTER": "survey_quarter",
            "CPI3": "spf_cpi_next_quarter",
        }
    )

    df = df.dropna(
        subset=["survey_year", "survey_quarter", "spf_cpi_next_quarter"]
    ).copy()

    df["survey_year"] = df["survey_year"].astype(int)
    df["survey_quarter"] = df["survey_quarter"].astype(int)

    if df.duplicated(["survey_year", "survey_quarter"]).any():
        duplicates = df.loc[
            df.duplicated(["survey_year", "survey_quarter"], keep=False)
        ]
        raise ValueError(
            "Duplicate YEAR-QUARTER keys in CPI source:\n"
            + duplicates.to_string(index=False)
        )

    return df


def build_monthly_series() -> pd.DataFrame:
    cpi = load_cpi3(CPI_FILE)
    releases = parse_release_dates(RELEASE_FILE)

    quarterly = cpi.merge(
        releases,
        on=["survey_year", "survey_quarter"],
        how="inner",
        validate="one_to_one",
    )

    quarterly = quarterly.sort_values("release_date").reset_index(drop=True)

    month_ends = pd.DataFrame(
        {
            "month_end": pd.date_range(
                START_MONTH,
                END_MONTH,
                freq="ME",
            )
        }
    )

    monthly = pd.merge_asof(
        month_ends.sort_values("month_end"),
        quarterly[
            [
                "release_date",
                "survey_year",
                "survey_quarter",
                "spf_cpi_next_quarter",
            ]
        ].sort_values("release_date"),
        left_on="month_end",
        right_on="release_date",
        direction="backward",
        allow_exact_matches=True,
    )

    monthly["days_since_release"] = (
        monthly["month_end"] - monthly["release_date"]
    ).dt.days

    monthly["spf_survey"] = (
        monthly["survey_year"].astype("Int64").astype(str)
        + "Q"
        + monthly["survey_quarter"].astype("Int64").astype(str)
    )

    monthly = monthly[
        [
            "month_end",
            "spf_survey",
            "survey_year",
            "survey_quarter",
            "release_date",
            "days_since_release",
            "spf_cpi_next_quarter",
        ]
    ]

    return monthly


def validate(monthly: pd.DataFrame) -> None:
    expected_months = len(
        pd.date_range(START_MONTH, END_MONTH, freq="ME")
    )

    if len(monthly) != expected_months:
        raise ValueError(
            f"Expected {expected_months} monthly rows, got {len(monthly)}."
        )

    if monthly["month_end"].duplicated().any():
        raise ValueError("Duplicate month-end rows detected.")

    if monthly[
        [
            "spf_survey",
            "release_date",
            "spf_cpi_next_quarter",
        ]
    ].isna().any().any():
        raise ValueError("Missing SPF mapping in estimation window.")

    if (monthly["release_date"] > monthly["month_end"]).any():
        raise ValueError("Look-ahead detected: release date after month-end.")

    checks = {
        "2016-01-31": ("2015Q4", 1.7479),
        "2016-02-29": ("2016Q1", 1.6797),
        "2019-02-28": ("2018Q4", 2.4267),
        "2019-03-31": ("2019Q1", 2.3051),
        "2025-06-30": ("2025Q2", 3.6809),
    }

    indexed = monthly.set_index(
        monthly["month_end"].dt.strftime("%Y-%m-%d")
    )

    for date_text, (expected_survey, expected_cpi) in checks.items():
        row = indexed.loc[date_text]

        if row["spf_survey"] != expected_survey:
            raise ValueError(
                f"{date_text}: expected {expected_survey}, "
                f"got {row['spf_survey']}."
            )

        if abs(float(row["spf_cpi_next_quarter"]) - expected_cpi) > 1e-10:
            raise ValueError(
                f"{date_text}: expected CPI3 {expected_cpi}, "
                f"got {row['spf_cpi_next_quarter']}."
            )


def main() -> None:
    monthly = build_monthly_series()
    validate(monthly)

    monthly.to_csv(
        OUTPUT_FILE,
        index=False,
        date_format="%Y-%m-%d",
    )

    print("REAL FED 3M SPF MONTHLY BUILDER")
    print("--------------------------------")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Rows: {len(monthly)}")
    print(
        "Range:",
        monthly["month_end"].min().date(),
        "to",
        monthly["month_end"].max().date(),
    )
    print(
        "Missing SPF CPI:",
        int(monthly["spf_cpi_next_quarter"].isna().sum()),
    )
    print(
        "Look-ahead violations:",
        int((monthly["release_date"] > monthly["month_end"]).sum()),
    )
    print()
    print("Validation checkpoints:")
    print(
        monthly.loc[
            monthly["month_end"].isin(
                pd.to_datetime(
                    [
                        "2016-01-31",
                        "2016-02-29",
                        "2019-02-28",
                        "2019-03-31",
                        "2025-06-30",
                    ]
                )
            )
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
