# src/finmath/termstructure/ntnb_real_curve.py

import numpy as np
import pandas as pd

from calendars.daycounts import DayCounts

from src.finmath.termstructure.curve_models import (
    NelsonSiegelSvensson,
)
from src.finmath.termstructure.combined_real_curve import CombinedRealCurve


# ANBIMA convention for sovereign curves
DAYCOUNT_BUS252 = DayCounts("bus/252", calendar="cdr_anbima")


# =====================================================================
# 1. Load NTNB metadata (using correct identifier column: "ID")
# =====================================================================
def load_ntnb_metadata(govt_path: str) -> pd.DataFrame:
    """
    Load NTNB metadata from domestic_sovereign_curve_brazil.xlsx,
    using the column 'ID' (with "Corp" suffix) as the identifier.

    This EXACTLY matches YA govt columns such as:
        "BRSTNCNTB4U6 Corp"
        "BRSTNCNTB682 Corp"
    """

    df = pd.read_excel(govt_path, sheet_name="db_values_only")

    # Identifier column is "ID" (uppercase) — not "id", not ISIN
    if "ID" not in df.columns:
        raise ValueError("Column 'ID' not found in government metadata Excel.")

    df["ID"] = df["ID"].astype(str).str.strip()

    # Filter only NTNB (inflation-linked) bonds
    df["CALC_TYP_DES"] = df["CALC_TYP_DES"].astype(str).str.upper().str.strip()
    df = df[df["CALC_TYP_DES"] == "BRAZIL I/L BOND"].copy()

    df["ISSUE_DT"] = pd.to_datetime(
        df["ISSUE_DT"],
        errors="coerce"
    )

    df["MATURITY"] = pd.to_datetime(
        df["MATURITY"],
        errors="coerce"
    )

    df["FIRST_CPN_DT"] = pd.to_datetime(
        df["FIRST_CPN_DT"],
        errors="coerce"
    )

    df = df.dropna(
        subset=[
            "ID",
            "ISSUE_DT",
            "MATURITY",
            "FIRST_CPN_DT",
        ]
    )

    # Ensure coupon fields exist
    for col in ["CPN", "CPN_FREQ", "CPN_TYP"]:
        if col not in df.columns:
            df[col] = np.nan

    # Use ID as index (this matches YA tickers)
    df = df.set_index("ID")

    return df


# =====================================================================
# 2. Load NTNB yields from govt_ya.v1.xlsx
# =====================================================================
def load_ntnb_yields(ya_path: str, id_index) -> pd.DataFrame:
    """
    Load NTNB YA yields using the SAME IDs as metadata.
    These IDs look like "BRSTNCNTB4U6 Corp" and appear as YA columns.
    """

    df = pd.read_excel(ya_path, sheet_name="ya_values_only")

    # Keep the column names exactly, just strip whitespace
    df.columns = [str(c).strip() for c in df.columns]

    # First column = date
    date_col = df.columns[0]
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).set_index(date_col)

    meta_ids = list(id_index)

    # Select only columns that match metadata NTNB IDs
    cols = [c for c in df.columns if c in meta_ids]

    # DEBUG
    print("\n[DEBUG] Raw YA columns:", df.columns.tolist()[:20])
    print("[DEBUG] Expected NTNB IDs:", meta_ids[:20])
    print("[DEBUG] Matching NTNB YA columns:", cols)

    # Extract only those columns
    df = df[cols].apply(pd.to_numeric, errors="coerce")

    return df



# =====================================================================
# 3. Build normalized NTN-B future cash flows
# =====================================================================
def build_ntnb_cash_flows(
    meta_row: pd.Series,
    obs_date: pd.Timestamp,
    principal: float = 100.0,
) -> pd.Series:
    """
    Build future normalized cash flows for a standard NTN-B.

    NTN-B convention:
      - 6% annual real coupon
      - semiannual coupon payments
      - semiannual coupon factor:
            (1 + 0.06) ** 0.5 - 1
      - principal normalized to 100
      - only cash flows strictly after obs_date are returned

    The normalization means that historical VNA is not required for
    constructing the real zero-rate curve.
    """

    obs_date = pd.Timestamp(obs_date).normalize()

    first_coupon = pd.Timestamp(
        meta_row["FIRST_CPN_DT"]
    ).normalize()

    maturity = pd.Timestamp(
        meta_row["MATURITY"]
    ).normalize()

    annual_coupon = float(meta_row["CPN"]) / 100.0
    frequency = int(meta_row["CPN_FREQ"])

    if frequency != 2:
        raise ValueError(
            f"Unexpected NTN-B coupon frequency: {frequency}"
        )

    # Brazilian NTN-B semiannual coupon convention:
    # not simply 6% / 2.
    semiannual_coupon_rate = (
        (1.0 + annual_coupon) ** (1.0 / frequency)
        - 1.0
    )

    coupon_amount = (
        principal * semiannual_coupon_rate
    )

    # Build complete coupon schedule from first coupon date
    # through maturity.
    payment_dates = []

    d = first_coupon

    while d <= maturity:
        payment_dates.append(d)
        d = d + pd.DateOffset(
            months=int(12 / frequency)
        )

    # Defensive guard: ensure maturity is included exactly once.
    if maturity not in payment_dates:
        payment_dates.append(maturity)

    payment_dates = sorted(
        set(payment_dates)
    )

    cash_flows = {}

    for payment_date in payment_dates:

        # We only need future cash flows as of obs_date.
        if payment_date <= obs_date:
            continue

        amount = coupon_amount

        # Principal is repaid at maturity.
        if payment_date == maturity:
            amount += principal

        cash_flows[
            payment_date.date()
        ] = float(amount)

    return pd.Series(
        cash_flows,
        dtype=float,
    ).sort_index()


