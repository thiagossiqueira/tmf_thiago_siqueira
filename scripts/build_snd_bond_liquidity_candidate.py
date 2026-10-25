"""
TFM WP-06D - Build SND historical bond-liquidity candidate.

Definition
----------
verified_trade_day = 1 iff SND reports >=1 secondary-market trade record
eligible day = cdr_anbima business day within [ISSUE_DT, MATURITY)
bond_trading_day_share_snd =
    verified_trading_days_snd / eligible_trading_days_snd

Panel window ends at 2025-06, matching frozen thesis panel v4.

No-trade convention
-------------------
verified_trading_days_snd = 0
bond_trading_day_share_snd = 0
total_reported_quantity_snd = missing
total_reported_trades_snd = missing
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from calendars.daycounts import DayCounts


DAYCOUNT = DayCounts(
    "bus/252",
    calendar="cdr_anbima",
)

PANEL_SKELETON = (
    ROOT
    / "datos_y_modelos"
    / "db"
    / "econometrics_db"
    / "wp06b_bond_liquidity_candidate_v1.csv"
)

CROSSWALK = (
    ROOT
    / "datos_y_modelos"
    / "db"
    / "brazil_domestic_corp_bonds"
    / "wp06c_103_bonds_exchange_id_crosswalk.csv"
)

SND_TRADES = (
    ROOT
    / "datos_y_modelos"
    / "db"
    / "brazil_domestic_corp_bonds"
    / "snd_secondary_market"
    / "snd_103_bonds_trades_raw.csv"
)

OUTPUT = (
    ROOT
    / "datos_y_modelos"
    / "db"
    / "econometrics_db"
    / "wp06d_bond_liquidity_snd_candidate_v1.csv"
)

PANEL_END = pd.Timestamp("2025-06-30")


def parse_br_number(value):
    if pd.isna(value):
        return np.nan

    text = str(value).strip()

    if not text:
        return np.nan

    return float(
        text
        .replace(".", "")
        .replace(",", ".")
    )


def eligible_days(row):
    month_start = row["month"].start_time
    next_month_start = (
        row["month"] + 1
    ).start_time

    start = max(
        month_start,
        row["ISSUE_DT"],
    )

    end = min(
        next_month_start,
        row["MATURITY"],
    )

    if start >= end:
        return 0

    dates = pd.date_range(
        start=start.normalize(),
        end=(end - pd.Timedelta(days=1)).normalize(),
        freq="D",
    )

    return sum(
        bool(DAYCOUNT.isbus(d))
        and d >= row["ISSUE_DT"]
        and d < row["MATURITY"]
        for d in dates
    )


def main():

    # --------------------------------------------------------
    # Panel skeleton
    # --------------------------------------------------------

    panel = pd.read_csv(
        PANEL_SKELETON,
        encoding="utf-8-sig",
    )[
        [
            "bond_id",
            "obs_date",
        ]
    ].copy()

    panel["obs_date"] = pd.to_datetime(
        panel["obs_date"],
        errors="raise",
    )

    panel["month"] = (
        panel["obs_date"]
        .dt.to_period("M")
    )

    if len(panel) != 4648:
        raise RuntimeError(
            f"Expected 4,648 panel rows; found {len(panel)}"
        )

    if panel["bond_id"].nunique() != 103:
        raise RuntimeError(
            "Expected 103 panel bonds."
        )

    # --------------------------------------------------------
    # Lifecycle
    # --------------------------------------------------------

    crosswalk = pd.read_csv(
        CROSSWALK,
        encoding="utf-8-sig",
    )

    crosswalk["ISSUE_DT"] = pd.to_datetime(
        crosswalk["ISSUE_DT"],
        errors="raise",
    )

    crosswalk["MATURITY"] = pd.to_datetime(
        crosswalk["MATURITY"],
        errors="raise",
    )

    life = crosswalk[
        [
            "ID",
            "ISSUE_DT",
            "MATURITY",
        ]
    ].rename(
        columns={
            "ID": "bond_id",
        }
    )

    panel = panel.merge(
        life,
        on="bond_id",
        how="left",
        validate="many_to_one",
    )

    if panel[
        ["ISSUE_DT", "MATURITY"]
    ].isna().any().any():
        raise RuntimeError(
            "Missing lifecycle data."
        )

    # --------------------------------------------------------
    # SND daily trade records
    # --------------------------------------------------------

    trades = pd.read_csv(
        SND_TRADES,
        encoding="utf-8-sig",
    )

    trades["trade_date"] = pd.to_datetime(
        trades["trade_date"],
        format="%d/%m/%Y",
        errors="raise",
    )

    trades = trades.loc[
        trades["trade_date"] <= PANEL_END
    ].copy()

    trades["month"] = (
        trades["trade_date"]
        .dt.to_period("M")
    )

    if trades.duplicated(
        ["bloomberg_id", "trade_date"]
    ).any():
        raise RuntimeError(
            "Duplicate SND bond-date records."
        )

    trades["quantity"] = (
        trades["quantity_raw"]
        .map(parse_br_number)
    )

    trades["num_trades"] = (
        trades["num_trades_raw"]
        .map(parse_br_number)
    )

    monthly = (
        trades.groupby(
            ["bloomberg_id", "month"],
            as_index=False,
        )
        .agg(
            verified_trading_days_snd=(
                "trade_date",
                "nunique",
            ),
            total_reported_quantity_snd=(
                "quantity",
                "sum",
            ),
            total_reported_trades_snd=(
                "num_trades",
                "sum",
            ),
        )
        .rename(
            columns={
                "bloomberg_id": "bond_id",
            }
        )
    )

    # --------------------------------------------------------
    # Merge onto all 4,648 thesis observations
    # --------------------------------------------------------

    panel = panel.merge(
        monthly,
        on=["bond_id", "month"],
        how="left",
        validate="one_to_one",
    )

    no_trade = (
        panel["verified_trading_days_snd"]
        .isna()
    )

    panel[
        "verified_trading_days_snd"
    ] = (
        panel["verified_trading_days_snd"]
        .fillna(0)
        .astype(int)
    )

    # Preserve WP-06B convention:
    # no trade => volume/count aggregates remain missing.
    panel.loc[
        no_trade,
        [
            "total_reported_quantity_snd",
            "total_reported_trades_snd",
        ],
    ] = np.nan

    # --------------------------------------------------------
    # Eligible days: exact frozen WP-06B denominator
    # --------------------------------------------------------

    panel[
        "eligible_trading_days_snd"
    ] = panel.apply(
        eligible_days,
        axis=1,
    ).astype(int)

    if (
        panel["eligible_trading_days_snd"]
        <= 0
    ).any():
        bad = panel.loc[
            panel["eligible_trading_days_snd"] <= 0,
            [
                "bond_id",
                "obs_date",
                "ISSUE_DT",
                "MATURITY",
            ],
        ]

        raise RuntimeError(
            "Panel rows with zero eligible days:\n"
            + bad.to_string(index=False)
        )

    # --------------------------------------------------------
    # Liquidity share
    # --------------------------------------------------------

    panel[
        "bond_trading_day_share_snd"
    ] = (
        panel["verified_trading_days_snd"]
        /
        panel["eligible_trading_days_snd"]
    )

    panel[
        "liquidity_snd_usable"
    ] = 1

    # Impossible value gate
    if (
        panel["bond_trading_day_share_snd"]
        > 1 + 1e-12
    ).any():
        bad = panel.loc[
            panel["bond_trading_day_share_snd"]
            > 1 + 1e-12,
            [
                "bond_id",
                "obs_date",
                "eligible_trading_days_snd",
                "verified_trading_days_snd",
                "bond_trading_day_share_snd",
            ],
        ]

        raise RuntimeError(
            "SND verified days exceed eligible days:\n"
            + bad.to_string(index=False)
        )

    # --------------------------------------------------------
    # Final candidate
    # --------------------------------------------------------

    output = panel[
        [
            "bond_id",
            "obs_date",
            "liquidity_snd_usable",
            "eligible_trading_days_snd",
            "verified_trading_days_snd",
            "total_reported_quantity_snd",
            "total_reported_trades_snd",
            "bond_trading_day_share_snd",
        ]
    ].copy()

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.to_csv(
        OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )

    # --------------------------------------------------------
    # Audit screen
    # --------------------------------------------------------

    print(
        "=== WP-06D SND LIQUIDITY CANDIDATE v1 ==="
    )

    print("\nSAMPLE")
    print("Rows:", len(output))
    print(
        "Bonds:",
        output["bond_id"].nunique(),
    )
    print(
        "First month:",
        output["obs_date"]
        .min()
        .to_period("M"),
    )
    print(
        "Last month:",
        output["obs_date"]
        .max()
        .to_period("M"),
    )

    print("\nTRADING")
    print(
        "Rows with >=1 verified trade day:",
        int(
            (
                output["verified_trading_days_snd"]
                > 0
            ).sum()
        ),
    )
    print(
        "Zero-share months:",
        int(
            (
                output[
                    "bond_trading_day_share_snd"
                ]
                == 0
            ).sum()
        ),
    )

    print("\nDISTRIBUTION")
    s = output[
        "bond_trading_day_share_snd"
    ]

    print("Mean:", round(s.mean(), 6))
    print("Median:", round(s.median(), 6))
    print("Min:", round(s.min(), 6))
    print("Max:", round(s.max(), 6))

    print("\nDENOMINATOR")
    print(
        "Eligible min:",
        output[
            "eligible_trading_days_snd"
        ].min(),
    )
    print(
        "Eligible max:",
        output[
            "eligible_trading_days_snd"
        ].max(),
    )

    print("\nOUTPUT")
    print(OUTPUT)


if __name__ == "__main__":
    main()
