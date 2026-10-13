from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

PANEL_FILE = (
    ROOT
    / "datos_y_modelos"
    / "db"
    / "econometrics_db"
    / "panel_main_and_robustness_rebuilt.xlsx"
)

OUTPUT_DIR = (
    ROOT
    / "datos_y_modelos"
    / "db"
    / "brazil_macroeconomic_data"
    / "real_brazil_3m"
)

OUTPUT_FILE = OUTPUT_DIR / "focus_ipca_3m_expected_panel_dates.csv"

BCB_ENDPOINT = (
    "https://olinda.bcb.gov.br/olinda/servico/"
    "Expectativas/versao/v1/odata/ExpectativaMercadoMensais"
)


def panel_dates() -> pd.DatetimeIndex:
    df = pd.read_excel(
        PANEL_FILE,
        sheet_name="ts",
        usecols=["obs_date"],
    )

    dates = (
        pd.to_datetime(
            df["obs_date"],
            errors="coerce",
            format="mixed",
        )
        .dropna()
        .dt.normalize()
        .drop_duplicates()
        .sort_values()
    )

    if dates.empty:
        raise ValueError("No valid panel observation dates found.")

    return pd.DatetimeIndex(dates)


def focus_rows_for_date(obs_date: pd.Timestamp) -> list[dict]:
    date_text = obs_date.strftime("%Y-%m-%d")

    flt = (
        "Indicador eq 'IPCA' "
        f"and Data eq '{date_text}' "
        "and baseCalculo eq 0"
    )

    url = (
        BCB_ENDPOINT
        + "?%24format=json"
        + "&%24select=Data,DataReferencia,Mediana,baseCalculo"
        + "&%24filter="
        + quote(flt, safe="'")
        + "&%24top=100"
    )

    last_error = None

    for attempt in range(3):
        try:
            with urlopen(url, timeout=30) as response:
                return json.load(response)["value"]
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.0)

    raise RuntimeError(
        f"BCB Focus request failed for {date_text}: {last_error}"
    )


def build_series() -> pd.DataFrame:
    rows = []

    for obs_date in panel_dates():

        targets = [
            obs_date + pd.DateOffset(months=1),
            obs_date + pd.DateOffset(months=2),
            obs_date + pd.DateOffset(months=3),
        ]

        target_labels = [
            d.strftime("%m/%Y")
            for d in targets
        ]

        raw = focus_rows_for_date(obs_date)

        selected = {}

        for item in raw:
            ref = item.get("DataReferencia")

            if ref in target_labels:
                if ref in selected:
                    raise ValueError(
                        f"Duplicate Focus row for "
                        f"{obs_date.date()} / {ref}"
                    )

                selected[ref] = item

        missing = [
            ref
            for ref in target_labels
            if ref not in selected
        ]

        if missing:
            raise ValueError(
                f"{obs_date.date()}: missing Focus targets {missing}"
            )

        medians = [
            float(selected[ref]["Mediana"])
            for ref in target_labels
        ]

        pi_3m = (
            (1.0 + medians[0] / 100.0)
            * (1.0 + medians[1] / 100.0)
            * (1.0 + medians[2] / 100.0)
            - 1.0
        )

        # Fixed three-calendar-month expectation:
        # annualize a three-month cumulative rate with power 4.
        pi_ann = (1.0 + pi_3m) ** 4 - 1.0

        rows.append(
            {
                "obs_date": obs_date,
                "target_m1": target_labels[0],
                "target_m2": target_labels[1],
                "target_m3": target_labels[2],
                "ipca_exp_m1_pct": medians[0],
                "ipca_exp_m2_pct": medians[1],
                "ipca_exp_m3_pct": medians[2],
                "expected_ipca_3m_pct": pi_3m * 100.0,
                "expected_ipca_ann_pct": pi_ann * 100.0,
                "focus_indicator": "IPCA",
                "focus_base_calculo": 0,
            }
        )

    return pd.DataFrame(rows)


def validate(out: pd.DataFrame) -> None:
    expected_dates = panel_dates()

    if len(out) != len(expected_dates):
        raise ValueError(
            f"Expected {len(expected_dates)} rows, got {len(out)}."
        )

    if out["obs_date"].duplicated().any():
        raise ValueError("Duplicate obs_date rows detected.")

    if out.isna().any().any():
        raise ValueError(
            "Missing values detected in Focus expected-IPCA output."
        )

    if not pd.DatetimeIndex(out["obs_date"]).equals(expected_dates):
        raise ValueError(
            "Focus output dates do not exactly match frozen-panel dates."
        )

    checks = {
        "2011-04-29": {
            "m1": 0.43,
            "m2": 0.25,
            "m3": 0.30,
            "pi3m": 0.983118224999968,
            "piann": 3.99084520276192,
        },
        "2020-04-30": {
            "m1": -0.27,
            "m2": 0.10,
            "m3": 0.23,
            "pi3m": 0.059338379,
            "piann": 0.237564862178874,
        },
        "2024-04-30": {
            "m1": 0.25,
            "m2": 0.17,
            "m3": 0.15,
            "pi3m": 0.5710556375,
            "piann": 2.303863418,
        },
    }

    indexed = out.set_index(
        out["obs_date"].dt.strftime("%Y-%m-%d")
    )

    for date_text, expected in checks.items():
        row = indexed.loc[date_text]

        tests = {
            "ipca_exp_m1_pct": expected["m1"],
            "ipca_exp_m2_pct": expected["m2"],
            "ipca_exp_m3_pct": expected["m3"],
            "expected_ipca_3m_pct": expected["pi3m"],
            "expected_ipca_ann_pct": expected["piann"],
        }

        for column, target in tests.items():
            actual = float(row[column])

            if abs(actual - target) > 1e-8:
                raise ValueError(
                    f"{date_text} {column}: "
                    f"expected {target}, got {actual}"
                )


def main() -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    out = build_series()
    validate(out)

    out.to_csv(
        OUTPUT_FILE,
        index=False,
        date_format="%Y-%m-%d",
    )

    print("REAL BRAZIL 3M - FOCUS IPCA BUILDER")
    print("------------------------------------")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Rows: {len(out)}")
    print(
        "Range:",
        out["obs_date"].min().date(),
        "to",
        out["obs_date"].max().date(),
    )
    print(
        "Missing values:",
        int(out.isna().sum().sum()),
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
            )
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