def price_ntnb_from_ytm(
    cash_flows: pd.Series,
    obs_date: pd.Timestamp,
    ytm: float,
) -> float:
    """
    Reconstruct a normalized NTN-B price from its observed real YTM.

    Parameters
    ----------
    cash_flows
        Future normalized NTN-B cash flows.
    obs_date
        Curve observation date.
    ytm
        Annual real YTM in decimal form
        (e.g. 0.075 = 7.5%).

    Returns
    -------
    float
        Normalized bond price.

    Notes
    -----
    Discounting follows the Brazilian BUS/252 convention:

        P = sum[ CF_t / (1 + y)^tau_t ]

    where tau_t is the BUS/252 year fraction from the
    observation date to each payment date.
    """

    obs_date = pd.Timestamp(obs_date).normalize()
    ytm = float(ytm)

    if ytm <= -1.0:
        raise ValueError(
            f"Invalid YTM for discounting: {ytm}"
        )

    price = 0.0

    for payment_date, amount in cash_flows.items():

        payment_date = pd.Timestamp(
            payment_date
        ).normalize()

        t = DAYCOUNT_BUS252.tf(
            obs_date.date(),
            payment_date.date(),
        )

        if t <= 0:
            continue

        price += (
            float(amount)
            / ((1.0 + ytm) ** float(t))
        )

    return float(price)

# =====================================================================
# 3. Build real sovereign curve for ONE DATE using NSS
# =====================================================================
def build_real_curve_for_date(
    obs_date: pd.Timestamp,
    meta_df: pd.DataFrame,
    ya_df: pd.DataFrame,
    wla_yield_func_for_date,
    wla_max_tenor_func_for_date=None,
) -> CombinedRealCurve | None:

    """
    Build the real sovereign zero curve for one observation date.

    Method:
      1. Keep only NTN-Bs that are active on obs_date.
      2. Exclude missing / zero-placeholder YTMs.
      3. Build normalized future NTN-B cash flows.
      4. Reconstruct normalized bond prices from observed real YTMs.
      5. Fit a price-based NSS zero/spot curve.
      6. Combine:
            WLA zero curve for t <= 5 years
            NTN-B NSS zero curve for t > 5 years
         with continuity at the 5-year splice.
    """

    obs_date = pd.Timestamp(obs_date).normalize()

    # No sovereign data for this date
    if ya_df.empty or obs_date not in ya_df.index:
        return None

    row = ya_df.loc[obs_date]

    prices = []
    cash_flows = []
    ytms = []
    ntnb_tenors = []

    for sec_id in meta_df.index:

        if sec_id not in row.index:
            continue

        y_raw = row[sec_id]

        if pd.isna(y_raw):
            continue

        y_raw = float(y_raw)

        # In the sovereign YA dataset, 0.00 represents an
        # unavailable observation. No active zero-YTM NTN-B
        # observations occur on the thesis monthly curve dates.
        if y_raw == 0.0:
            continue

        meta_row = meta_df.loc[sec_id]

        issue_date = meta_row["ISSUE_DT"]
        maturity = meta_row["MATURITY"]

        if pd.isna(issue_date) or pd.isna(maturity):
            continue

        issue_date = pd.Timestamp(issue_date).normalize()
        maturity = pd.Timestamp(maturity).normalize()

        # Bond must actually exist on the observation date.
        if obs_date < issue_date or obs_date >= maturity:
            continue

        ntnb_tenor = DAYCOUNT_BUS252.tf(
            obs_date,
            maturity,
        )

        # Bloomberg YA stores percentage points:
        # 7.50 means 7.50%.
        ytm = y_raw / 100.0
        ytms.append(ytm)


        cf = build_ntnb_cash_flows(
            meta_row=meta_row,
            obs_date=obs_date,
        )

        if cf.empty:
            continue

        price = price_ntnb_from_ytm(
            cash_flows=cf,
            obs_date=obs_date,
            ytm=ytm,
        )

        prices.append(price)
        cash_flows.append(cf)
        ntnb_tenors.append(float(ntnb_tenor))

    # Four beta parameters are estimated by the NSS specification.
    if len(prices) < 4:
        return None

    # Price-based NSS fit:
    # fitted rates are zero / spot rates, not coupon-bond YTMs.
    initial_betas = np.array(
        [float(np.median(ytms)), 0.0, 0.0, 0.0]
    )

    nss_curve = NelsonSiegelSvensson(
        prices=prices,
        cash_flows=cash_flows,
        day_count_convention="bus/252",
        calendar="cdr_anbima",
        ref_date=obs_date.date(),
        initial_betas=initial_betas,
    )

    # WLA is already a zero-rate curve.
    def wla_func(t: float) -> float:
        return wla_yield_func_for_date(
            obs_date,
            t,
        )

    # -------------------------------------------------------------
    # Dynamic splice points:
    #   t_switch    = last actually observed WLA tenor on obs_date
    #   t_blend_end = first valid NTN-B maturity beyond that point
    # -------------------------------------------------------------
    if wla_max_tenor_func_for_date is None:
        return None

    t_switch = wla_max_tenor_func_for_date(obs_date)

    if pd.isna(t_switch):
        return None

    t_switch = float(t_switch)

    ntnb_beyond_wla = [
        t for t in ntnb_tenors
        if t > t_switch
    ]

    if not ntnb_beyond_wla:
        return None

    t_blend_end = float(min(ntnb_beyond_wla))

    combined = CombinedRealCurve(
        wla_func=wla_func,
        model_curve=nss_curve,
        t_switch=t_switch,
        t_blend_end=t_blend_end,
    )

    return combined